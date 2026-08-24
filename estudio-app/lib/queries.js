import sql from './db';

/** Todos los estudios publicados. Alimenta generateStaticParams y el indice. */
export async function estudiosPublicados() {
  return sql`
    select e.id, e.slug, e.nombre_canonico, g.slug as grupo_slug, g.nombre as grupo
    from estudio e
    left join estudio_grupo eg on eg.estudio_id = e.id and eg.es_principal
    left join grupo g on g.id = eg.grupo_id
    where e.estado = 'publicado'
    order by g.orden nulls last, e.nombre_canonico`;
}

/** Un estudio con todo lo que la plantilla TPL-01 necesita. */
export async function estudioPorSlug(slug) {
  const [estudio] = await sql`
    select e.id, e.slug, e.nombre_canonico, e.respuesta_breve, e.codigo_nomenclador,
           e.validado_at, e.contenido_cambiado_at,
           g.slug as grupo_slug, g.nombre as grupo,
           r.nombre_completo as revisor, r.matricula_tipo, r.matricula_numero,
           r.especialidad, r.perfil_externo
    from estudio e
    left join estudio_grupo eg on eg.estudio_id = e.id and eg.es_principal
    left join grupo g on g.id = eg.grupo_id
    left join revisor_medico r on r.id = e.validado_por
    where e.slug = ${slug} and e.estado = 'publicado'`;
  if (!estudio) return null;

  const [sinonimos, centros, hermanos] = await Promise.all([
    sql`select termino, tipo from estudio_sinonimo
        where estudio_id = ${estudio.id} and tipo <> 'canonico'
        order by (tipo = 'sigla') desc, length(termino), termino`,
    sql`select centro_id, centro_slug, nombre_comercial, n_sedes, barrios
        from estudio_disponible where estudio_id = ${estudio.id}
        order by n_sedes desc, nombre_comercial`,
    sql`select e.slug, e.nombre_canonico from estudio e
        join estudio_grupo eg on eg.estudio_id = e.id and eg.es_principal
        join grupo g on g.id = eg.grupo_id
        where g.slug = ${estudio.grupo_slug} and e.slug <> ${slug} and e.estado = 'publicado'
        order by e.nombre_canonico`,
  ]);
  return { ...estudio, sinonimos, centros, hermanos };
}

/** Un centro con sus sedes. TPL-04. */
export async function centroPorSlug(slug) {
  const [centro] = await sql`
    select centro_id, centro_slug, nombre_comercial, sitio_web, n_sedes, barrios, ciudades
    from centro_publico where centro_slug = ${slug}`;
  if (!centro) return null;
  const [sedes, estudios] = await Promise.all([
    sql`select s.slug, s.nombre, s.direccion, s.telefono, s.lat, s.lng,
               b.nombre as barrio, ci.nombre as ciudad
        from sede s
        left join barrio b on b.id = s.barrio_id
        left join ciudad ci on ci.id = s.ciudad_id
        where s.centro_id = ${centro.centro_id} and s.estado = 'publicado'
        order by s.es_principal desc, s.nombre`,
    sql`select e.slug, e.nombre_canonico, g.nombre as grupo
        from centro_estudio ce
        join estudio e on e.id = ce.estudio_id and e.estado = 'publicado'
        left join estudio_grupo eg on eg.estudio_id = e.id and eg.es_principal
        left join grupo g on g.id = eg.grupo_id
        where ce.centro_id = ${centro.centro_id} and ce.activo
        order by g.orden nulls last, e.nombre_canonico`,
  ]);
  return { ...centro, sedes, estudios };
}

export async function centrosPublicados() {
  return sql`select centro_slug, nombre_comercial, n_sedes, barrios from centro_publico
             order by n_sedes desc, nombre_comercial`;
}

/** Los grupos con su cuenta, para el indice TPL-06. */
export async function gruposConEstudios() {
  return sql`
    select g.slug, g.nombre, g.orden, count(e.id)::int as n
    from grupo g
    join estudio_grupo eg on eg.grupo_id = g.id
    join estudio e on e.id = eg.estudio_id and e.estado = 'publicado'
    where g.estado = 'publicado'
    group by g.slug, g.nombre, g.orden
    order by g.orden`;
}

/** Un grupo con sus estudios. Es la capa de hub de §2.2: sin ella las paginas
 *  de estudio cuelgan directo de la home y se pasa el limite de links utiles. */
export async function grupoPorSlug(slug) {
  const [grupo] = await sql`
    select id, slug, nombre from grupo where slug = ${slug} and estado = 'publicado'`;
  if (!grupo) return null;
  const estudios = await sql`
    select e.slug, e.nombre_canonico,
           coalesce((select count(*) from centro_estudio ce
                     where ce.estudio_id = e.id and ce.activo), 0)::int as n_centros
    from estudio e
    join estudio_grupo eg on eg.estudio_id = e.id and eg.grupo_id = ${grupo.id}
    where e.estado = 'publicado'
    order by n_centros desc, e.nombre_canonico`;
  return { ...grupo, estudios };
}
