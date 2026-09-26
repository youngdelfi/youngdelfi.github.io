---
name: omint-cartilla
description: Carga la cobertura de "Estudios de Diagnostico y Tratamiento" (centros, no medicos individuales) de Omint a la base de Supabase "Mi Turno Salud", usando la API real detras de la cartilla publica de autogestion.omint.com.ar para CABA + GBA (Norte/Oeste/Sur). Usar cuando el usuario pida cargar/actualizar la cobertura de Omint.
---

# Carga de cobertura Omint (via API)

## Hallazgos clave (no obvios)

1. **La SPA visible (autogestion.omint.com.ar) no es el backend.** Pegarle
   directo a `autogestion.omint.com.ar/api/...` da 404 (ese host solo sirve
   el bundle de React). El backend real es:

   ```
   https://ws.grupo-omint.com.ar/ws-pad/api/v0/OpenMedicalDirectory
   ```

   Se descubre leyendo el JS bundle (`/static/js/main.*.chunk.js`) buscando
   `baseURL` / el objeto de config por ambiente (`PRODUCTION`).

2. **El endpoint `/search` devuelve `results: []` (con `totalRows` correcto)
   si no se mandan los headers `Origin` y `Referer` imitando el sitio real.**
   Sin esos headers "funciona" (200 OK) pero no trae nada:

   ```
   Origin: https://autogestion.omint.com.ar
   Referer: https://autogestion.omint.com.ar/cartilla/publica/L/mis-resultados
   ```

3. **Cada plan tiene su PROPIA taxonomia de secciones/especialidades.** El id
   de la seccion "Estudios de Diagnostico y Tratamiento" es `"W"` para el
   plan `7` (Genesis 1500) pero `"ED"` para el plan `XN` (Clasico 6500) —
   varia por plan, y los ids de sección incluso pueden referirse a cosas
   distintas entre planes (ej. sección `P` = "Consultorios de Profesionales"
   en un plan, pero `CM` en otro). Por eso hay que pedir
   `FilterSectionSpeciality?plan=<code>` **por cada plan** y buscar la
   sección por NOMBRE ("Estudios de Diagnóstico y Tratamiento"), nunca
   asumir un id fijo.
   El código numérico después del guion bajo (ej. `"63.00"` en `W_63.00` /
   `ED_63.00`) SÍ es estable entre planes (mismo catálogo subyacente) — el
   mapeo a nuestro esquema (`ESPECIALIDAD_MAP` en `fetch_omint.py`) se hace
   por ese código numérico.
   Dos planes (`11`=Comunidad, `10`=Omint midoc) no tienen sección de
   diagnóstico y tratamiento — quedan sin cargar, es esperado.

4. **La sección "Diagnóstico y Tratamiento" de Omint SÍ mezcla médicos
   individuales con centros reales** (a diferencia de Medife). Muchos
   médicos hacen sus propios estudios (ecocardiogramas, oftalmología,
   endoscopías, etc.) en su consultorio particular y aparecen listados ahí
   igual que un centro. No hay señal limpia tipo "coma en el nombre"
   (Medife) para separarlos — acá los nombres vienen en Mayúscula/minúscula
   normal, formato "Apellido Nombre" sin coma, indistinguible de una
   institución corta por patrón simple.
   Se resuelve con una heurística de palabras clave institucionales
   (`KW_WORDS` en el script: centro, instituto, laboratorio, clínica,
   consultorio, diagnóstico, etc. + siglas en mayúsculas + nombres de 5+
   palabras) y un descarte por defecto de cualquier nombre de 2-4 palabras
   sin esas keywords (bucket "dudoso"). Esto es un trade-off: puede excluir
   alguna institución real de nombre corto y genérico (falso negativo, se
   documenta y se puede revisar a mano en `review_dudoso.txt`) para evitar
   cargar médicos individuales como si fueran centros (falso positivo, mucho
   peor para la base). **Revisar siempre el archivo de dudosos generado
   antes de descartarlo definitivamente** — quedan casos raros de nombres
   compuestos españoles de 5 palabras que igual son médicos (ej. "Bavastro
   De Sapia Graciela Celina") y hay que sacarlos a mano si aparecen en el
   bucket de instituciones.

5. **Colisiones de sede por reuso de `itemID`:** un mismo lugar físico
   (mismo `itemID` en la API) puede aparecer bajo nombres de institución
   ligeramente distintos según la especialidad consultada (ej. "Diagnóstico
   por Imágenes Dr. Deragopyan" vs "Centro Medico Deragopyan", mismo
   itemID). Esto generaba `pid`s de staging distintos que, tras el merge por
   nombre normalizado, terminaban resolviendo al MISMO `prestador_id` con la
   MISMA dirección — violando la unicidad de sede. Se resuelve dedupeando
   por `(prestador_id, direccion normalizada)` ANTES del insert de `sede`
   (ver `_sdedup` en el paso de merge), no solo por `pid` de staging.

## Paso 1 — Correr el script

```bash
python3 .claude/skills/omint-cartilla/fetch_omint.py /path/scratchpad/omint_out
```

Genera `omint_raw.json`, `omint_p.sql`, `omint_s.sql`, `omint_a.sql`,
`omint_cob.sql`, `omint_summary.txt`. Tarda unos minutos (8 planes × ~55
especialidades × 4 ubicaciones ≈ 1100-1800 combos según cuántos planes
tengan sección de diagnóstico).

## Paso 2 — Revisar antes de cargar

- Aplicar la heurística de institución/dudoso (ver hallazgo 4) — el script
  YA la aplica al generar los `.sql`, pero conviene revisar
  `medife_summary.txt`/el listado de nombres cargados una vez más:
  - Nombres de 5+ palabras sin keyword institucional que hayan colado como
    institución (ej. nombres compuestos españoles) — sacarlos a mano con
    `sed -i '/<pid>/d' omint_*.sql` de los 4 archivos.
  - Nombres con coma tipo "Consultorio X Dres. Apellido1, Apellido2 y
    Apellido3" (consultorio compartido real) — está bien dejarlos como
    institución.

## Paso 3 — Cobertura y planes en Supabase

```sql
INSERT INTO cobertura (cobertura_id, pais_id, slug, nombre_comercial, tipo, fecha_alta)
VALUES ('COB-OMINT', 'ar', 'omint', 'Omint', 'prepaga', CURRENT_DATE)
ON CONFLICT DO NOTHING;

INSERT INTO cobertura_plan (plan_id, cobertura_id, nombre) VALUES
('PLAN-OMINT-CLASICO-6500', 'COB-OMINT', 'Omint Clasico 6500'),
('PLAN-OMINT-GENESIS-1500', 'COB-OMINT', 'Omint Genesis 1500'),
('PLAN-OMINT-GENESIS-2500', 'COB-OMINT', 'Omint Genesis 2500'),
('PLAN-OMINT-GLOBAL-4021', 'COB-OMINT', 'Omint Global 4021'),
('PLAN-OMINT-GLOBAL-4500', 'COB-OMINT', 'Omint Global 4500'),
('PLAN-OMINT-PREMIUM-8500', 'COB-OMINT', 'Omint Premium 8500')
ON CONFLICT DO NOTHING;
```

(Comunidad y Omint midoc no tienen datos de diagnóstico y tratamiento — no
se crea plan para ellos.)

## Paso 4 — Staging

```sql
DROP TABLE IF EXISTS _omt_p; DROP TABLE IF EXISTS _omt_s; DROP TABLE IF EXISTS _omt_a; DROP TABLE IF EXISTS _omt_cob;
CREATE TABLE _omt_p(pid text, nombre text);
CREATE TABLE _omt_s(pid text, direccion text, loc text, tel text);
CREATE TABLE _omt_a(pid text, atributo_id text, poblacion_id text);
CREATE TABLE _omt_cob(pid text, plan text);
```

Cargar los 4 archivos tal cual.

## Paso 5 — Merge a producción

Mismo patrón que Medife/Medicus, con el agregado del dedupe de sedes por
`(prestador_id, direccion)` antes de insertar (ver hallazgo 5):

```sql
BEGIN;

INSERT INTO prestador (prestador_id, pais_id, slug, nombre_comercial, tipo, catalogo_completo)
SELECT 'OMT-' || upper(t.pid), (SELECT pais_id FROM pais LIMIT 1),
       left(regexp_replace(normalizar(t.nombre),'[^a-z0-9]+','-','g'),60) || '-' || right(t.pid,6),
       t.nombre, 'centro', false
FROM _omt_p t
WHERE NOT EXISTS (SELECT 1 FROM prestador x WHERE normalizar(x.nombre_comercial) = normalizar(t.nombre))
AND NOT EXISTS (SELECT 1 FROM prestador x WHERE x.prestador_id = 'OMT-' || upper(t.pid));

CREATE TEMP TABLE _map ON COMMIT DROP AS
SELECT DISTINCT ON (t.pid) t.pid, p.prestador_id
FROM _omt_p t JOIN prestador p ON normalizar(p.nombre_comercial) = normalizar(t.nombre)
ORDER BY t.pid, p.prestador_id;

-- clave: dedupear por (prestador_id, direccion) ANTES de insertar sede,
-- porque distintos pids de staging pueden resolver al mismo prestador
-- con la misma direccion (ver hallazgo 5)
CREATE TEMP TABLE _sdedup ON COMMIT DROP AS
SELECT DISTINCT ON (m.prestador_id, normalizar(s.direccion))
  m.prestador_id, s.pid, s.direccion, s.loc, s.tel
FROM _omt_s s JOIN _map m ON m.pid = s.pid
ORDER BY m.prestador_id, normalizar(s.direccion), s.pid;

INSERT INTO sede (sede_id, prestador_id, slug, nombre, localidad_id, direccion, telefono, es_principal)
SELECT 'SD-OMT-' || s.pid || '-' || row_number() OVER (PARTITION BY s.pid ORDER BY s.direccion),
       s.prestador_id,
       left(regexp_replace(normalizar(s.direccion),'[^a-z0-9]+','-','g'),40) || '-omt-' || left(md5(s.pid),8) || '-' || row_number() OVER (PARTITION BY s.pid ORDER BY s.direccion),
       s.prestador_id || ' - ' || s.direccion, l.localidad_id, s.direccion, s.tel, false
FROM _sdedup s
LEFT JOIN localidad l ON normalizar(l.nombre) = normalizar(s.loc)
WHERE NOT EXISTS (SELECT 1 FROM sede sx WHERE sx.prestador_id = s.prestador_id AND normalizar(sx.direccion) = normalizar(s.direccion));

INSERT INTO prestador_cobertura (prestador_id, plan_id)
SELECT DISTINCT m.prestador_id,
  CASE c.plan
    WHEN 'Clasico 6500' THEN 'PLAN-OMINT-CLASICO-6500' WHEN 'Genesis 1500' THEN 'PLAN-OMINT-GENESIS-1500'
    WHEN 'Genesis 2500' THEN 'PLAN-OMINT-GENESIS-2500' WHEN 'Global 4021' THEN 'PLAN-OMINT-GLOBAL-4021'
    WHEN 'Global 4500' THEN 'PLAN-OMINT-GLOBAL-4500' WHEN 'Premium 8500' THEN 'PLAN-OMINT-PREMIUM-8500'
  END
FROM _omt_cob c JOIN _map m ON m.pid = c.pid
ON CONFLICT DO NOTHING;

INSERT INTO prestador_atributo (prestador_id, atributo_id, poblacion_id, sede_id)
SELECT DISTINCT m.prestador_id, a.atributo_id, a.poblacion_id, sd.sede_id
FROM _omt_a a JOIN _map m ON m.pid = a.pid
JOIN _omt_s s2 ON s2.pid = a.pid
JOIN sede sd ON sd.prestador_id = m.prestador_id AND normalizar(sd.direccion) = normalizar(s2.direccion)
ON CONFLICT DO NOTHING;

UPDATE sede s SET es_principal = true
WHERE s.sede_id IN (SELECT DISTINCT ON (prestador_id) sede_id FROM sede WHERE prestador_id IN (SELECT prestador_id FROM _map) ORDER BY prestador_id, sede_id)
AND NOT EXISTS (SELECT 1 FROM sede sx WHERE sx.prestador_id = s.prestador_id AND sx.es_principal);

COMMIT;
```

## Paso 6 — Verificar y limpiar

```sql
select plan_id, count(*) from prestador_cobertura where plan_id like 'PLAN-OMINT-%' group by plan_id;
select count(*) from prestador where prestador_id like 'OMT-%';

DROP TABLE _omt_p; DROP TABLE _omt_s; DROP TABLE _omt_a; DROP TABLE _omt_cob;
```

## Notas / limitaciones conocidas

- Ubicaciones cubiertas: `C` (Capital Federal), `B_BN`/`B_BO`/`B_BS` (GBA
  Norte/Oeste/Sur). `B_B` (resto de la Provincia de Buenos Aires) queda
  fuera a propósito, igual que se decidió para Medicus/Medife.
- El filtro institución/médico (hallazgo 4) es heurístico y conservador:
  puede haber excluido alguna institución real de nombre corto y genérico
  sin palabra clave reconocible. Si el usuario nota un centro faltante,
  buscarlo en el `review_dudoso.txt` de esa corrida y agregarlo a mano.
- Comunidad (plan `11`) y Omint midoc (plan `10`) no tienen red de
  diagnóstico y tratamiento en esta API — no se cargan.
