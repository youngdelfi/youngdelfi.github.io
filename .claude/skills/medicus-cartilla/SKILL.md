---
name: medicus-cartilla
description: Carga la cobertura de "Diagnostico y Tratamiento" (centros de diagnostico por imagenes/laboratorio, no medicos individuales) de una cartilla PDF de Medicus a la base de Supabase "Mi Turno Salud", para cualquier plan (Azul, Celeste, Family Care, Integra, etc.) y toda el area metropolitana (CABA + zonas GBA). Usar cuando el usuario pase una URL de backend.medicus.com.ar/cartillas/*.pdf y pida cargar/actualizar ese plan.
---

# Carga de cartillas Medicus

Este skill reproduce el pipeline usado para cargar `PLAN-MEDICUS-AZUL` (project_id
Supabase `nazazktkstwphprjtbtr`), generalizado para cualquier PDF de cartilla
Medicus con la misma estructura ("CUERPO MEDICO" + "DIAGNOSTICO Y TRATAMIENTO"
+ "FARMACIAS"/"OPTICAS"). Solo carga la sección **Diagnóstico y Tratamiento**
(centros, no médicos individuales) — igual que se acordó con el usuario para
Plan Azul.

## Paso 0 — Confirmar con el usuario

Antes de tocar la base, confirmar: URL del PDF y `plan_id`/nombre de plan
(ej. "Celeste Advance", "Family Care One", "Integra"). Si el usuario no lo
dice explícitamente, preguntar el nombre corto del plan tal como debe
aparecer en `cobertura_plan.nombre`.

## Paso 1 — Descargar el PDF

`WebFetch` normalmente falla contra `backend.medicus.com.ar` (bloqueado por el
proxy de egress). Usar `curl` directo, que sí funciona:

```bash
mkdir -p /tmp/claude-0/*/scratchpad/medicus  # usar el scratchpad de la sesión
curl -sS -o /path/scratchpad/medicus/plan.pdf "https://backend.medicus.com.ar/cartillas/<NOMBRE>.pdf"
```

(La URL puede tener espacios/mayúsculas; pasarla entre comillas tal cual la
dio el usuario — curl no necesita URL-encoding manual para esto.)

## Paso 2 — Parsear con el script del skill

```bash
pip install --quiet pymupdf   # si no está instalado en el entorno
python3 .claude/skills/medicus-cartilla/parse_cartilla.py \
  /path/scratchpad/medicus/plan.pdf \
  <prefix_corto>  \
  /path/scratchpad/medicus/<prefix_corto>
```

- `<prefix_corto>`: 2-3 letras que identifiquen el plan y no choquen con
  prefijos ya usados (`mz` = Medicus Azul; usar `mc` para Celeste, `mf` para
  Family Care, `mi` para Integra, etc. — revisar que no exista ya un
  prestador con `prestador_id` que empiece igual).
- Esto genera `<prefix>_p.sql`, `<prefix>_s.sql`, `<prefix>_a.sql`,
  `<prefix>_entries.json` y `<prefix>_summary.txt` en el output dir.

**Importante:** el parser solo reconoce las modalidades listadas en
`MODMAP` dentro de `parse_cartilla.py` (Densitometría, Ecografía [+infantil],
Mamografía, Radiología [+infantil], Resonancia, Tomografía, Hemodinamia,
Endoscopía, Electrocardiograma, Electroencefalograma, Holter). Si el PDF
nuevo trae modalidades con otro texto exacto de encabezado, agregarlas a
`MODMAP` antes de correr (revisar `<prefix>_summary.txt`: las entradas bajo
"SIN MODALIDAD ESPECIFICA" son centros que no matchearon ningún atributo,
por texto no reconocido o por ser el bloque genérico de referencia al
principio de la sección — no significa que estén mal atribuidos a la
institución, solo que no llevan `prestador_atributo`).

## Paso 3 — Revisar antes de cargar

Leer `<prefix>_summary.txt` y sanity-check rápido:
- ¿El número de instituciones es razonable (parecido a Azul: ~90-100)?
- ¿Hay alguna institución con direcciones que mezclen zonas obviamente
  incompatibles (ej. un sanatorio de Recoleta con una sede en Pilar)? Eso
  indicaría un caso similar al bug ya resuelto (fragmentos de dirección sin
  localidad mal atribuidos) que el parser ya filtra, pero vale una
  revisión visual rápida por si aparece un patrón nuevo.
- Compartir el resumen con el usuario si el volumen es grande, antes de
  tocar producción (mismo criterio usado con Plan Azul).

## Paso 4 — Cobertura y plan en Supabase

```sql
INSERT INTO cobertura (cobertura_id, pais_id, slug, nombre_comercial, tipo, fecha_alta)
VALUES ('COB-MEDICUS', 'ar', 'medicus', 'Medicus', 'prepaga', CURRENT_DATE)
ON CONFLICT DO NOTHING;

INSERT INTO cobertura_plan (plan_id, cobertura_id, nombre)
VALUES ('PLAN-MEDICUS-<NOMBRE>', 'COB-MEDICUS', 'Medicus <Nombre>')
ON CONFLICT DO NOTHING;
```

## Paso 5 — Crear staging y cargar los 3 archivos SQL

```sql
DROP TABLE IF EXISTS _<prefix>_p; DROP TABLE IF EXISTS _<prefix>_s; DROP TABLE IF EXISTS _<prefix>_a;
CREATE TABLE _<prefix>_p(pid text, nombre text);
CREATE TABLE _<prefix>_s(pid text, direccion text, loc text);
CREATE TABLE _<prefix>_a(pid text, atributo_id text, poblacion_id text);
```

Luego ejecutar el contenido de `<prefix>_p.sql`, `<prefix>_s.sql`,
`<prefix>_a.sql` (leerlos con `Read` y pasarlos tal cual a
`mcp__Supabase__execute_sql`; si son muy grandes, partirlos en bloques).

## Paso 6 — Merge a producción

Mismo patrón que OSDE/Galeno/Azul — matchea por nombre normalizado, crea
solo los prestadores realmente nuevos, y usa un `sede_id` namespaced por
`pid` de staging (no por `prestador_id`) para evitar colisiones con sedes
ya creadas por otras cargas sobre el mismo prestador (esto rompió la
primera corrida de Plan Azul con "Centro Medico Deragopyan"):

```sql
BEGIN;

INSERT INTO prestador (prestador_id, pais_id, slug, nombre_comercial, tipo, catalogo_completo)
SELECT '<PREFIJO_MAY>-' || upper(t.pid),
       (SELECT pais_id FROM pais LIMIT 1),
       left(regexp_replace(normalizar(t.nombre),'[^a-z0-9]+','-','g'),60) || '-' || right(t.pid,6),
       t.nombre, 'centro', false
FROM _<prefix>_p t
WHERE NOT EXISTS (SELECT 1 FROM prestador x WHERE normalizar(x.nombre_comercial) = normalizar(t.nombre));

CREATE TEMP TABLE _map ON COMMIT DROP AS
SELECT DISTINCT ON (t.pid) t.pid, p.prestador_id
FROM _<prefix>_p t JOIN prestador p ON normalizar(p.nombre_comercial) = normalizar(t.nombre)
ORDER BY t.pid, p.prestador_id;

INSERT INTO sede (sede_id, prestador_id, slug, nombre, localidad_id, direccion, telefono, es_principal)
SELECT 'SD-<PREFIJO_MAY>-' || s.pid || '-' || row_number() OVER (PARTITION BY s.pid ORDER BY s.direccion),
       m.prestador_id,
       left(regexp_replace(normalizar(s.direccion),'[^a-z0-9]+','-','g'),50) || '-<prefix>-' || right(s.pid,6) || '-' || row_number() OVER (PARTITION BY s.pid ORDER BY s.direccion),
       m.prestador_id || ' - ' || s.direccion,
       l.localidad_id,
       s.direccion, NULL, false
FROM _<prefix>_s s
JOIN _map m ON m.pid = s.pid
LEFT JOIN localidad l ON normalizar(l.nombre) = normalizar(s.loc)
WHERE NOT EXISTS (
  SELECT 1 FROM sede sx WHERE sx.prestador_id = m.prestador_id AND normalizar(sx.direccion) = normalizar(s.direccion)
);

INSERT INTO prestador_cobertura (prestador_id, plan_id)
SELECT DISTINCT m.prestador_id, 'PLAN-MEDICUS-<NOMBRE>' FROM _map m
ON CONFLICT DO NOTHING;

INSERT INTO prestador_atributo (prestador_id, atributo_id, poblacion_id, sede_id)
SELECT DISTINCT m.prestador_id, a.atributo_id, a.poblacion_id, sd.sede_id
FROM _<prefix>_a a
JOIN _map m ON m.pid = a.pid
JOIN _<prefix>_s s2 ON s2.pid = a.pid
JOIN sede sd ON sd.prestador_id = m.prestador_id AND normalizar(sd.direccion) = normalizar(s2.direccion)
ON CONFLICT DO NOTHING;

UPDATE sede s SET es_principal = true
WHERE s.sede_id IN (
  SELECT DISTINCT ON (prestador_id) sede_id FROM sede WHERE prestador_id IN (SELECT prestador_id FROM _map)
  ORDER BY prestador_id, sede_id
)
AND NOT EXISTS (SELECT 1 FROM sede sx WHERE sx.prestador_id = s.prestador_id AND sx.es_principal);

COMMIT;
```

## Paso 7 — Verificar y limpiar

```sql
select count(*) from prestador_cobertura where plan_id='PLAN-MEDICUS-<NOMBRE>';
select count(*) from prestador where prestador_id like '<PREFIJO_MAY>-%';

DROP TABLE _<prefix>_p; DROP TABLE _<prefix>_s; DROP TABLE _<prefix>_a;
```

## Paso 8 — Duplicados (opcional pero recomendado)

Si varios planes de Medicus comparten los mismos centros (como pasó entre
Azul y lo que se cargue después), correr el chequeo de duplicados por
nombre normalizado y por similitud (`pg_trgm`) contra prestadores ya
existentes, igual que se hizo para Galeno 300/OSDE, antes de dar por
terminada la carga — confirmando por dirección antes de fusionar cualquier
par sospechoso.

## Notas / limitaciones conocidas

- El parser asume el mismo layout de columnas fijas (x<150 nombre, 150-300
  dirección, 300-420 localidad, ≥420 teléfono) y la misma jerarquía de
  negritas (14pt sección/zona al pie de página, 10pt categoría, 8pt
  modalidad). Si Medicus cambia el diseño del PDF, hay que re-verificar
  estas heurísticas contra el nuevo archivo antes de confiar en la salida.
- Los fragmentos de dirección sin localidad (partidos en dos líneas, típico
  en direcciones de autopista/km) se descartan en vez de adivinar a qué
  institución pertenecen — es decir, algunas sedes reales pueden faltar en
  vez de cargarse mal. Si el resumen muestra pocas instituciones para una
  zona, vale la pena revisar el PDF a mano en esa sección.
- El script solo extrae la sección "Diagnóstico y Tratamiento". Cuerpo
  Médico, Cuerpo Odontológico, Farmacias y Ópticas quedan fuera de alcance
  (igual que se decidió para Plan Azul) salvo que el usuario pida
  explícitamente extenderlo.
- **Direcciones cruzadas con localidad presente (visto en Integra):** el
  filtro de "fragmento sin localidad" (nota anterior) no atrapa todos los
  casos. Cuando el mismo nombre de institución se repite en cada bloque de
  modalidad (patrón normal del documento) y una institución tiene una
  dirección que ocupa 2+ líneas completas (con localidad incluida en una
  línea intermedia), esa dirección puede terminar atribuida a la
  institución impresa inmediatamente ANTES en vez de a la que realmente le
  pertenece — ambas instituciones son reales y ambas direcciones son
  reales, solo el emparejamiento nombre↔dirección fallado. Se vio con
  "Diagnóstico Tesla" arrastrando una sede de "Hospital San Juan de Dios".
  No hay filtro automático confiable para esto todavía: conviene, antes de
  cargar, buscar en `<prefix>_summary.txt` instituciones que compartan
  literalmente la misma dirección de texto con otra institución de nombre
  distinto (ej. grep de la localidad "MORON", "SAN JUSTO", etc. y comparar
  a mano contra el PDF esa página puntual) y corregir el JSON de entradas
  antes de generar el SQL final (como se hizo manualmente para Integra).
