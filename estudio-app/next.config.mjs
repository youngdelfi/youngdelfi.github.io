/** @type {import('next').NextConfig} */
export default {
  // Cada pagina se regenera sola cuando cambia el dato, sin rebuildear las otras.
  experimental: { staleTimes: { dynamic: 30 } },
};
