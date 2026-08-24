import { centrosPublicados } from '../../lib/queries';

export const revalidate = 3600;
export const metadata = { title: 'Centros', description: 'Los centros de diagnóstico del catálogo y sus barrios.' };

export default async function Centros() {
  const centros = await centrosPublicados();
  return (
    <>
      <p className="miga"><a href="/">Inicio</a> › Centros</p>
      <h1>Centros</h1>
      <p className="respuesta">{centros.length} centros relevados. Cada uno puede tener varias sedes; abajo están los barrios donde atiende.</p>
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
