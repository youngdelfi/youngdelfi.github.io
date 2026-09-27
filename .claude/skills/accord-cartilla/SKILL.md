# Accord Salud cartilla — Diagnóstico y Tratamiento

Reusable pipeline to (re)load Accord Salud's imaging/lab "centros" (not individual
doctors) into the Supabase "Mi Turno Salud" DB, for CABA + GBA (área metropolitana),
across all plans. Mirrors the Medicus/Medife/Omint pipelines in scope and shape.

## Hallazgos clave

1. **Accord Salud shares its cartilla backend with Unión Personal.** The
   `accordsalud.com.ar/cartilla` page is a Vite/React SPA whose bundle
   (`assets/index-*.js`) calls `https://api.unionpersonal.com.ar/cartilla`
   directly — a REST API with a static `X-API-KEY` header baked into the JS
   (see `KEY` in `fetch_accord.py`). Accord Salud is Unión Personal's
   prepaga arm; passing `org="ac"` (vs `"up"` for Unión Personal itself, or
   `"uruguay"`) selects the Accord Salud network.

2. **Hierarchical REST API, one param per level**, all GET, all wrapped
   `{success, data, ...}`:
   ```
   /planes/{org}
   /zonas/{org}                                      -> "metropolitana" = CABA+GBA
   /tipos/{org}/{plan}                                -> M=MEDICA, O=ODONTO, ...
   /subzonas/{org}/{plan}/{zona}/{tipo}
   /categorias/{org}/{plan}/{zona}/{subzona}/{tipo}
   /especialidades/{org}/{plan}/{zona}/{subzona}/{tipo}/{categoria}
   /localidades/{org}/{plan}/{zona}/{subzona}/{tipo}/{categoria}/{especialidad}
   /prestadores/{org}/{plan}/{zona}/{subzona}/{tipo}/{categoria}/{especialidad}/{localidad}
   ```
   Diagnóstico y Tratamiento = tipo `M` (MEDICA), categorías `M6` (Estudios y
   Prácticas Médicas), `M7` (Radiología), `M11` (Laboratorios). Other `M`
   categories (M1/M2/M8/M9/M10 — internación, urgencias, especialidades
   médicas, fonoaudiología, kinesiología) are out of scope.

3. **`/prestadores` REQUIRES a localidad — without one it returns `data: []`
   with HTTP 200**, not an error. Localidades are NOT a fixed list per
   subzona: they must be swept from `/localidades` for every
   (subzona, categoria, especialidad) combo, exactly mirroring what the
   frontend does (`Promise.all` over each localidad's `/prestadores` call).
   This is a much finer crawl than Medife/Omint needed — full sweep across
   15 plans × 5 subzonas × ~33 especialidades × several localidades each
   comes out to ~4,000+ `/prestadores` calls, done concurrently
   (`asyncio` + `aiohttp`, semaphore 25) in a few minutes.

4. **Subzonas used** (the "área metropolitana" zone, CABA + GBA):
   `CAR991` Ciudad de Buenos Aires, `CAR992` GBA Norte, `CAR993` GBA Oeste,
   `CAR994` GBA Sur, `CAR995` GBA Noroeste.

5. **Unlike Medife (and like Omint), the M6/M7/M11 results mix individual
   doctors in with real institutions** (solo practitioners billing
   diagnostic studies — ecocardiogramas, laboratorios, etc. — under their
   own name). A keyword-based `is_institution()` classifier filters these
   out (see `KW_WORDS` in `fetch_accord.py`). Key difference from Omint's
   classifier: **all Accord names are uppercase**, so Omint's "short
   all-caps name = acronym" heuristic and "5+ words = institution"
   heuristic both produce false positives here (every doctor name is
   already short + uppercase; multiple doctors sharing one consultorio
   produce long strings like "ASCUA ESTER MARIA VICTORIA FABRO JUAN
   PEDRO" that are NOT institutions). Both heuristics were dropped for
   Accord; the classifier here relies only on: keyword match (institutional
   words + "RED UP" style entity suffixes), a digit in the name, and
   spaced-out legal-entity abbreviations (`S A`, `S R L`, `S H` — these
   don't match a plain `sa`/`srl` token since they're written with spaces).
   Reviewed manually against the actual fetched data (96 institutions kept
   of 176 raw names, 80 doctor names excluded — see `accord_review_dudoso.txt`).

6. **`poblacion_id` in `prestador_atributo` is TEXT, not an integer 1/2**
   (unlike what earlier providers' scripts assumed) — its FK actually points
   at `atributo(atributo_id)`, and the values in use are `'general'` /
   `'infantil'` / `'prenatal'`. The merge SQL maps the script's internal
   1/2 codes to `'general'`/`'infantil'` at insert time. Any future script
   reusing the old `(atributo_id, poblacion_id)` int convention must do the
   same translation — don't insert raw integers into `prestador_atributo`.

7. **Dedup key for a raw record**: `NomConsultorio` (the specific branch
   name, e.g. "CENTRO MEDICO DE NEFROLOGIA FINAER") rather than
   `NomPrestador` (the legal/holding name, e.g. "FINAER") — `NomConsultorio`
   is what the app actually displays and is closer to a commercial name.

## Runbook

1. `python3 fetch_accord.py` — fetches all plans → especialidades →
   localidades → prestadores concurrently, applies `is_institution()`,
   maps especialidad descriptions to `(atributo_id, poblacion_id)` via
   `ESPECIALIDAD_MAP`, and writes `accord_raw.json`, `accord_p.sql`,
   `accord_s.sql`, `accord_a.sql`, `accord_cob.sql`, `accord_summary.txt`,
   `accord_review_dudoso.txt`. Took ~7 minutes for the full 15-plan sweep.
2. Review `accord_review_dudoso.txt` (excluded doctor names) if precision
   matters more than recall for a re-sync.
3. Create `cobertura`/`cobertura_plan` rows for `COB-ACCORD` and its plans
   (`PLAN-ACCORD-<SLUG>`) if not already present.
4. Create 4 staging tables and load the generated SQL files:
   ```sql
   CREATE TABLE _acc_p (pid text, nombre text);
   CREATE TABLE _acc_s (pid text, direccion text, loc text, tel text);
   CREATE TABLE _acc_a (pid text, direccion text, atributo_id text, poblacion_id int);
   CREATE TABLE _acc_cob (pid text, plan_nombre text);
   ```
5. Run the merge transaction (see git history for the exact SQL used in
   this load — same shape as Medife/Omint's: insert new `prestador` rows
   deduped by `normalizar(nombre_comercial)` against ALL existing
   prestadores including other coverages; build `_map` (staging pid → real
   prestador_id); dedupe sedes per (prestador_id, normalizar(direccion))
   via a `_sdedup` temp table BEFORE inserting (a per-row `NOT EXISTS`
   check alone misses intra-statement duplicates — same trap as Omint);
   insert `prestador_cobertura` mapping raw plan names to
   `PLAN-ACCORD-*` ids; insert `prestador_atributo` translating
   poblacion_id 1/2 → `'general'`/`'infantil'`; mark one sede per
   prestador `es_principal`).
6. Verify per-plan `prestador_cobertura` counts, then
   `DROP TABLE _acc_p, _acc_s, _acc_a, _acc_cob;`.

## Load results (2026-09-27)

96 institutions in raw fetch → 68 new `prestador` rows created (rest
deduped against existing prestadores from other coverages), 82 sedes, 327
`prestador_atributo` links. All 15 plans have `prestador_cobertura` rows
(range 34–68 per plan). `pais_id` picked as `(SELECT pais_id FROM pais
LIMIT 1)` matching the convention used for Medife/Omint.

## Notas / limitaciones conocidas

- Some raw especialidad names had no counterpart in the existing atributo
  taxonomy (e.g. "CISTOSCOPIAS", "CAMPO VISUAL/CAMPIMETRIA", "RIESGO
  QUIRURGICO", "HISTEROSCOPIA") and were left unmapped — the institution
  and its sede are still loaded, just without that specific
  `prestador_atributo` link. See `ESPECIALIDAD_MAP` for the full mapping
  and the unmapped list printed by the script.
- The doctor/institution classifier is a heuristic; some short, generically
  named real institutions could in principle be misclassified as doctors.
  Reviewable via `accord_review_dudoso.txt`.
- 15 plans were fetched (`codigo_plan`s: 150, 220, 320, 420, 420C, 110, 210,
  310, AC101, AC102, AC211, 4, 3, 202, 5) — some (110/210/310 vs
  AC101/AC102/AC211) may be legacy/duplicate plan codes for the same
  commercial plans; both were kept since the API returns them as distinct
  `codigo_plan` values with their own cartilla results.
