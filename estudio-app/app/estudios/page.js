import { estudiosPublicados } from '../../lib/queries';

export const revalidate = 3600;
export const metadata = {
  title: 'Todos los estudios',
  description: 'El catálogo completo de estudios, agrupados por tipo.',
};

export default async function Indice() {
  const estudios = await estudiosPublicados();
  const porGrupo = estudios.reduce((acc, e) => {
    const k = e.grupo || 'Otros';
    (acc[k] ||= []).push(e);
    return acc;
  }, {});

  return (
    <>
      <p className="miga"><a href="/">Inicio</a> › Estudios</p>
      <h1>Todos los estudios</h1>
      <p className="respuesta">
        {estudios.length} estudios en el catálogo. Si el nombre de tu orden no aparece acá,
        puede estar cargado como sinónimo: buscalo igual.
      </p>
      {Object.entries(porGrupo).map(([grupo, lista]) => (
        <section key={grupo}>
          <h2>{grupo}</h2>
          <ul className="tarjetas">
            {lista.map((e) => (
              <li className="tarjeta" key={e.slug}>
                <a href={`/estudios/${e.slug}`}>{e.nombre_canonico}</a>
              </li>
            ))}
          </ul>
        </section>
      ))}
    </>
  );
}
