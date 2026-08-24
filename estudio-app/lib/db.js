import postgres from 'postgres';

// Conexion directa a Postgres, no PostgREST. Para generar paginas estaticas es
// mas simple y mas rapido, y deja escribir SQL de verdad en vez de encadenar
// filtros. La anon key + RLS siguen siendo el camino para consultas del cliente.
const url = process.env.DATABASE_URL;
if (!url) throw new Error('Falta DATABASE_URL. Copiá .env.example a .env y completalo.');

// Supabase exige TLS; un Postgres local de desarrollo normalmente no lo tiene.
const esLocal = /@(localhost|127\.0\.0\.1|\[::1\])[:/]/.test(url);

const sql = postgres(url, {
  ssl: esLocal ? false : 'require',
  max: 4,
  idle_timeout: 20,
  transform: { undefined: null },
});

export default sql;

export const SITE = process.env.SITE_URL || 'https://estudio.com.ar';
