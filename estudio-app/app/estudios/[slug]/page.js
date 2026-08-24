import { notFound } from 'next/navigation';
import { estudioPorSlug, estudiosPublicados, grupoPorSlug, gruposConEstudios } from '../../../lib/queries';
import { SITE } from '../../../lib/db';
import JsonLd from '../../jsonld';

export const revalidate = 3600;
export const dynamicParams = true;

// Un solo segmento sirve a las dos plantillas: TPL-03 hub de grupo y TPL-01
// estudio pilar. Las URLs quedan planas y el slug es unico entre tipos, que es
// justo el constraint que pide §2.2.
export async function generateStaticParams() {
  const [estudios, grupos] = await Promise.all([estudiosPublicados(), gruposConEstudios()]);
  return [...grupos, ...estudios].map(({ slug }) => ({ slug }));
}

export async function generateMetadata({ params }) {
  const { slug } = await params;
  const g = await grupoPorSlug(slug);
  if (g) return {
    title: g.nombre,
    description: `${g.estudios.length} estudios de ${g.nombre.toLowerCase()}: dónde se hacen y cómo figuran en la orden.`,
    alternates: { canonical: `/estudios/${g.slug}` },
  };
  const e = await estudioPorSlug(slug);
  if (!e) return {};
  return {
    title: e.nombre_canonico,
    description: e.respuesta_breve || `Dónde hacerse ${e.nombre_canonico}: centros, barrios y cobertura.`,
    alternates: { canonical: `/estudios/${e.slug}` },
    // §5.3: el control de indice es por meta robots, nunca por robots.txt.
    robots: e.centros.length > 0 ? { index: true, follow: true } : { index: false, follow: true },
  };
}

export default async function Estudio({ params }) {
  const { slug } = await params;
  const grupo = await grupoPorSlug(slug);
  if (grupo) return <Hub g={grupo} />;
  const e = await estudioPorSlug(slug);
  if (!e) notFound();

  const siglas = e.sinonimos.filter((s) => s.tipo === 'sigla').map((s) => s.termino);
  const respuesta = e.respuesta_breve || bloqueDeRespuesta(e, siglas);

  return (
    <>
      <p className="miga">
        <a href="/">Inicio</a> › <a href="/estudios">Estudios</a>
        {e.grupo && <> › <a href={`/estudios/${e.grupo_slug}`}>{e.grupo}</a></>} › {e.nombre_canonico}
      </p>

      <h1>{e.nombre_canonico}</h1>
      {siglas.length > 0 && <p className="barrios">También: {siglas.join(', ')}</p>}

      {/* Bloque de respuesta: 40-60 palabras, con el dato duro adelante. Es lo que citan los LLM. */}
      <p className="respuesta">{respuesta}</p>

      <h2>Dónde se hace</h2>
      {e.centros.length === 0 ? (
        <p className="vacio">Todavía no hay ningún centro relevado que lo realice.</p>
      ) : (
        <ul className="tarjetas">
          {e.centros.map((c) => (
            <li className="tarjeta" key={c.centro_slug}>
              <a href={`/centros/${c.centro_slug}`}>{c.nombre_comercial}</a>
              <p>{c.n_sedes} {c.n_sedes === 1 ? 'sede' : 'sedes'}</p>
              {c.barrios?.length > 0 && <p className="barrios">{c.barrios.join(' · ')}</p>}
            </li>
          ))}
        </ul>
      )}

      {e.sinonimos.length > 0 && (
        <>
          <h2>Cómo puede figurar en tu orden</h2>
          <ul className="alias">
            {e.sinonimos.map((s, i) => <li key={i}>{s.termino}</li>)}
          </ul>
        </>
      )}

      {e.hermanos.length > 0 && (
        <>
          <h2>Estudios parecidos, que no son el mismo</h2>
          <ul className="tarjetas">
            {e.hermanos.map((h) => (
              <li className="tarjeta" key={h.slug}>
                <a href={`/estudios/${h.slug}`}>{h.nombre_canonico}</a>
              </li>
            ))}
          </ul>
        </>
      )}

      {e.revisor && (
        <p className="revision">
          Revisado por <b>{e.revisor}</b>
          {e.especialidad && `, ${e.especialidad}`}
          {e.matricula_numero && ` (${e.matricula_tipo} ${e.matricula_numero})`}
          {e.validado_at && ` · ${new Date(e.validado_at).toLocaleDateString('es-AR')}`}
        </p>
      )}

      <JsonLd data={schema(e, respuesta)} />
    </>
  );
}

/** Si no hay respuesta_breve cargada, se arma una con los datos que si hay. */
function bloqueDeRespuesta(e, siglas) {
  const n = e.centros.length;
  const barrios = [...new Set(e.centros.flatMap((c) => c.barrios || []))];
  const partes = [
    `${e.nombre_canonico}${siglas.length ? ` (${siglas.join(', ')})` : ''} se realiza en ` +
      `${n} ${n === 1 ? 'centro relevado' : 'centros relevados'}`,
  ];
  if (barrios.length) partes.push(`, en ${barrios.slice(0, 4).join(', ')}`);
  return partes.join('') + '.';
}

function schema(e, respuesta) {
  const grafo = [
    {
      '@type': 'MedicalWebPage',
      '@id': `${SITE}/estudios/${e.slug}#page`,
      url: `${SITE}/estudios/${e.slug}`,
      name: e.nombre_canonico,
      description: respuesta,
      inLanguage: 'es-AR',
      ...(e.contenido_cambiado_at && { lastReviewed: fecha(e.contenido_cambiado_at) }),
      ...(e.revisor && {
        reviewedBy: {
          '@type': 'Physician',
          name: e.revisor,
          ...(e.especialidad && { medicalSpecialty: e.especialidad }),
          ...(e.perfil_externo && { sameAs: e.perfil_externo }),
        },
      }),
      mainEntity: { '@id': `${SITE}/estudios/${e.slug}#test` },
    },
    {
      '@type': 'MedicalTest',
      '@id': `${SITE}/estudios/${e.slug}#test`,
      name: e.nombre_canonico,
      alternateName: e.sinonimos.map((s) => s.termino),
      ...(e.codigo_nomenclador && { code: { '@type': 'MedicalCode', codeValue: e.codigo_nomenclador } }),
      availableService: e.centros.map((c) => ({
        '@type': 'MedicalClinic',
        name: c.nombre_comercial,
        url: `${SITE}/centros/${c.centro_slug}`,
      })),
    },
    {
      '@type': 'BreadcrumbList',
      itemListElement: [
        { '@type': 'ListItem', position: 1, name: 'Inicio', item: SITE },
        { '@type': 'ListItem', position: 2, name: 'Estudios', item: `${SITE}/estudios` },
        { '@type': 'ListItem', position: 3, name: e.nombre_canonico },
      ],
    },
  ];
  return { '@context': 'https://schema.org', '@graph': grafo };
}

const fecha = (d) => new Date(d).toISOString().slice(0, 10);

/** TPL-03 · hub de grupo. */
function Hub({ g }) {
  const conCentro = g.estudios.filter((e) => e.n_centros > 0).length;
  return (
    <>
      <p className="miga"><a href="/">Inicio</a> › <a href="/estudios">Estudios</a> › {g.nombre}</p>
      <h1>{g.nombre}</h1>
      <p className="respuesta">
        {g.estudios.length} estudios en esta categoría, {conCentro} con al menos un centro
        que los realiza. Buscá el nombre tal como figura en tu orden.
      </p>
      <ul className="tarjetas">
        {g.estudios.map((e) => (
          <li className="tarjeta" key={e.slug}>
            <a href={`/estudios/${e.slug}`}>{e.nombre_canonico}</a>
            <p>{e.n_centros === 0 ? 'sin centro relevado' :
                `${e.n_centros} ${e.n_centros === 1 ? 'centro' : 'centros'}`}</p>
          </li>
        ))}
      </ul>
      <JsonLd data={{
        '@context': 'https://schema.org',
        '@type': 'CollectionPage',
        name: g.nombre,
        url: `${SITE}/estudios/${g.slug}`,
        hasPart: g.estudios.map((e) => ({
          '@type': 'MedicalTest', name: e.nombre_canonico, url: `${SITE}/estudios/${e.slug}`,
        })),
      }} />
    </>
  );
}
