import './globals.css';
import { SITE } from '../lib/db';

export const metadata = {
  metadataBase: new URL(SITE),
  title: { default: 'Estudio', template: '%s | Estudio' },
  description: 'Dónde hacerte tu estudio médico, con qué cobertura y en qué barrio.',
};

export default function RootLayout({ children }) {
  return (
    <html lang="es-AR">
      <body>
        <header className="top">
          <a className="brand" href="/">Estudio</a>
          <nav>
            <a href="/estudios">Estudios</a>
            <a href="/centros">Centros</a>
          </nav>
        </header>
        <main>{children}</main>
        <footer className="pie">
          <p>La cobertura se verifica contra la cartilla oficial de cada obra social. Este sitio no reemplaza la consulta médica.</p>
        </footer>
      </body>
    </html>
  );
}
