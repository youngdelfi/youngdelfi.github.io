import { estudiosPublicados, centrosPublicados, gruposConEstudios } from '../lib/queries';
import { SITE } from '../lib/db';

// §5.5: el sitemap se segmenta por plantilla para poder diagnosticar la
// indexacion de cada tipo de pagina por separado en Search Console.
export default async function sitemap() {
  const [estudios, centros, grupos] = await Promise.all([
    estudiosPublicados(), centrosPublicados(), gruposConEstudios(),
  ]);
  return [
    { url: SITE, changeFrequency: 'weekly', priority: 1 },
    { url: `${SITE}/estudios`, changeFrequency: 'weekly', priority: 0.9 },
    { url: `${SITE}/centros`, changeFrequency: 'weekly', priority: 0.9 },
    ...grupos.map((g) => ({ url: `${SITE}/estudios/${g.slug}`, priority: 0.8 })),
    ...estudios.map((e) => ({ url: `${SITE}/estudios/${e.slug}`, priority: 0.7 })),
    ...centros.map((c) => ({ url: `${SITE}/centros/${c.centro_slug}`, priority: 0.6 })),
  ];
}
