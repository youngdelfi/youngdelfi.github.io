import { notFound } from 'next/navigation';
import { centroPorSlug, centrosPublicados } from '../../../lib/queries';
import { SITE } from '../../../lib/db';
import JsonLd from '../../jsonld';

export const revalidate = 3600;

export async function generateStaticParams() {
  const c = await centrosPublicados();
  return c.map(({ centro_slug }) => ({ slug: centro_slug }));
}

export async function generateMetadata({ params }) {
  const { slug } = await params;
  const c = await centroPorSlug(slug);
  if (!c) return {};
  const donde = c.barrios?.length ? ` en ${c.barrios.join(', ')}` : '';
  return {
    title: c.nombre_comercial,
    description: `${c.nombre_comercial}: ${c.estudios.length} estudios${donde}.`,
    alternates: { canonical: `/centros/${c.centro_slug}` },
  };
}

export default async function Centro({ params }) {
  const { slug } = await params;
  const c = await centroPorSlug(slug);
  if (!c) notFound();

  const porGrupo = c.estudios.reduce((acc, e) => {
    (acc[e.grupo || 'Otros'] ||= []).push(e);
    return acc;
  }, {});

  return (
    <>
      <p className="miga"><a href="/">Inicio</a> › <a href="/centros">Centros</a> › {c.nombre_comercial}</p>
      <h1>{c.nombre_comercial}</h1>

      <p className="respuesta">
        {c.nombre_comercial} tiene {c.n_sedes} {c.n_sedes === 1 ? 'sede' : 'sedes'}
        {c.barrios?.length > 0 && ` en ${c.barrios.join(', ')}`}
        {c.ciudades?.length > 1 && ` (${c.ciudades.join(', ')})`}
        {' '}y realiza {c.estudios.length} de los estudios del catálogo.
      </p>

      <h2>Sedes</h2>
      {c.sedes.length === 0 ? (
        <p className="vacio">Sin sedes publicadas todavía.</p>
      ) : (
        <ul className="tarjetas">
          {c.sedes.map((s) => (
            <li className="tarjeta" key={s.slug}>
              <h3>{s.nombre}</h3>
              {s.direccion && <p>{s.direccion}</p>}
              <p className="barrios">{[s.barrio, s.ciudad].filter(Boolean).join(', ')}</p>
              {s.telefono && <p>{s.telefono}</p>}
            </li>
          ))}
        </ul>
      )}

      <h2>Qué estudios hace</h2>
      {c.estudios.length === 0 ? (
        <p className="vacio">Todavía no hay estudios relevados para este centro.</p>
      ) : (
        Object.entries(porGrupo).map(([grupo, lista]) => (
          <section key={grupo}>
            <h3 style={{ marginTop: 20 }}>{grupo}</h3>
            <ul className="tarjetas">
              {lista.map((e) => (
                <li className="tarjeta" key={e.slug}>
                  <a href={`/estudios/${e.slug}`}>{e.nombre_canonico}</a>
                </li>
              ))}
            </ul>
          </section>
        ))
      )}

      <JsonLd data={schema(c)} />
    </>
  );
}

function schema(c) {
  return {
    '@context': 'https://schema.org',
    '@type': 'Organization',
    '@id': `${SITE}/centros/${c.centro_slug}#org`,
    name: c.nombre_comercial,
    url: `${SITE}/centros/${c.centro_slug}`,
    ...(c.sitio_web && { sameAs: [c.sitio_web] }),
    // Varias sedes = varios MedicalClinic dentro del mismo Organization.
    // No hace falta una pagina por sede para que Google entienda las direcciones.
    location: c.sedes.map((s) => ({
      '@type': 'MedicalClinic',
      name: `${c.nombre_comercial} ${s.nombre}`,
      ...(s.telefono && { telephone: s.telefono }),
      address: {
        '@type': 'PostalAddress',
        addressCountry: 'AR',
        ...(s.direccion && { streetAddress: s.direccion }),
        ...(s.barrio && { addressLocality: s.barrio }),
        ...(s.ciudad && { addressRegion: s.ciudad }),
      },
      ...(s.lat && s.lng && {
        geo: { '@type': 'GeoCoordinates', latitude: Number(s.lat), longitude: Number(s.lng) },
      }),
    })),
  };
}
