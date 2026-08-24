# estudio-app

El sitio de Estudio.com, servido desde el catálogo que está en Supabase.

Next.js App Router. Todas las páginas se prerenderizan como HTML estático y se
revalidan solas cada hora (ISR): cuando cambia un dato en la base, esa página se
regenera sin rebuildear las otras. Es el requisito operativo del plan — con
miles de páginas, un rebuild completo por cada verificación de cartilla no
escala.

## Arrancar

```bash
cp .env.example .env      # completar DATABASE_URL y SITE_URL
npm install
npm run dev               # http://localhost:3000
```

`DATABASE_URL` sale de Supabase → **Project Settings → Database → Connection
string → Session pooler**. La de *Direct connection* no funciona desde
serverless.

## Qué hay

| Ruta | Plantilla | Qué muestra |
|---|---|---|
| `/` | — | grupos y centros |
| `/estudios` | TPL-06 índice | los 47 estudios agrupados |
| `/estudios/{grupo}` | TPL-03 hub | los estudios de una categoría |
| `/estudios/{estudio}` | TPL-01 pilar | bloque de respuesta, dónde se hace, alias, estudios parecidos, revisor |
| `/centros` | — | los centros con sus barrios |
| `/centros/{centro}` | TPL-04 centro | sedes con dirección y qué estudios hace |
| `/sitemap.xml` `/robots.txt` | — | generados desde la base |

Un solo segmento `/estudios/[slug]` sirve al hub y al estudio: resuelve primero
grupo, después estudio. Las URLs quedan planas y el slug es único entre tipos,
que es el constraint que ya pide §2.2 del plan.

## Decisiones que conviene no revertir sin pensarlo

- **Postgres directo, no PostgREST.** Para generar páginas estáticas es más
  simple y permite SQL de verdad en vez de encadenar filtros. Esto **saltea
  RLS** porque usa el rol `postgres`: está bien para un directorio público de
  solo lectura, pero cualquier consulta desde el cliente tiene que ir por
  `supabase-js` con la anon key, que sí respeta las policies del `02`.
- **El control de índice es por `meta robots`, nunca por robots.txt.** Un
  estudio sin ningún centro sale `noindex, follow`: no aporta nada al buscador
  pero sí pasa autoridad a los que sí tienen. Está en `generateMetadata`.
- **`robots.txt` no bloquea nada del sitio.** Una URL bloqueada ahí se puede
  indexar igual y sus links salientes se vuelven invisibles.
- **El bloque de respuesta va primero y arranca con el dato duro.** Es lo que
  citan los LLM. Si `estudio.respuesta_breve` está vacío se arma solo con los
  centros y barrios reales.
- **Un centro con varias sedes es un `Organization` con `location` como arreglo
  de `MedicalClinic`.** No hace falta una página por sede para que Google
  entienda que hay varias direcciones.

## Lo que falta

- `estudio.respuesta_breve` está vacío en las 47 filas: hoy se genera solo. El
  texto escrito a mano rinde más y es lo que revisa el médico.
- No hay `revisor_medico` real cargado, así que el bloque de revisión no aparece
  y el `reviewedBy` del schema queda afuera.
- No hay coberturas cargadas, así que falta TPL-02 (estudio × cobertura), que es
  la página comercial principal del plan.
- Las sedes están en `borrador` sin dirección: hasta que se completen, los
  centros muestran «sin sedes publicadas».
