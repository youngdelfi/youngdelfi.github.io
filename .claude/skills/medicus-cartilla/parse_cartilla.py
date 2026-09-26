#!/usr/bin/env python3
"""
Parser de cartillas PDF de Medicus (formato "Diagnostico y Tratamiento").

Extrae instituciones (centros, no medicos individuales) agrupadas por
modalidad de estudio y zona geografica, a partir del layout posicional
del PDF (columnas fijas: nombre x<150, direccion 150<=x<300,
localidad 300<=x<420, telefono x>=420; encabezados en negrita en 3
niveles de tamaño: 14=seccion/zona, 10=categoria, 8=modalidad).

Uso:
    python3 parse_cartilla.py <pdf_path> <pid_prefix> <out_dir>

Genera en <out_dir>:
    <prefix>_p.sql   INSERT INTO _<prefix>_p (pid, nombre)
    <prefix>_s.sql   INSERT INTO _<prefix>_s (pid, direccion, loc)
    <prefix>_a.sql   INSERT INTO _<prefix>_a (pid, atributo_id, poblacion_id)
    <prefix>_entries.json   entradas limpias (modalidad, zona, nombre, direccion, localidad)
    <prefix>_summary.txt    resumen legible para revisar antes de cargar

No requiere Supabase ni red: solo pymupdf. El merge final a producción
se hace aparte (ver SKILL.md), corriendo el SQL generado + una
transaccion de merge.
"""
import sys
import re
import json
import unicodedata
from pathlib import Path

try:
    import pymupdf
except ImportError:
    print("Falta pymupdf. Instalar con: pip install pymupdf", file=sys.stderr)
    sys.exit(1)

SECTION_NAME = "DIAGNOSTICO Y TRATAMIENTO"

DOCTOR_RE = re.compile(r'^(DR\.|DRA\.|LIC\.)', re.I)
PERSON_RE = re.compile(r'^[A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\'\-\. ]+,\s*[A-ZÑÁÉÍÓÚ]')

MODMAP = {
    'DENSITOMETRIA OSEA': ('densitometria', 'general'),
    'ECOGRAFIA': ('ecografia', 'general'),
    'ECOGRAFIA INFANTIL': ('ecografia', 'infantil'),
    'MAMOGRAFIA': ('mamografia', 'general'),
    'RADIOLOGIA': ('radiologia', 'general'),
    'RADIOLOGIA INFANTIL': ('radiologia', 'infantil'),
    'RESONANCIA NUCLEAR MAGNETICA (R.N.M.)': ('resonancia', 'general'),
    'TOMOGRAFIA AXIAL COMPUTADA (T.A.C.)': ('tomografia', 'general'),
    'HEMODINAMIA': ('hemodinamia', 'general'),
    'ENDOSCOPIA DIGESTIVA': ('endoscopia', 'general'),
    'ELECTROCARDIOGRAMA': ('electrocardiograma', 'general'),
    'ELECTROENCEFALOGRAMA': ('electroencefalograma', 'general'),
    'HOLTER': ('holter-ritmo', 'general'),
}


def is_doctor(name: str) -> bool:
    return bool(DOCTOR_RE.match(name) or PERSON_RE.match(name))


def norm(s: str) -> str:
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return s.lower()


def slug(s: str, maxlen: int = 35) -> str:
    s = norm(s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:maxlen]


def extract_rows(pdf_path: str):
    """Recorre todo el PDF y devuelve filas con su contexto jerarquico:
    (pagina, seccion, zona, categoria, modalidad, nombre, direccion, localidad, telefono)
    """
    doc = pymupdf.open(pdf_path)
    records = []
    top_section = None
    zone = None
    category = None
    modality = None

    for pno in range(len(doc)):
        page = doc[pno]
        d = page.get_text("dict")
        rows = {}
        headers = []
        for b in d["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b.get("lines", []):
                for s in l["spans"]:
                    y = round(s["origin"][1], 0)
                    x = s["origin"][0]
                    text = s["text"]
                    bold = 'Bold' in s["font"]
                    stripped = text.strip()
                    if stripped == 'CARTILLA AZUL' or stripped.startswith('Página') \
                            or re.match(r'^\d\d/\d\d/\d\d\d\d$', stripped) \
                            or re.match(r'^CARTILLA\s', stripped, re.I):
                        continue
                    if bold:
                        headers.append((y, s["size"], stripped))
                        continue
                    rows.setdefault(y, []).append((x, text))

        # nivel 1 (size>=13): seccion / zona, corre para toda la pagina
        l1 = [h for h in headers if h[1] >= 13]
        prev_section = top_section
        for (y, size, text) in l1:
            if 'ZONA' in text or text == 'CAPITAL FEDERAL':
                zone = text
            else:
                top_section = text
        if top_section != prev_section:
            category = None
            modality = None

        # niveles 2/3 (size<13): categoria (>=9.5) / modalidad (<9.5), secuenciales
        l23 = sorted([h for h in headers if h[1] < 13], key=lambda t: -t[0])
        ys = sorted(rows.keys(), reverse=True)
        hidx = 0

        def apply_header(size, text):
            nonlocal category, modality
            if size >= 9.5:
                category = text
            else:
                modality = text

        for y in ys:
            while hidx < len(l23) and l23[hidx][0] > y:
                _, size, text = l23[hidx]
                apply_header(size, text)
                hidx += 1
            cols = sorted(rows[y], key=lambda t: t[0])
            name = addr = loc = phone = ''
            for x, text in cols:
                if x < 150:
                    name += text
                elif x < 300:
                    addr += text
                elif x < 420:
                    loc += text
                else:
                    phone += text
            name, addr, loc, phone = name.strip(), addr.strip(), loc.strip(), phone.strip()
            if not (name or addr or loc or phone):
                continue
            records.append((pno + 1, top_section, zone, category, modality, name, addr, loc, phone))
        while hidx < len(l23):
            _, size, text = l23[hidx]
            apply_header(size, text)
            hidx += 1

    return records


def merge_entries(records, section_name=SECTION_NAME):
    """Reconstruye instituciones+direcciones a partir de las filas crudas,
    resolviendo nombres/direcciones partidos en dos lineas y descartando
    fragmentos ambiguos (direcciones sin localidad tipo 'PILAR 26474')."""
    sub = [r for r in records if r[1] == section_name]

    pending_suffix = None
    current_institution = None
    last_zone = None
    last_modality = None
    entries = []
    for (page, section, zone, category, modality, name, addr, loc, phone) in sub:
        if zone != last_zone or modality != last_modality:
            pending_suffix = None
            current_institution = None
            last_zone = zone
            last_modality = modality
        if name and not addr and not loc:
            # linea de continuacion de nombre (se imprime ARRIBA de la fila base)
            pending_suffix = name.strip()
            continue
        if name:
            full_name = name.strip()
            if pending_suffix:
                full_name = full_name + ' ' + pending_suffix
                pending_suffix = None
            if is_doctor(full_name):
                current_institution = None
                continue
            current_institution = full_name
            if addr or loc:
                entries.append((modality, zone, full_name, addr, loc))
        else:
            if addr or loc:
                if loc.strip():
                    if current_institution:
                        entries.append((modality, zone, current_institution, addr, loc))
                # si loc esta vacio es un fragmento de direccion ambiguo
                # (wrap de 2 lineas mal resuelto) -> se descarta, no se
                # adivina a que institucion pertenece.
            pending_suffix = None

    return entries


def build_sql(entries, prefix):
    names = sorted(set(e[2] for e in entries))
    name2pid = {}
    seen = {}
    for n in names:
        p = f'{prefix}-' + slug(n)
        if p in seen:
            i = 2
            newp = p + str(i)
            while newp in seen:
                i += 1
                newp = p + str(i)
            p = newp
        seen[p] = n
        name2pid[n] = p

    sedes = set()
    attrs = set()
    for (mod, zone, name, addr, loc) in entries:
        pid = name2pid[name]
        sedes.add((pid, addr.strip(), loc.strip()))
        if mod in MODMAP:
            atr, pobl = MODMAP[mod]
            attrs.add((pid, atr, pobl))

    def esc(s):
        return s.replace("'", "''")

    p_sql = "INSERT INTO _%s_p (pid, nombre) VALUES\n" % prefix
    p_sql += ",\n".join(f"('{pid}','{esc(name)}')" for name, pid in name2pid.items()) + ";\n"

    s_sql = "INSERT INTO _%s_s (pid, direccion, loc) VALUES\n" % prefix
    s_sql += ",\n".join(f"('{pid}','{esc(a)}','{esc(l)}')" for pid, a, l in sedes) + ";\n"

    a_sql = "INSERT INTO _%s_a (pid, atributo_id, poblacion_id) VALUES\n" % prefix
    a_sql += ",\n".join(f"('{pid}','{atr}','{pobl}')" for pid, atr, pobl in attrs) + ";\n"

    return p_sql, s_sql, a_sql, name2pid


def main():
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    pdf_path, prefix, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    print(f"Extrayendo texto posicional de {pdf_path} ...")
    records = extract_rows(pdf_path)
    print(f"  {len(records)} filas crudas")

    entries = merge_entries(records)
    print(f"  {len(entries)} entradas limpias (institucion, direccion)")

    p_sql, s_sql, a_sql, name2pid = build_sql(entries, prefix)
    (out / f"{prefix}_p.sql").write_text(p_sql, encoding='utf-8')
    (out / f"{prefix}_s.sql").write_text(s_sql, encoding='utf-8')
    (out / f"{prefix}_a.sql").write_text(a_sql, encoding='utf-8')
    (out / f"{prefix}_entries.json").write_text(json.dumps(entries, ensure_ascii=False, indent=None), encoding='utf-8')

    by_mod = {}
    for (mod, zone, name, addr, loc) in entries:
        by_mod.setdefault(mod or "SIN MODALIDAD ESPECIFICA", {}).setdefault(name, set()).add(f"{addr} - {loc} [{zone}]")
    lines = [f"Instituciones: {len(name2pid)}", ""]
    for mod in sorted(by_mod.keys()):
        insts = by_mod[mod]
        lines.append(f"## {mod} ({len(insts)} instituciones)")
        for name in sorted(insts.keys()):
            lines.append(f"- {name}")
            for a in sorted(insts[name]):
                lines.append(f"    {a}")
        lines.append("")
    (out / f"{prefix}_summary.txt").write_text("\n".join(lines), encoding='utf-8')

    print(f"OK. {len(name2pid)} instituciones. Archivos en {out_dir}/{prefix}_*.sql")
    print(f"Revisar {out_dir}/{prefix}_summary.txt antes de cargar.")


if __name__ == '__main__':
    main()
