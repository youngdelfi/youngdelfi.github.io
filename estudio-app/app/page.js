import { gruposConEstudios, centrosPublicados } from '../lib/queries';

export const revalidate = 3600;

export default async function Home() {
  const [grupos, centros] = await Promise.all([gruposConEstudios(), centrosPublicados()]);
  const total = grupos.reduce((a, g) => a + g.n, 0);

  return (
    <>
      <h1>Dónde hacerte tu estudio</h1>
      <p className="respuesta">
        Buscá el estudio tal como figura en tu orden médica y mirá en qué centros se hace
        y en qué barrios están. Hoy hay {total} estudios de {centros.length} centros.
      </p>

      <h2>Por tipo de estudio</h2>
      <ul className="tarjetas">
        {grupos.map((g) => (
          <li className="tarjeta" key={g.slug}>
            <a href={`/estudios/${g.slug}`}>{g.nombre}</a>
            <p>{g.n} {g.n === 1 ? 'estudio' : 'estudios'}</p>
          </li>
        ))}
      </ul>

      <h2>Centros</h2>
      <ul className="tarjetas">
        {centros.map((c) => (
          <li className="tarjeta" key={c.centro_slug}>
            <a href={`/centros/${c.centro_slug}`}>{c.nombre_comercial}</a>
            <p>{c.n_sedes} {c.n_sedes === 1 ? 'sede' : 'sedes'}</p>
            {c.barrios?.length > 0 && <p className="barrios">{c.barrios.join(' · ')}</p>}
          </li>
        ))}
      </ul>
    </>
  );
}
