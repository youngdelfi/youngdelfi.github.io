#!/usr/bin/env python3
"""
Descarga masiva de prestadores de Medife (cartilla "Diagnostico y Tratamiento")
via la API publica de medife.com.ar, para CABA+GBA (idProvincia=1) y
Provincia de Buenos Aires (idProvincia=2).

La API expone, por especialidad+provincia+plan, una lista paginada de
prestadores. Cada registro trae flags embebidos indicando en que otros
planes participa ese mismo prestador (ej. "ORO":"ORO","PLATA":"PLATA"),
asi que basta con consultar un plan representativo por cada red distinta
en vez de los 7 planes completos:

  - ORO representa a {ORO, BRONCE, PLATINUM, PLATA, BRONCE CLASSIC}
    (confirmado con mismo total y mismos IDs para una especialidad de
    prueba; si el usuario necesita 100% de certeza para todas las
    especialidades, se puede correr con QUERY_PLANS = todos los 7).
  - MEDIFE+ y PLATA CLASSIC e INDIE tienen redes propias distintas.

Uso:
    python3 fetch_medife.py <out_dir> [--full-plans]

Genera en <out_dir>:
    medife_raw.json       lista cruda de registros (prestador, especialidad, provincia)
    medife_p.sql / _s.sql / _a.sql   SQL de staging (mismo formato que medicus-cartilla)
    medife_summary.txt    resumen por especialidad para revisar antes de cargar
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

BASE = "https://www.medife.com.ar/medifeapp"

QUERY_PLANS = ["ORO", "MEDIFE+", "PLATA CLASSIC", "INDIE"]
FULL_PLANS = ["ORO", "BRONCE", "PLATINUM", "PLATA", "BRONCE CLASSIC", "MEDIFE+", "PLATA CLASSIC", "INDIE"]

PROVINCIAS = [1, 2]  # ya no se usa como filtro geografico real (ver CODIGOS_POSTALES)

# DESCUBRIMIENTO IMPORTANTE (ver commit que agrega esto): idProvincia NO filtra
# geograficamente. El filtro real es codigoPostalUno. El CP "9999" que trae la
# URL de ejemplo del usuario es un codigo generico/comodin que devuelve
# practicamente solo instituciones de CABA (confirmado: bajo idProvincia=1 Y 2,
# con CP=9999, el 100% de los ~1074 registros crudos traia LOCALIDAD="CIUDAD
# AUTONOMA DE BS.AS." y coordenadas dentro de CABA). Un CP real de GBA (ej.
# 1900=La Plata, 1704=Ramos Mejia, 1650=San Martin) sí devuelve instituciones
# localizadas correctamente ahi, sin importar el idProvincia usado.
#
# Por eso el barrido geografico correcto es por CODIGO POSTAL, no por
# idProvincia. Se usa un CP representativo por partido del GBA (uno de los
# mas centricos/pobladas de cada partido) mas 9999 para CABA — igual que
# Medicus cubre "area metropolitana" con un conjunto representativo de zonas,
# esto NO es un barrido exhaustivo de todos los CP de la region (hay cientos),
# así que puede faltar algun centro de un barrio/localidad puntual no cubierto
# por el CP elegido para ese partido. Si hace falta más cobertura, agregar más
# CPs por partido a esta lista.
CODIGOS_POSTALES = [
    "9999",  # CABA (comodin, cubre toda la ciudad)
    "1642",  # San Isidro
    "1602",  # Vicente Lopez
    "1646",  # San Fernando
    "1648",  # Tigre
    "1663",  # San Miguel
    "1665",  # Jose C. Paz
    "1613",  # Malvinas Argentinas (Los Polvorines)
    "1650",  # General San Martin
    "1678",  # Tres de Febrero (Caseros)
    "1686",  # Hurlingham
    "1714",  # Ituzaingo
    "1708",  # Moron
    "1722",  # Merlo
    "1744",  # Moreno
    "1748",  # General Rodriguez
    "1754",  # La Matanza (San Justo)
    "1804",  # Ezeiza
    "1842",  # Esteban Echeverria (Monte Grande)
    "1846",  # Almirante Brown (Adrogue)
    "1832",  # Lomas de Zamora
    "1824",  # Lanus
    "1870",  # Avellaneda
    "1878",  # Quilmes
    "1884",  # Berazategui
    "1888",  # Florencio Varela
    "1629",  # Pilar
    "1625",  # Escobar
    "1900",  # La Plata
]

# cada registro de la API trae, ademas de sus propios datos, flags booleanas
# (la clave presente = pertenece a ese plan) indicando en que otros planes
# participa el mismo prestador — asi que de una sola consulta (a cualquiera
# de los QUERY_PLANS) se puede leer la pertenencia a los 8 planes completos.
PLAN_KEYS = {
    "ORO": "ORO",
    "BRONCE": "BRONCE",
    "PLATINUM": "PLATINUM",
    "PLATA": "PLATA",
    "BRONCECLASSIC": "BRONCE CLASSIC",
    "PLATACLASSIC": "PLATA CLASSIC",
    "MEDIFEPLUS": "MEDIFE+",
    "INDIE": "INDIE",
}

# mapeo IDESPECIALIDAD (tipo PRA) -> (atributo_id, poblacion_id) en nuestra base.
# especialidades sin equivalente claro en nuestro modelo (kinesiologia,
# nutricion, quimioterapia, traslados, etc.) se omiten (no generan
# prestador_atributo, pero el prestador y su cobertura igual se cargan).
ESPECIALIDAD_MAP = {
    87: ("anatomia-patologica", "general"),
    88: ("radiologia-intervencionista", "general"),
    89: ("radiologia-intervencionista", "general"),
    90: ("audiometria", "general"),
    92: ("densitometria", "general"),
    167: ("ecodoppler", "general"),
    93: ("ecocardiograma", "general"),
    94: ("ecocardiograma", "infantil"),
    95: ("ecografia", "general"),
    160: ("ecodoppler", "general"),
    96: ("ecografia", "infantil"),
    97: ("electrocardiograma", "infantil"),
    98: ("electrocardiograma", "general"),
    100: ("electroencefalograma", "general"),
    101: ("electroencefalograma", "infantil"),
    102: ("electromiograma", "general"),
    103: ("endoscopia", "general"),
    104: ("endoscopia", "infantil"),
    105: ("endoscopia", "general"),
    106: ("endoscopia", "general"),
    107: ("endoscopia", "general"),
    108: ("ergometria", "general"),
    109: ("espirometria", "general"),
    110: ("espirometria", "infantil"),
    111: ("mamografia", "general"),
    113: ("hemodinamia", "general"),
    114: ("hemodinamia", "infantil"),
    99: ("holter-ritmo", "general"),
    117: ("laboratorio", "general"),
    119: ("medicina-nuclear", "general"),
    120: ("medicina-nuclear", "infantil"),
    121: ("monitoreo-fetal", "general"),
    124: ("potenciales-evocados", "general"),
    128: ("radiologia", "general"),
    129: ("radiologia", "infantil"),
    133: ("resonancia", "general"),
    134: ("tomografia", "general"),
    135: ("urodinamia", "general"),
}

DOCTOR_RE = re.compile(r'^[A-ZÑÁÉÍÓÚ][A-ZÑÁÉÍÓÚ\'\-\. ]+,\s*[A-ZÑÁÉÍÓÚ]')


def http_get_json(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read()
            data = json.loads(body)
            if isinstance(data, dict) and "content" not in data and "TIPO" not in data and not isinstance(data, list):
                # respuesta valida pero con forma inesperada (posible error silencioso del backend)
                print(f"UNEXPECTED SHAPE {url}: {body[:200]}", file=sys.stderr)
            return data
        except Exception as e:
            print(f"attempt {attempt+1}/{retries} failed for {url}: {e}", file=sys.stderr)
            if attempt == retries - 1:
                return None
            time.sleep(1.0 * (attempt + 1))


def get_especialidades():
    url = f"{BASE}/lista-especialidades-v2?tipoEspecialidad=PRA&t=1"
    data = http_get_json(url)
    return [(d["IDESPECIALIDAD"], d["NOMBRE"]) for d in data]


def fetch_combo(plan, esp_id, cp):
    """Devuelve lista de registros de prestadores para (plan, especialidad, codigo
    postal), recorriendo todas las paginas. Si una pagina falla persistentemente
    tras reintentar, se registra el combo como incompleto en vez de truncar en
    silencio (ver INCOMPLETE global). idProvincia se deja fijo en 1: no filtra
    geograficamente (ver nota junto a CODIGOS_POSTALES), asi que el valor no
    importa."""
    out = []
    pagina = 1
    plan_q = urllib.parse.quote(plan)
    while True:
        url = (f"{BASE}/lista-prestadores-v2?nombrePlan={plan_q}&idEspecialidad={esp_id}"
               f"&codigoPostalDos=1&codigoPostalUno={cp}&idProvincia=1"
               f"&pagina={pagina}&size=20&t=1")
        data = None
        for flaky_attempt in range(4):
            data = http_get_json(url, retries=3)
            if data and "content" in data:
                total_elements = data.get("totalElements", 0)
                if total_elements > 0 and not data["content"]:
                    # respuesta 200 pero con contenido vacio pese a haber
                    # resultados (flakiness intermitente del backend) -> reintentar
                    time.sleep(0.5 * (flaky_attempt + 1))
                    continue
                break
            time.sleep(0.5 * (flaky_attempt + 1))
        if not data or "content" not in data:
            INCOMPLETE.append((plan, esp_id, cp, pagina))
            break
        if data.get("totalElements", 0) > 0 and not data["content"]:
            # sigue vacio tras reintentar: registrar como incompleto y cortar
            # esta pagina en vez de perder las siguientes en silencio
            INCOMPLETE.append((plan, esp_id, cp, pagina))
            break
        out.extend(data["content"])
        total_pages = data.get("totalPages", 1)
        if pagina >= total_pages:
            break
        pagina += 1
    return out


INCOMPLETE = []


def is_doctor(name):
    # en los datos de Medife, absolutamente ninguna institucion tiene coma
    # en el nombre (los medicos siempre se listan "APELLIDO, NOMBRE");
    # mas robusto que cualquier regex de patron de persona.
    return ',' in name


def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return s.lower()


def slug(s, maxlen=35):
    s = norm(s)
    s = re.sub(r'[^a-z0-9]+', '-', s).strip('-')
    return s[:maxlen]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    out_dir = Path(sys.argv[1])
    out_dir.mkdir(parents=True, exist_ok=True)
    full = "--full-plans" in sys.argv
    plans = FULL_PLANS if full else QUERY_PLANS

    especialidades = get_especialidades()
    print(f"{len(especialidades)} especialidades PRA, {len(plans)} planes, {len(CODIGOS_POSTALES)} codigos postales")

    combos = [(plan, eid, cp) for plan in plans for (eid, ename) in especialidades for cp in CODIGOS_POSTALES]
    esp_names = {eid: ename for eid, ename in especialidades}

    raw = []
    seen_keys = set()  # (prestador_id, especialidad_id, direccion) dedupe across plans/CPs

    def work(combo):
        plan, eid, cp = combo
        recs = fetch_combo(plan, eid, cp)
        return eid, cp, recs

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(work, c): c for c in combos}
        done = 0
        for fut in as_completed(futures):
            eid, cp, recs = fut.result()
            for r in recs:
                key = (r.get("ID"), eid, r.get("DIRECCION","").strip())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                raw.append({
                    "especialidad_id": eid,
                    "especialidad": esp_names.get(eid, ""),
                    "cp_consultado": cp,
                    "id": r.get("ID"),
                    "nombre": r.get("NOMBRE", "").strip(),
                    "direccion": r.get("DIRECCION", "").strip(),
                    "localidad": r.get("LOCALIDAD", "").strip(),
                    "cp": r.get("CODIGOPOSTAL", ""),
                    "lat": r.get("LATITUD"),
                    "lon": r.get("LONGITUD"),
                    "telefono": r.get("TELEFONO1", ""),
                    "planes": [nombre for key_, nombre in PLAN_KEYS.items() if r.get(key_)],
                })
            done += 1
            if done % 200 == 0:
                print(f"  {done}/{len(combos)} combos, {len(raw)} registros unicos hasta ahora")

    # segundo pase: reintentar combos/paginas que fallaron durante la corrida concurrente
    if INCOMPLETE:
        print(f"Reintentando {len(INCOMPLETE)} combos incompletos (secuencial, con pausas)...")
        retry_targets = sorted(set((p, e, pr) for p, e, pr, _ in INCOMPLETE))
        for plan, eid, cp in retry_targets:
            time.sleep(0.3)
            recs = fetch_combo(plan, eid, cp)
            for r in recs:
                key = (r.get("ID"), eid, r.get("DIRECCION","").strip())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                raw.append({
                    "especialidad_id": eid,
                    "especialidad": esp_names.get(eid, ""),
                    "cp_consultado": cp,
                    "id": r.get("ID"),
                    "nombre": r.get("NOMBRE", "").strip(),
                    "direccion": r.get("DIRECCION", "").strip(),
                    "localidad": r.get("LOCALIDAD", "").strip(),
                    "cp": r.get("CODIGOPOSTAL", ""),
                    "lat": r.get("LATITUD"),
                    "lon": r.get("LONGITUD"),
                    "telefono": r.get("TELEFONO1", ""),
                    "planes": [nombre for key_, nombre in PLAN_KEYS.items() if r.get(key_)],
                })
        still_bad = [x for x in INCOMPLETE if (x[0], x[1], x[2]) in retry_targets]
        print(f"Tras reintento: {len(raw)} registros totales. (revisar stderr por fallas persistentes)")

    json.dump(raw, open(out_dir / "medife_raw.json", "w", encoding="utf-8"), ensure_ascii=False)
    print(f"Total registros crudos (prestador x especialidad, deduplicado): {len(raw)}")

    # armar staging: institutions = nombres que NO matchean patron de persona
    institutions = {}
    sedes = set()
    attrs = set()
    coberturas = set()
    for r in raw:
        if is_doctor(r["nombre"]):
            continue
        pid = "mdf-" + slug(r["nombre"]) + "-" + str(r["id"])[-5:]
        institutions[pid] = r["nombre"]
        sedes.add((pid, r["direccion"], r["localidad"], r["telefono"]))
        mapping = ESPECIALIDAD_MAP.get(r["especialidad_id"])
        if mapping:
            attrs.add((pid, mapping[0], mapping[1]))
        for plan in r.get("planes", []):
            coberturas.add((pid, plan))

    def esc(s):
        return (s or "").replace("'", "''")

    with open(out_dir / "medife_p.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _mdf_p (pid, nombre) VALUES\n")
        f.write(",\n".join(f"('{pid}','{esc(name)}')" for pid, name in institutions.items()) + ";\n")

    with open(out_dir / "medife_s.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _mdf_s (pid, direccion, loc, tel) VALUES\n")
        f.write(",\n".join(f"('{pid}','{esc(a)}','{esc(l)}','{esc(t)}')" for pid, a, l, t in sedes) + ";\n")

    with open(out_dir / "medife_a.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _mdf_a (pid, atributo_id, poblacion_id) VALUES\n")
        f.write(",\n".join(f"('{pid}','{atr}','{pobl}')" for pid, atr, pobl in attrs) + ";\n")

    with open(out_dir / "medife_cob.sql", "w", encoding="utf-8") as f:
        f.write("INSERT INTO _mdf_cob (pid, plan) VALUES\n")
        f.write(",\n".join(f"('{pid}','{esc(plan)}')" for pid, plan in coberturas) + ";\n")

    by_esp = {}
    for r in raw:
        if is_doctor(r["nombre"]):
            continue
        by_esp.setdefault(r["especialidad"], set()).add(r["nombre"])
    with open(out_dir / "medife_summary.txt", "w", encoding="utf-8") as f:
        f.write(f"Instituciones unicas: {len(institutions)}\n\n")
        for esp in sorted(by_esp.keys()):
            f.write(f"## {esp} ({len(by_esp[esp])} instituciones)\n")
        f.write("\n")

    print(f"Instituciones: {len(institutions)}, sedes: {len(sedes)}, atributos: {len(attrs)}, cobertura x plan: {len(coberturas)}")
    print(f"Archivos en {out_dir}/medife_*.sql — revisar medife_summary.txt antes de cargar.")


if __name__ == "__main__":
    main()
