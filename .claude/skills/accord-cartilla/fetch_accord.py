#!/usr/bin/env python3
"""
Fetch Diagnostico y Tratamiento centros (institutions, not individual doctors) from
Accord Salud's public cartilla API, for CABA + GBA (zona metropolitana), all plans.

Accord Salud shares its cartilla backend with Union Personal (same corporate group):
  https://api.unionpersonal.com.ar/cartilla
Auth: header X-API-KEY: <static key extracted from the accordsalud.com.ar bundle>.
org param "ac" = Accord Salud (vs "up" = Union Personal, "uy"/"uruguay" variants).

API hierarchy (all GET, all wrapped {success, data, ...}):
  /planes/{org}                                              -> [{codigo_plan, nombre_plan}]
  /zonas/{org}                                                -> [{key, texto}] ("metropolitana" = CABA+GBA)
  /tipos/{org}/{plan}                                         -> [{code, description}] (M=MEDICA, O=ODONTO, ...)
  /subzonas/{org}/{plan}/{zona}/{tipo}                        -> {results:[{code, description}]}
  /categorias/{org}/{plan}/{zona}/{subzona}/{tipo}            -> {results:[{code, description}]}
  /especialidades/{org}/{plan}/{zona}/{subzona}/{tipo}/{categoria} -> {results:[{code, description}]}
  /localidades/{org}/{plan}/{zona}/{subzona}/{tipo}/{categoria}/{especialidad} -> {results:[{code, description}]}
  /prestadores/{org}/{plan}/{zona}/{subzona}/{tipo}/{categoria}/{especialidad}/{localidad} -> {results:[{...}]}

IMPORTANT: /prestadores WITHOUT a localidad returns data:[] (empty) even though HTTP 200 -
localidad is mandatory and must be swept from /localidades per (subzona, categoria, especialidad)
combo - it is NOT a fixed list per subzona, it depends on which specialty is being searched.

Diagnostico y Tratamiento scope = tipo "M" (MEDICA), categorias:
  M6  ESTUDIOS Y PRACTICAS MEDICAS  (~30 especialidades: ecografia, tomografia, etc.)
  M7  RADIOLOGIA                    (radiologia simple + con contraste)
  M11 LABORATORIOS                  (laboratorios clinicos)
(other M categories like M1/M2/M8/M9/M10 - internacion, urgencias, especialidades medicas,
fonoaudiologia, kinesiologia - are consultorios/individual-professional scope, excluded)

Zona metropolitana subzonas used (CABA + GBA, matching the "area metropolitana" scope used
for Medicus/Medife/Omint): CAR991 Ciudad de Bs As, CAR992 GBA Norte, CAR993 GBA Oeste,
CAR994 GBA Sur, CAR995 GBA Noroeste.

Like Omint (and unlike Medife), Accord's /prestadores results DO mix individual doctors in
with real institutions in the M6/M7/M11 categories (solo practitioners billing diagnostic
studies under their own name). A keyword-based classifier (KW_WORDS, is_institution()) filters
these out, tuned by manually reviewing the excluded/included split on the actual fetched data.
All Accord names are uppercase, so - unlike Omint's classifier - there is no "short all-caps =
acronym" heuristic (it would just match every doctor name) and no "5+ words = institution"
heuristic (multiple doctors sharing one consultorio produce long personal-name strings, e.g.
"ASCUA ESTER MARIA VICTORIA FABRO JUAN PEDRO" - two doctors, not an institution).

Dedup key for a raw provider record: NomConsultorio (the specific branch name) + direccion,
since NomPrestador is the legal/holding name (e.g. "FINAER") while NomConsultorio is the
actual commercial branch (e.g. "CENTRO MEDICO DE NEFROLOGIA FINAER") - we use NomConsultorio
as nombre_comercial, matching how the app itself displays results (Rt/NomConsultorio in the JS).

Usage: python3 fetch_accord.py
Outputs (in this directory): accord_raw.json, accord_p.sql, accord_s.sql, accord_a.sql,
accord_cob.sql, accord_summary.txt
"""
import asyncio
import aiohttp
import json
import re
import unicodedata
import hashlib
from collections import defaultdict

API = "https://api.unionpersonal.com.ar/cartilla"
KEY = "vL1gTwRCkOtgr6Fu1p0UBa778OnMDCpgoNlbNTURHMBIM3iYKHvLepDSkWq8E1twKwgT9NYoy5s0OSlt9eQqFFqXM8vXTNFsj7H3NWBqOfLpUuvVBqroodPsRbzpUGTVG7kWwZLEfkYe2NCxi1pBhgjP0I8ytcaagawZ7LOqEG7CGnKxJcPKLUZXtgPF5jhqgK0mhnLUaaaaQdwYhAK6eJaAHqKFgHzqCSxCSnl3ipfRGW4zBhXjP7YcAhqH2xNm"
HEADERS = {"X-API-KEY": KEY}
ORG = "ac"
ZONA = "metropolitana"
TIPO = "M"
CATEGORIAS = ["M6", "M7", "M11"]
SUBZONAS = ["CAR991", "CAR992", "CAR993", "CAR994", "CAR995"]

# atributo_id/poblacion_id map, keyed by especialidad description (uppercased, normalized).
# poblacion_id 1 = adultos+pediatrico (general) unless the name says otherwise.
ESPECIALIDAD_MAP = {
    "ANATOMIA PATOLOGICA": ("anatomia-patologica", 1),
    "AUDIOMETRIA-LOGOAUDIOMETRIA-TIMPANOMETRIA-IMPEDANCIOMETRIA": ("audiometria", 1),
    "CAMPO VISUAL/ CAMPIMETRIA/PERIMETRIA/COMPUTARIZADA": None,
    "CISTOSCOPIAS": None,
    "CITOLOGIA EXFOLIATIVA (PAP)": None,
    "COLANGIOGRAFIA RETROGRADA": None,
    "DENSITOMETRIA OSEA": ("densitometria", 1),
    "ECOCARDIOGRAMA": ("ecocardiograma", 1),
    "ECOCARDIOGRAMA INFANTIL": ("ecocardiograma", 2),
    "ECODOPPLER ARTERIAL Y VENOSO": ("ecodoppler", 1),
    "ECODOPPLER CARDIOLOGICO": ("ecodoppler", 1),
    "ECOGRAFIAS GENERALES": ("ecografia", 1),
    "ECOGRAFIAS INFANTILES": ("ecografia", 2),
    "ECOTOMOGRAFIA MAMARIA": ("mamografia", 1),
    "EJERCICIOS ORTOPTICOS": None,
    "ELECTROCARDIOGRAMA": ("electrocardiograma", 1),
    "ELECTROENCEFALOGRAMA": ("electroencefalograma", 1),
    "ELECTROMIOGRAMA": None,
    "ERGOMETRIA": ("ergometria", 1),
    "ESPINOGRAMA": None,
    "ESPIROMETRIA": ("espirometria", 1),
    "HISTEROSCOPIA": None,
    "HOLTER": ("holter-ritmo", 1),
    "MAMOGRAFIA-SENOGRAFIA": ("mamografia", 1),
    "OTOMISIONES ACUSTICAS": None,
    "PAQUIMETRIA CORNEAL COMPUTARIZADA": None,
    "POLISOMNOGRAFIA CON O SIN OXIMETRIA - NOCTURNA": None,
    "POLISOMNOGRAFIA NOCTURNA + C-PAP": None,
    "POTENCIALES EVOCADOS (BERA - POE - PESS)": ("potenciales-evocados", 1),
    "PRESUROMETRIA": ("holter-presion", 1),
    "PUNCION BIOPSIA BAJO CONTROL ECOGRAFICO": None,
    "PUNCION BIOPSIA BAJO CONTROL TOMOGRAFICO": None,
    "RADIOLOGIA SERIADA": ("radiologia", 1),
    "RADIOLOGIA": ("radiologia", 1),
    "RADIOLOGIA CON CONTRASTE": ("radiologia-intervencionista", 1),
    "LABORATORIOS": ("laboratorio", 1),
    "RESONANCIA MAGNETICA": ("resonancia", 1),
    "TOMOGRAFIA COMPUTADA": ("tomografia", 1),
    "TOMOGRAFIA COMPUTADA MULTICORTE": ("tomografia", 1),
    "UROFLUJOMETRIA": ("urodinamia", 1),
    "MEDICINA NUCLEAR": ("medicina-nuclear", 1),
    "MONITOREO FETAL": ("monitoreo-fetal", 1),
    "HEMODINAMIA": ("hemodinamia", 1),
    "ENDOSCOPIA DIGESTIVA": ("endoscopia", 1),
    "VIDEOENDOSCOPIA DIGESTIVA": ("endoscopia", 1),
    "VIDEOCOLONOSCOPIA (VCC)": ("endoscopia", 1),
    "VIDEOENDOSCOPIA DIGESTIVA ALTA/ BAJA (VEDA/ VCC)": ("endoscopia", 1),
    "VIDEOESOFAGOGASTRODUODENOSCOPIA (VEDA)": ("endoscopia", 1),
    "FIBROBRONCOSCOPIA": ("endoscopia", 1),
    "TOMOGRAFIA AXIAL COMPUTADA": ("tomografia", 1),
    "COLANGIORESONANCIA MAGNETICA": ("resonancia", 1),
    "ECODOPPLER ARTERIAL Y VENOSO INFANTIL": ("ecodoppler", 2),
    "ECODOPPLER CARDIOLOGICO INFANTIL": ("ecodoppler", 2),
    "ELECTROCARDIOGRAMA INFANTIL": ("electrocardiograma", 2),
    "ELECTROENCEFALOGRAMA INFANTIL": ("electroencefalograma", 2),
    "ELECTROMIOGRAMA": ("electromiograma", 1),
    "HOLTER INFANTIL": ("holter-ritmo", 2),
    "POTENCIALES EVOCADOS (BERA - POE - PESS) INFANTILES": ("potenciales-evocados", 2),
    "URODINAMIA ADULTOS": ("urodinamia", 1),
    "URODINAMIA INFANTIL": ("urodinamia", 2),
    "RADIOTERAPIA CON ACELERADOR LINEAL": ("radioterapia", 1),
    "TELECOBALTO TERAPIA": ("radioterapia", 1),
}


def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().strip()


def slug(s, maxlen=35):
    s = re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-")
    return s[:maxlen]


KW_WORDS = [
    "centro", "centros", "ctro", "instituto", "institutos", "laboratorio", "laboratorios",
    "lab", "clinica", "sanatorio", "consultorio", "consultorios", "fundacion", "grupo",
    "diagnostico", "diagnostica", "ecografia", "ecografico", "radiologia", "radiologico",
    "imagenes", "imagen", "tomografia", "resonancia", "cardiovascular", "gastroenterologia",
    "oftalmologico", "oftalmologia", "cardiologico", "cardiologia", "servicio", "servicios",
    "unidad", "srl", "sa", "sh", "hospital", "policlinica", "sistema", "analisis", "clinico",
    "clinicos", "bioquimico", "densitometria", "radiologica", "medicina", "medico", "medicos",
    "prevencion", "prestaciones", "equipo", "oftalmologica", "urologia", "traumatologico",
    "integral", "integrales", "asoc", "sanatorial", "anal", "cidi", "imat",
]
INSTITUTION_WHITELIST = {"fundus"}
_WORD_RE = re.compile(r"[a-z]+")


def is_institution(name):
    """Accord's M6/M7/M11 results mix individual doctors with real institutions (like Omint,
    unlike Medife). Classified by keyword match, digits, or spaced-out legal-entity suffixes
    ("S A", "S R L", "S H") - see module docstring for why length/case heuristics don't work
    here (all names are uppercase)."""
    u = norm(name)
    words = set(_WORD_RE.findall(u))
    if words & set(KW_WORDS):
        return True
    if u in INSTITUTION_WHITELIST:
        return True
    if re.search(r"\d", name):
        return True
    if re.search(r"\bs\s+a\b", u) or re.search(r"\bs\s+r\s+l\b", u) or re.search(r"\bs\s+h\b", u):
        return True
    return False


async def get(session, path, sem, retries=4):
    url = f"{API}{path}"
    for attempt in range(retries):
        try:
            async with sem:
                async with session.get(url, headers=HEADERS, timeout=30) as r:
                    if r.status != 200:
                        await asyncio.sleep(1 + attempt)
                        continue
                    j = await r.json()
                    if not j.get("success"):
                        return None
                    return j.get("data")
        except Exception:
            await asyncio.sleep(1 + attempt)
    return None


async def main():
    sem = asyncio.Semaphore(25)
    async with aiohttp.ClientSession() as session:
        planes_raw = await get(session, f"/planes/{ORG}", sem)
        planes = []
        seen_codes = set()
        for p in planes_raw:
            if p["codigo_plan"] in seen_codes:
                continue
            seen_codes.add(p["codigo_plan"])
            planes.append(p)
        print(f"{len(planes)} planes")

        # Step 1: for each (plan, subzona, categoria) get especialidades.
        esp_tasks = {}
        for plan in planes:
            pc = plan["codigo_plan"]
            for sub in SUBZONAS:
                for cat in CATEGORIAS:
                    key = (pc, sub, cat)
                    esp_tasks[key] = get(
                        session, f"/especialidades/{ORG}/{pc}/{ZONA}/{sub}/{TIPO}/{cat}", sem
                    )
        esp_results = dict(zip(esp_tasks.keys(), await asyncio.gather(*esp_tasks.values())))

        # Step 2: for each (plan, subzona, categoria, especialidad) get localidades.
        loc_tasks = {}
        combo_meta = {}
        for (pc, sub, cat), data in esp_results.items():
            if not data:
                continue
            for esp in data.get("results", []):
                ecode = esp["code"]
                combo = (pc, sub, cat, ecode)
                combo_meta[combo] = esp["description"]
                loc_tasks[combo] = get(
                    session,
                    f"/localidades/{ORG}/{pc}/{ZONA}/{sub}/{TIPO}/{cat}/{ecode}",
                    sem,
                )
        print(f"{len(loc_tasks)} especialidad combos, fetching localidades...")
        loc_results = dict(zip(loc_tasks.keys(), await asyncio.gather(*loc_tasks.values())))

        # Step 3: for each (plan, subzona, categoria, especialidad, localidad) get prestadores.
        pr_tasks = {}
        for combo, data in loc_results.items():
            if not data:
                continue
            pc, sub, cat, ecode = combo
            for loc in data.get("results", []):
                lcode = loc["code"]
                full = combo + (lcode,)
                pr_tasks[full] = get(
                    session,
                    f"/prestadores/{ORG}/{pc}/{ZONA}/{sub}/{TIPO}/{cat}/{ecode}/{lcode}",
                    sem,
                )
        print(f"{len(pr_tasks)} localidad combos, fetching prestadores...")
        # Fetch in chunks to log progress.
        keys = list(pr_tasks.keys())
        results = []
        CHUNK = 500
        for i in range(0, len(keys), CHUNK):
            chunk_keys = keys[i : i + CHUNK]
            chunk_res = await asyncio.gather(*[pr_tasks[k] for k in chunk_keys])
            results.extend(zip(chunk_keys, chunk_res))
            print(f"  {min(i+CHUNK, len(keys))}/{len(keys)}")

    raw = []
    for (pc, sub, cat, ecode, lcode), data in results:
        if not data:
            continue
        plist = data.get("results", []) if isinstance(data, dict) else []
        for r in plist:
            r["_plan"] = pc
            r["_esp_desc"] = combo_meta.get((pc, sub, cat, ecode), "")
            raw.append(r)

    with open("accord_raw.json", "w") as f:
        json.dump(raw, f, ensure_ascii=False)
    print(f"{len(raw)} raw records saved")

    plan_names = {p["codigo_plan"]: p["nombre_plan"] for p in planes}

    # Dedup institutions by normalized NomConsultorio (the branch/commercial name).
    inst_by_key = {}
    inst_pid = {}
    sedes = {}
    attrs = set()
    cobs = set()
    unmapped_esp = set()
    excluded_names = set()

    for r in raw:
        nombre = (r.get("NomConsultorio") or r.get("NomPrestador") or "").strip()
        if not nombre:
            continue
        if not is_institution(nombre):
            excluded_names.add(nombre)
            continue
        direccion = (r.get("fullDireccion") or f"{r.get('Calle','')} {r.get('Numero','')}").strip()
        localidad = r.get("NomLocalidad", "")
        tel = r.get("Telefono", "")
        ikey = norm(nombre)
        if ikey not in inst_pid:
            pid = "p" + hashlib.md5(ikey.encode()).hexdigest()[:10]
            inst_pid[ikey] = pid
            inst_by_key[pid] = nombre
        pid = inst_pid[ikey]

        skey = (pid, norm(direccion))
        if skey not in sedes:
            sedes[skey] = {
                "pid": pid,
                "direccion": direccion,
                "localidad": localidad,
                "telefono": tel,
            }

        esp_desc = r.get("_esp_desc") or r.get("NomEspecialidad", "")
        mapped = ESPECIALIDAD_MAP.get(esp_desc.strip().upper())
        if mapped is None:
            unmapped_esp.add(esp_desc)
        else:
            atributo_id, poblacion_id = mapped
            attrs.add((pid, direccion, atributo_id, poblacion_id))

        cobs.add((pid, r["_plan"]))

    print(f"{len(inst_by_key)} institutions, {len(sedes)} sedes, {len(attrs)} atributo links, {len(cobs)} cobertura links")
    print(f"{len(excluded_names)} individual-doctor names excluded (see accord_review_dudoso.txt)")
    with open("accord_review_dudoso.txt", "w") as f:
        f.write(f"{len(excluded_names)} names classified as individual doctors (excluded):\n\n")
        for n in sorted(excluded_names):
            f.write(f"{n}\n")
    if unmapped_esp:
        print(f"WARNING: {len(unmapped_esp)} unmapped especialidades (skipped, not in Diag/Trat map): {sorted(unmapped_esp)}")

    def esc(s):
        return (s or "").replace("'", "''")

    with open("accord_p.sql", "w") as f:
        for pid, nombre in inst_by_key.items():
            f.write(f"INSERT INTO _acc_p (pid, nombre) VALUES ('{pid}', '{esc(nombre)}');\n")

    with open("accord_s.sql", "w") as f:
        for (pid, _), s in sedes.items():
            f.write(
                f"INSERT INTO _acc_s (pid, direccion, loc, tel) VALUES "
                f"('{s['pid']}', '{esc(s['direccion'])}', '{esc(s['localidad'])}', '{esc(s['telefono'])}');\n"
            )

    with open("accord_a.sql", "w") as f:
        for pid, direccion, atributo_id, poblacion_id in attrs:
            f.write(
                f"INSERT INTO _acc_a (pid, direccion, atributo_id, poblacion_id) VALUES "
                f"('{pid}', '{esc(direccion)}', '{atributo_id}', {poblacion_id});\n"
            )

    with open("accord_cob.sql", "w") as f:
        for pid, plan_code in cobs:
            f.write(f"INSERT INTO _acc_cob (pid, plan_nombre) VALUES ('{pid}', '{esc(plan_names.get(plan_code, plan_code))}');\n")

    with open("accord_summary.txt", "w") as f:
        f.write(f"Planes: {len(planes)}\n")
        for p in planes:
            f.write(f"  {p['codigo_plan']}: {p['nombre_plan']}\n")
        f.write(f"\nInstitutions: {len(inst_by_key)}\nSedes: {len(sedes)}\nAtributo links: {len(attrs)}\nCobertura links: {len(cobs)}\n")
        if unmapped_esp:
            f.write(f"\nUnmapped especialidades:\n")
            for e in sorted(unmapped_esp):
                f.write(f"  {e}\n")

    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
