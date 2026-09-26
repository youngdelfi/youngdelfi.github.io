---
name: medife-cartilla
description: Carga la cobertura de "Diagnostico y Tratamiento" (centros, no medicos individuales) de Medife a la base de Supabase "Mi Turno Salud", usando la API publica de medifeapp (no PDF) para toda el area metropolitana (CABA + partidos de GBA). Usar cuando el usuario pida cargar/actualizar la cobertura de Medife.
---

# Carga de cobertura Medife (via API)

A diferencia de Medicus (cartilla en PDF), Medife expone sus prestadores en un
JSON publico (`www.medifeapp.com.ar/medifeapp/lista-prestadores-v2` y
endpoints relacionados), mucho mas simple de scrapear que un PDF. Este skill
reproduce la carga hecha con `fetch_medife.py`.

## Hallazgos clave (no obvios, ya resueltos en el script)

1. **`idProvincia` NO filtra geograficamente.** El filtro real es
   `codigoPostalUno` (codigo postal). El CP `9999` de la URL de ejemplo del
   usuario es un comodin que trae casi solo instituciones de CABA, sin
   importar el `idProvincia` usado — confirmado pidiendo el mismo combo
   plan+especialidad con `idProvincia=1` y `idProvincia=2`: devuelven
   subconjuntos distintos de IDs, pero el 100% de los registros trae
   `LOCALIDAD: "CIUDAD AUTONOMA DE BS.AS."` en ambos casos. Un CP real de GBA
   (ej. `1900`=La Plata, `1704`=Ramos Mejia, `1650`=San Martin) sí devuelve
   instituciones correctamente localizadas ahi.
   El script (`CODIGOS_POSTALES` en `fetch_medife.py`) barre `9999` (CABA) +
   ~28 CPs representativos, uno por partido de GBA. **No es un barrido
   exhaustivo** (hay cientos de CPs reales); si falta un centro de una zona
   puntual, agregar su CP a la lista.
2. **Un solo plan trae la pertenencia a los 8 planes completos.** Cada
   registro de la API trae, ademas de sus propios datos, flags booleanas
   (`ORO`, `BRONCE`, `PLATINUM`, `PLATA`, `BRONCECLASSIC`, `PLATACLASSIC`,
   `MEDIFEPLUS`, `INDIE`) indicando en que otros planes participa ese mismo
   prestador. Por eso alcanza con consultar 4 planes representativos
   (`QUERY_PLANS = ["ORO", "MEDIFE+", "PLATA CLASSIC", "INDIE"]`) para leer
   la pertenencia a los 8 planes completos — no hace falta consultar los 7/8
   planes uno por uno.
3. **ORO/PLATA/PLATINUM son practicamente universales** (presentes en el
   100% de las instituciones encontradas); BRONCE/BRONCE CLASSIC/PLATA
   CLASSIC casi (~97-98%); MEDIFE+ e INDIE son redes chicas y distintas
   (~15-20% de las instituciones). El paso de carga (Paso 5) aprovecha esto:
   linkea los 6 planes "anchos" en bloque a todas las instituciones
   (sobre-cobertura de ~25 links de mas sobre 1536 reales, documentada y
   aceptada) y carga MEDIFE+/INDIE con la lista exacta (mucho mas chica).
4. **Flakiness intermitente del backend**: a veces responde HTTP 200 con
   `content: []` pese a `totalElements > 0`. El script reintenta esto
   explicitamente (no basta con reintentar solo ante excepciones).
5. **Filtro de médicos**: `is_doctor(name)` es simplemente `',' in name` —
   verificado empiricamente contra el dataset completo: TODOS los nombres
   con coma son médicos ("APELLIDO, Nombre") y NINGUNA institución tiene
   coma. Mas robusto que cualquier regex de patrón de persona (evita el
   error de reconocer "D´ALESSANDRO, MARCELO" por su acento no-ASCII). Aun
   así quedan casos raros sin coma que son personas (ej. "LUXEN SCHIMPF
   GISELLA ADRIANA", "ZARINI PAULA") — revisar `medife_p.sql` a mano contra
   nombres de 2-4 palabras sin keywords institucionales (CENTRO, INSTITUTO,
   LABORATORIO, etc.) antes de cargar, y sacarlos con `sed -i '/<pid>/d'` de
   los 4 archivos de staging.

## Paso 1 — Correr el script

```bash
pip install --quiet requests   # solo usa stdlib (urllib), no requiere pip
python3 .claude/skills/medife-cartilla/fetch_medife.py /path/scratchpad/medife_out
```

Tarda varios minutos (≈4 planes × 56 especialidades × ~29 CPs ≈ 6500
combos, con `ThreadPoolExecutor(max_workers=6)`). Genera:
`medife_raw.json`, `medife_p.sql`, `medife_s.sql`, `medife_a.sql`,
`medife_cob.sql`, `medife_summary.txt`.

## Paso 2 — Revisar antes de cargar

- Leer `medife_summary.txt`: cantidad de instituciones por especialidad.
- Chequear nombres sin coma que parezcan personas (ver hallazgo 5) y
  sacarlos manualmente de los 4 SQL si aparecen.

## Paso 3 — Cobertura y planes en Supabase

```sql
INSERT INTO cobertura (cobertura_id, pais_id, slug, nombre_comercial, tipo, fecha_alta)
VALUES ('COB-MEDIFE', 'ar', 'medife', 'Medife', 'prepaga', CURRENT_DATE)
ON CONFLICT DO NOTHING;

INSERT INTO cobertura_plan (plan_id, cobertura_id, nombre) VALUES
('PLAN-MEDIFE-ORO', 'COB-MEDIFE', 'Medife Oro'),
('PLAN-MEDIFE-BRONCE', 'COB-MEDIFE', 'Medife Bronce'),
('PLAN-MEDIFE-PLATINUM', 'COB-MEDIFE', 'Medife Platinum'),
('PLAN-MEDIFE-PLATA', 'COB-MEDIFE', 'Medife Plata'),
('PLAN-MEDIFE-BRONCE-CLASSIC', 'COB-MEDIFE', 'Medife Bronce Classic'),
('PLAN-MEDIFE-PLATA-CLASSIC', 'COB-MEDIFE', 'Medife Plata Classic'),
('PLAN-MEDIFE-PLUS', 'COB-MEDIFE', 'Medife+'),
('PLAN-MEDIFE-INDIE', 'COB-MEDIFE', 'Medife Indie')
ON CONFLICT DO NOTHING;
```

## Paso 4 — Staging

```sql
DROP TABLE IF EXISTS _mdf_p; DROP TABLE IF EXISTS _mdf_s; DROP TABLE IF EXISTS _mdf_a; DROP TABLE IF EXISTS _mdf_cob;
CREATE TABLE _mdf_p(pid text, nombre text);
CREATE TABLE _mdf_s(pid text, direccion text, loc text, tel text);
CREATE TABLE _mdf_a(pid text, atributo_id text, poblacion_id text);
CREATE TABLE _mdf_cob(pid text, plan text);
```

Cargar `medife_p.sql`, `medife_s.sql`, `medife_a.sql` tal cual. Para
`_mdf_cob`, en vez de pegar las ~1500 filas del archivo, aprovechar el
hallazgo 3: linkear en bloque los 6 planes anchos y cargar MEDIFE+/INDIE
extrayendo solo esas filas del archivo (`grep "'MEDIFE+'"` / `grep "'INDIE'"`):

```sql
INSERT INTO _mdf_cob (pid, plan)
SELECT pid, plan FROM _mdf_p CROSS JOIN (VALUES ('ORO'),('PLATA'),('PLATINUM'),('BRONCE'),('BRONCE CLASSIC'),('PLATA CLASSIC')) AS v(plan);
-- + INSERT INTO _mdf_cob... con las filas MEDIFE+ / INDIE reales
```

## Paso 5 — Merge a producción

Mismo patrón que Medicus (namespacing de `sede_id` por `pid` de staging para
evitar colisiones), con el agregado del mapeo de plan vía `_mdf_cob`:

```sql
BEGIN;

INSERT INTO prestador (prestador_id, pais_id, slug, nombre_comercial, tipo, catalogo_completo)
SELECT 'MDF-' || upper(t.pid), (SELECT pais_id FROM pais LIMIT 1),
       left(regexp_replace(normalizar(t.nombre),'[^a-z0-9]+','-','g'),60) || '-' || right(t.pid,6),
       t.nombre, 'centro', false
FROM _mdf_p t
WHERE NOT EXISTS (SELECT 1 FROM prestador x WHERE normalizar(x.nombre_comercial) = normalizar(t.nombre));

CREATE TEMP TABLE _map ON COMMIT DROP AS
SELECT DISTINCT ON (t.pid) t.pid, p.prestador_id
FROM _mdf_p t JOIN prestador p ON normalizar(p.nombre_comercial) = normalizar(t.nombre)
ORDER BY t.pid, p.prestador_id;

INSERT INTO sede (sede_id, prestador_id, slug, nombre, localidad_id, direccion, telefono, es_principal)
SELECT 'SD-MDF-' || s.pid || '-' || row_number() OVER (PARTITION BY s.pid ORDER BY s.direccion),
       m.prestador_id,
       left(regexp_replace(normalizar(s.direccion),'[^a-z0-9]+','-','g'),50) || '-mdf-' || right(s.pid,6) || '-' || row_number() OVER (PARTITION BY s.pid ORDER BY s.direccion),
       m.prestador_id || ' - ' || s.direccion, l.localidad_id, s.direccion, s.tel, false
FROM _mdf_s s JOIN _map m ON m.pid = s.pid
LEFT JOIN localidad l ON normalizar(l.nombre) = normalizar(s.loc)
WHERE NOT EXISTS (SELECT 1 FROM sede sx WHERE sx.prestador_id = m.prestador_id AND normalizar(sx.direccion) = normalizar(s.direccion));

INSERT INTO prestador_cobertura (prestador_id, plan_id)
SELECT DISTINCT m.prestador_id,
  CASE c.plan
    WHEN 'ORO' THEN 'PLAN-MEDIFE-ORO' WHEN 'BRONCE' THEN 'PLAN-MEDIFE-BRONCE'
    WHEN 'PLATINUM' THEN 'PLAN-MEDIFE-PLATINUM' WHEN 'PLATA' THEN 'PLAN-MEDIFE-PLATA'
    WHEN 'BRONCE CLASSIC' THEN 'PLAN-MEDIFE-BRONCE-CLASSIC' WHEN 'PLATA CLASSIC' THEN 'PLAN-MEDIFE-PLATA-CLASSIC'
    WHEN 'MEDIFE+' THEN 'PLAN-MEDIFE-PLUS' WHEN 'INDIE' THEN 'PLAN-MEDIFE-INDIE'
  END
FROM _mdf_cob c JOIN _map m ON m.pid = c.pid
ON CONFLICT DO NOTHING;

INSERT INTO prestador_atributo (prestador_id, atributo_id, poblacion_id, sede_id)
SELECT DISTINCT m.prestador_id, a.atributo_id, a.poblacion_id, sd.sede_id
FROM _mdf_a a JOIN _map m ON m.pid = a.pid
JOIN _mdf_s s2 ON s2.pid = a.pid
JOIN sede sd ON sd.prestador_id = m.prestador_id AND normalizar(sd.direccion) = normalizar(s2.direccion)
ON CONFLICT DO NOTHING;

UPDATE sede s SET es_principal = true
WHERE s.sede_id IN (SELECT DISTINCT ON (prestador_id) sede_id FROM sede WHERE prestador_id IN (SELECT prestador_id FROM _map) ORDER BY prestador_id, sede_id)
AND NOT EXISTS (SELECT 1 FROM sede sx WHERE sx.prestador_id = s.prestador_id AND sx.es_principal);

COMMIT;
```

## Paso 6 — Verificar y limpiar

```sql
select plan_id, count(*) from prestador_cobertura where plan_id like 'PLAN-MEDIFE-%' group by plan_id;
select count(*) from prestador where prestador_id like 'MDF-%';

DROP TABLE _mdf_p; DROP TABLE _mdf_s; DROP TABLE _mdf_a; DROP TABLE _mdf_cob;
```

## Notas / limitaciones conocidas

- El barrido geográfico es por lista de CPs representativos (uno por
  partido de GBA), no exhaustivo. Puede faltar cobertura de barrios/zonas
  puntuales no cubiertas por el CP elegido para ese partido.
- La carga en bloque de los 6 planes "anchos" en `_mdf_cob` sobre-cubre
  levemente (~25 links de más sobre ~1536 reales para la corrida inicial):
  algunas instituciones quedan linkeadas a BRONCE/BRONCE CLASSIC/PLATA
  CLASSIC sin estar 100% confirmadas en esos planes puntuales. Aceptado
  como tradeoff de simplicidad; si se necesita exactitud total, cargar
  `_mdf_cob` fila por fila desde `medife_cob.sql` en vez de la carga en
  bloque.
- El especialidades sin mapeo en `ESPECIALIDAD_MAP` (kinesiología,
  nutrición, quimioterapia, etc.) igual generan prestador/sede pero no
  `prestador_atributo`.
