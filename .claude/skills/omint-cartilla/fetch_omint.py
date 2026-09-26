#!/usr/bin/env python3
"""
Descarga masiva de prestadores de Omint (cartilla publica, seccion "Estudios
de Diagnostico y Tratamiento") via la API real que usa la SPA de
autogestion.omint.com.ar, para CABA + GBA (Norte/Oeste/Sur).

Hallazgos clave (no obvios):

1. El frontend (autogestion.omint.com.ar) es una SPA que pega contra un
   backend en OTRO dominio: https://ws.grupo-omint.com.ar/ws-pad/api/v0/
   OpenMedicalDirectory/*. Pegarle directo a autogestion.omint.com.ar/api/...
   da 404 (ese host solo sirve el bundle de la SPA).
2. El endpoint /search responde 200 con `results: []` (pero `totalRows`
   correcto) si no se mandan los headers `Origin` y `Referer` imitando el
   sitio real. Sin esos headers parece "funcionar" pero no trae nada.
3. CADA PLAN TIENE SU PROPIA TAXONOMIA de secciones/especialidades: el id de
   la seccion "Estudios de Diagnostico y Tratamiento" es "W" para el plan 7
   pero "ED" para el plan XN (varia por plan). Por eso no se puede asumir un
   set fijo de `idEspecialidad` para todos los planes: hay que pedir
   `FilterSectionSpeciality?plan=<code>` por cada plan y buscar la seccion
   por NOMBRE ("Estudios de Diagnostico y Tratamiento"), no por id.
   El codigo numerico despues del guion bajo (ej. "63.00" en "W_63.00" /
   "ED_63.00") SI es estable entre planes (mismo catalogo de especialidades
   subyacente) — el mapeo a nuestro esquema (`ESPECIALIDAD_MAP`) se hace por
   ese codigo numerico, no por el id completo con prefijo de plan.
4. Los resultados de esta seccion son todos centros/instituciones (no
   medicos individuales): la separacion segun/institucion ya la hace Omint
   con secciones distintas (P/CM = consultorios de profesionales, W/ED =
   diagnostico y tratamiento). A diferencia de Medife, ACA NO HAY QUE
   FILTRAR POR COMA: los nombres de instituciones vienen en minuscula/
   capitalizados normales y algunos consultorios compartidos por varios
   socios usan coma en el nombre real (ej. "Consultorio Oftalmologico Dres.
   Donato, Oliveri y Rainaudi") — filtrarlos por coma los descarta por
   error. No se aplica ningun filtro de médico acá.

Uso:
    python3 fetch_omint.py <out_dir>

Genera en <out_dir>:
    omint_raw.json                  lista cruda de registros
    omint_p.sql / _s.sql / _a.sql / _cob.sql   SQL de staging
    omint_summary.txt               resumen por especialidad
"""
import sys
import re
import json
import time
import unicodedata
import urllib.request
import urllib.parse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://ws.grupo-omint.com.ar/ws-pad/api/v0/OpenMedicalDirectory"
HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json",
    "Origin": "https://autogestion.omint.com.ar",
    "Referer": "https://autogestion.omint.com.ar/cartilla/publica/L/mis-resultados",
}

# CABA + GBA (Norte/Oeste/Sur) — mismo alcance de "area metropolitana" usado
# para Medicus/Medife. "B_B" (Buenos Aires, resto de la provincia) queda
# fuera a proposito, igual que se decidio para Medife.
UBICACIONES = ["C", "B_BN", "B_BO", "B_BS"]

DIAG_SECTION_NAME = "Estudios de Diagnóstico y Tratamiento"

# mapeo por CODIGO NUMERICO de especialidad (estable entre planes, ver nota 3
# arriba) -> (atributo_id, poblacion_id) en nuestro esquema. Especialidades
# sin equivalente claro (estimulacion temprana, rehabilitacion, etc.) se
# omiten a proposito (el prestador/sede igual se carga, solo no llevan
# prestador_atributo).
ESPECIALIDAD_MAP = {
    "11.00": ("anatomia-patologica", "general"),
    "11.01": ("anatomia-patologica", "general"),
    "11.02": ("anatomia-patologica", "general"),
    "11.03": ("anatomia-patologica", "general"),
    "11.04": ("anatomia-patologica", "general"),
    "11.05": ("anatomia-patologica", "general"),
    "63.00": ("densitometria", "general"),
    "13.08": ("ecocardiograma", "general"),
    "13.02": ("ecocardiograma", "infantil"),
    "17.02": ("ecodoppler", "general"),
    "17.01": ("ecodoppler", "general"),
    "17.03": ("ecodoppler", "general"),
    "17.00": ("ecografia", "general"),
    "23.03": ("ecografia", "general"),
    "36.02": ("ecografia", "general"),
    "42.02": ("ecografia", "infantil"),
    "52.03": ("ecografia", "general"),
    "13.03": ("electrocardiograma", "general"),
    "13.05": ("electrocardiograma", "infantil"),
    "32.02": ("endoscopia", "general"),
    "21.02": ("endoscopia", "general"),
    "21.04": ("endoscopia", "infantil"),
    "41.01": ("endoscopia", "general"),
    "52.05": ("endoscopia", "general"),
    "13.04": ("ergometria", "general"),
    "21.03": ("espirometria", "general"),
    "13.06": ("hemodinamia", "general"),
    "13.10": ("hemodinamia", "infantil"),
    "13.07": ("holter-ritmo", "general"),
    "13.11": ("holter-presion", "general"),
    "28.00": ("laboratorio", "general"),
    "29.00": ("medicina-nuclear", "general"),
    "36.04": ("monitoreo-fetal", "general"),
    "34.02": ("electroencefalograma", "general"),
    "34.03": ("electroencefalograma", "infantil"),
    "38.02": ("potenciales-evocados", "general"),
    "41.02": ("audiometria", "general"),
    "46.00": ("radiologia", "general"),
    "46.05": ("radiologia-intervencionista", "general"),
    "46.02": ("mamografia", "general"),
    "46.01": ("radiologia", "infantil"),
    "48.00": ("resonancia", "general"),
    "32.03": ("espirometria", "general"),
    "50.00": ("tomografia", "general"),
    "52.04": ("urodinamia", "general"),
}



def http_get_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read()
            return json.loads(body)
        except Exception as e:
            print(f"attempt {attempt+1}/{retries} failed for {url}: {e}", file=sys.stderr)
            if attempt == retries - 1:
                return None
            time.sleep(1.0 * (attempt + 1))


def get_plans():
    data = http_get_json(f"{BASE}/plans")
    return [(d["code"], d["name"]) for d in data]


def get_diag_specialties(plan_code):
    """Devuelve [(idEspecialidad, codigo_numerico, nombre), ...] de la
    seccion "Estudios de Diagnostico y Tratamiento" para este plan
    (el id de seccion varia por plan, se busca por nombre)."""
    url = f"{BASE}/FilterSectionSpeciality?plan={urllib.parse.quote(plan_code)}"
    data = http_get_json(url)
    if not data:
        return []
    for section in data.get("sections", []):
        if section.get("name", "").strip() == DIAG_SECTION_NAME:
            out = []
            for sp in section.get("specialities", []):
                sid = sp["id"]
                codigo = sid.split("_", 1)[1] if "_" in sid else sid
                out.append((sid, codigo, sp["name"]))
            return out
    return []


INCOMPLETE = []


def fetch_combo(plan_code, esp_id, ubicacion):
    out = []
    pagina = 0
    cantidad = 80
    while True:
        url = (f"{BASE}/search?idEspecialidad={urllib.parse.quote(esp_id)}"
               f"&plan={urllib.parse.quote(plan_code)}&idProvincia={urllib.parse.quote(ubicacion)}"
               f"&pagina={pagina}&cantidad={cantidad}")
        data = http_get_json(url, retries=3)
        if data is None:
            INCOMPLETE.append((plan_code, esp_id, ubicacion, pagina))
            break
        results = data.get("results", [])
        out.extend(results)
        total = data.get("totalRows", 0)
        if (pagina + 1) * cantidad >= total or not results:
            break
        pagina += 1
    return out


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return s.lower()


def slug(s, maxlen=35):
    s = norm(s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:maxlen]


# Palabras que indican institucion (ver SKILL.md, hallazgo 4): la seccion de
# diagnostico y tratamiento de Omint mezcla medicos individuales (formato
# "Apellido Nombre", sin coma, indistinguible por patron simple) con centros
# reales. Cualquier nombre de 2-4 palabras SIN alguna de estas keywords se
# descarta por defecto (bucket "dudoso") en vez de cargarse como institucion.
KW_WORDS = ['centro', 'centros', 'instituto', 'institutos', 'laboratorio', 'laboratorios',
            'clinica', 'sanatorio', 'consultorio', 'consultorios', 'fundacion', 'grupo',
            'diagnostico', 'diagnostica', 'ecografia', 'ecografico', 'radiologia', 'radiologico',
            'imagenes', 'imagen', 'tomografia', 'resonancia', 'cardiovascular',
            'gastroenterologia', 'oftalmologico', 'oftalmologia', 'cardiologico', 'cardiologia',
            'servicio', 'servicios', 'unidad', 'srl', 'sa', 'hospital', 'policlinica', 'sistema',
            'centralab', 'gedyt', 'gedave', 'varelab', 'stamboulian', 'cedine', 'cinme',
            'biorossi', 'maiba', 'genos', 'paideia', 'infans', 'baimed', 'uroserver',
            'multidiagnostico', 'bioimagenes', 'osen', 'tcba', 'ceac', 'majestic', 'health',
            'dres', 'dr', 'dra', 'atencion', 'vision', 'ojos', 'ipc', 'iama', 'cid', 'dim',
            'cemi', 'cemedic', 'cepem', 'ineba', 'fleni', 'iamed', 'kinet', 'kinest',
            'oncologico', 'odontologico', 'odontologica', 'traumatologia', 'urologico',
            'neurologia', 'equipo', 'sr']

_WORD_RE = re.compile(r'[a-z]+')


def is_institution(name):
    """True si el nombre parece institucion (ver KW_WORDS arriba). False =
    bucket 'dudoso', se excluye de la carga por defecto (posible medico
    individual)."""
    u = norm(name)
    words = set(_WORD_RE.findall(u))
    if words & set(KW_WORDS):
        return True
    if re.search(r'\d', name):
        return True
    if name.replace('.', '').replace(' ', '').isupper() and len(name) <= 14:
        return True  # sigla tipo IAMA, INEBA, CEDINE
    nwords = name.split()
    if len(nwords) >= 5:
        return True
    return False


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)

    plans = get_plans()
    print(f"{len(plans)} planes: {plans}")

    plan_specs = {}
    for code, name in plans:
        specs = get_diag_specialties(code)
        plan_specs[code] = specs
        print(f"  plan {code} ({name}): {len(specs)} especialidades de diagnostico y tratamiento")

    combos = []
    for code, name in plans:
        for (esp_id, codigo, esp_name) in plan_specs[code]:
            for ubi in UBICACIONES:
                combos.append((code, esp_id, codigo, esp_name, ubi))

    print(f"Total combos a consultar: {len(combos)}")

    raw = []
    seen_keys = set()  # (itemID, codigo, address) dedupe

    def work(combo):
        code, esp_id, codigo, esp_name, ubi = combo
        recs = fetch_combo(code, esp_id, ubi)
        return code, codigo, esp_name, ubi, recs

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(work, c): c for c in combos}
        done = 0
        for fut in as_completed(futures):
            code, codigo, esp_name, ubi, recs = fut.result()
            for r in recs:
                item_id = r.get("itemID") or r.get("id")
                addr = (r.get("address") or "").strip()
                key = (item_id, codigo, addr)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                raw.append({
                    "plan": code,
                    "codigo_especialidad": codigo,
                    "especialidad": esp_name,
                    "ubicacion": ubi,
                    "item_id": item_id,
                    "nombre": (r.get("name") or "").strip(),
                    "direccion": addr,
                    "localidad": (r.get("locality") or "").strip(),
                    "provincia": (r.get("province") or "").strip(),
                    "cp": r.get("cp"),
                    "lat": r.get("latitude"),
                    "lon": r.get("longitude"),
                    "telefono": r.get("phoneNumber") or "",
                })
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(combos)} combos, {len(raw)} registros unicos hasta ahora")

    if INCOMPLETE:
        print(f"Reintentando {len(INCOMPLETE)} combos incompletos...")
        retry_targets = sorted(set((p, e, u) for p, e, u, _ in INCOMPLETE))
        esp_name_by_id = {}
        codigo_by_id = {}
        for code, specs in plan_specs.items():
            for (esp_id, codigo, esp_name) in specs:
                esp_name_by_id[esp_id] = esp_name
                codigo_by_id[esp_id] = codigo
        for plan_code, esp_id, ubi in retry_targets:
            time.sleep(0.3)
            recs = fetch_combo(plan_code, esp_id, ubi)
            codigo = codigo_by_id.get(esp_id, esp_id)
            esp_name = esp_name_by_id.get(esp_id, "")
            for r in recs:
                item_id = r.get("itemID") or r.get("id")
                addr = (r.get("address") or "").strip()
                key = (item_id, codigo, addr)
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                raw.append({
                    "plan": plan_code,
                    "codigo_especialidad": codigo,
                    "especialidad": esp_name,
                    "ubicacion": ubi,
                    "item_id": item_id,
                    "nombre": (r.get("name") or "").strip(),
                    "direccion": addr,
                    "localidad": (r.get("locality") or "").strip(),
                    "provincia": (r.get("province") or "").strip(),
                    "cp": r.get("cp"),
                    "lat": r.get("latitude"),
                    "lon": r.get("longitude"),
                    "telefono": r.get("phoneNumber") or "",
                })

    json.dump(raw, open(out_dir / "omint_raw.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Total registros crudos (deduplicado): {len(raw)}")

    institutions = {}
    sedes = set()
    attrs = set()
    coberturas = set()
    excluded_names = set()
    plan_by_code = dict(plans)
    for r in raw:
        if not r["nombre"]:
            continue
        if not is_institution(r["nombre"]):
            excluded_names.add(r["nombre"])
            continue
        pid = "omt-" + slug(r["nombre"]) + "-" + str(r["item_id"])[-6:]
        institutions[pid] = r["nombre"]
        sedes.add((pid, r["direccion"], r["localidad"], r["telefono"]))
        mapping = ESPECIALIDAD_MAP.get(r["codigo_especialidad"])
        if mapping:
            attrs.add((pid, mapping[0], mapping[1]))
        coberturas.add((pid, r["plan"]))

    with open(out_dir / "review_dudoso.txt", "w", encoding="utf-8") as f:
        f.write(f"{len(excluded_names)} nombres excluidos de la carga por parecer medicos individuales.\n")
        f.write("Si alguno es en realidad una institucion, avisa el nombre exacto.\n\n")
        for n in sorted(excluded_names):
            f.write(n + "\n")

    def esc(s):
        return (s or "").replace("'", "''")

    with open(out_dir / "omint_p.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _omt_p (pid, nombre) VALUES\n")
        f.write(",\n".join(f"('{pid}','{esc(name)}')" for pid, name in institutions.items()) + ";\n")

    with open(out_dir / "omint_s.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _omt_s (pid, direccion, loc, tel) VALUES\n")
        f.write(",\n".join(f"('{pid}','{esc(a)}','{esc(l)}','{esc(t)}')" for pid, a, l, t in sedes) + ";\n")

    with open(out_dir / "omint_a.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _omt_a (pid, atributo_id, poblacion_id) VALUES\n")
        f.write(",\n".join(f"('{pid}','{atr}','{pobl}')" for pid, atr, pobl in attrs) + ";\n")

    with open(out_dir / "omint_cob.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _omt_cob (pid, plan) VALUES\n")
        f.write(",\n".join(f"('{pid}','{esc(plan_by_code.get(plan,plan))}')" for pid, plan in coberturas) + ";\n")

    by_esp = {}
    for r in raw:
        if not r["nombre"] or r["nombre"] in excluded_names:
            continue
        by_esp.setdefault(r["especialidad"], set()).add(r["nombre"])
    with open(out_dir / "omint_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Instituciones unicas: {len(institutions)}\n\n")
        for esp in sorted(by_esp.keys()):
            f.write(f"## {esp} ({len(by_esp[esp])} instituciones)\n")

    print(f"Instituciones: {len(institutions)}, sedes: {len(sedes)}, atributos: {len(attrs)}, cobertura x plan: {len(coberturas)}, excluidos (dudoso): {len(excluded_names)}")
    print(f"Archivos en {out_dir}/omint_*.sql — revisar omint_summary.txt antes de cargar.")


if __name__ == "__main__":
    main()
