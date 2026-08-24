import { SITE } from '../lib/db';

// §5.4: robots.txt NO controla la indexacion. Una URL bloqueada aca puede
// indexarse igual, y sus links salientes se vuelven invisibles. El control de
// indice es por meta robots, en generateMetadata de cada plantilla.
export default function robots() {
  return {
    rules: [{ userAgent: '*', allow: '/', disallow: ['/api/', '/_next/'] }],
    sitemap: `${SITE}/sitemap.xml`,
  };
}
