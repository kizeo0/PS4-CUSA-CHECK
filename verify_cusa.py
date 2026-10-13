#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_cusa.py — Recompila CUSA + idiomas de dlpsgame.com (PS4)

Uso:
  py verify_cusa.py --one "https://dlpsgame.com/the-mortuary-assistant-ps4-pkg/"
  py verify_cusa.py --all --out data
  py verify_cusa.py --from-file urls.txt --out data

Lo que hace:
  - Descarga la ficha del juego
  - Extrae los bloques "CUSAxxxxx – REGION (@uploader)"
  - Decodifica los <div class="secure-data" data-payload="base64...">
    que contienen Voice: / Screen Languages:
  - Los empareja en orden (bloque 1 con payload 1, etc.) para una
    verificación exacta, igual que la manual.
  - Detecta español (España / México / genérico) en Voice y en Textos.
  - Guarda CSV + JSON.

No inventa nada: si no hay CUSA o no hay idiomas, lo marca como MISSING.
"""
import argparse
import base64
import csv
import json
import re
import sys
import sys
# Consola Windows: fuerza UTF-8 para que se vean tildes y – bien
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://dlpsgame.com/",
}

# CUSA12345, PLAS12345, PCAS12345, PLJM12345, etc.
CUSA_RE = re.compile(
    r"\b((?:CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)\s*-?\s*\d{5})\b\s*[–\-—]?\s*([A-Z]{2,4})?",
    re.IGNORECASE,
)
# Cabecera completa: CUSA43772 – EUR (@Opoisso893/Golemnight)
HEADER_RE = re.compile(
    r"((?:CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)\s*-?\s*\d{5})\s*[–\-—]\s*([A-Za-z]{2,4})?\s*(\(@[^)]+\)|\([^)]*@[^)]+\)|\(by[^)]+\)|\([^)]*\))?",
    re.IGNORECASE,
)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def fetch(url: str, timeout: int = 30, retries: int = 3, delay: float = 1.5) -> str:
    last_err = None
    for i in range(retries):
        try:
            r = SESSION.get(url, timeout=timeout)
            r.raise_for_status()
            # dlpsgame a veces devuelve con charset raro, forzamos utf-8 si hace falta
            if not r.encoding or r.encoding.lower() == "iso-8859-1":
                r.encoding = "utf-8"
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(delay * (i + 1))
    raise RuntimeError(f"No se pudo descargar {url}: {last_err}")


def clean_cusa(raw: str) -> str:
    """CUSA 43772 -> CUSA43772"""
    if not raw:
        return ""
    return re.sub(r"\s+|-", "", raw.strip().upper())


def decode_payload(b64: str) -> str:
    b64 = b64.strip()
    # a veces viene con espacios / saltos
    b64 += "=" * (-len(b64) % 4)
    try:
        raw = base64.b64decode(b64, validate=False)
    except Exception:
        # intenta limpiar
        b64clean = re.sub(r"[^A-Za-z0-9+/=]", "", b64)
        b64clean += "=" * (-len(b64clean) % 4)
        raw = base64.b64decode(b64clean)
    # casi siempre utf-8, a veces con entidades html
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except Exception:
            continue
    return raw.decode("utf-8", errors="replace")


def html_to_lines(html: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    # separa también los "|" que dlpsgame usa para juntar Audio | Subtitles en el mismo <p>
    t = soup.get_text(separator="\n", strip=True)
    # rompe por | y por saltos
    t = t.replace("|", "\n")
    lines = [re.sub(r"\s+", " ", x).strip() for x in t.splitlines()]
    return [x for x in lines if x]


# Variantes vistas en dlpsgame (incluye typos reales del sitio)
VOICE_LABELS = [
    "voice", "voices", "voise", "voises", "voi", "vois", "void", "voids",
    "audio", "audios", "dub", "dubs", "dubbed", "doblaje", "doblado",
    "voz", "voces", "vocal", "sound", "speech",
]
SCREEN_LABELS = [
    "screen languages", "screen language", "screen",
    "subtitles", "subtitle", "subs", "sub",
    "texts", "text", "text languages", "written",
    "languages", "language", "lenguages", "lenguage",
    "idiomas", "idioma", "langue", "langues",
    "menus", "interface",
]

# regex única para detectar cualquier etiqueta "algo :"
_ALL_LABELS_RE = re.compile(
    r"(?im)\b(" + "|".join(sorted(set(VOICE_LABELS + SCREEN_LABELS), key=len, reverse=True)) + r")\s*[:：]\s*"
)


def _clean_value(v: str) -> str:
    v = re.sub(r"\s+", " ", v).strip(" ,;|-\n\t")
    # corta coletillas de la ficha (Guide/Tool/Password/etc.)
    v = re.split(r"\(?\s*Guide Download", v, flags=re.IGNORECASE)[0]
    v = re.split(r"\(?\s*Tool Download", v, flags=re.IGNORECASE)[0]
    v = re.split(r"\bPassword\s*:", v, flags=re.IGNORECASE)[0]
    v = re.split(r"\bPasword\s*:", v, flags=re.IGNORECASE)[0]
    v = re.split(r"\bTnx to\b", v, flags=re.IGNORECASE)[0]
    v = v.strip(" ,;|-\n\t")
    # limpia tokens basura tipo "vv", "v", "-" (restos de links rotos)
    parts = [p.strip() for p in re.split(r",", v)]
    clean_parts = []
    for p in parts:
        pp = p.strip(" .;|()[]")
        if len(pp) < 2:
            continue
        if re.match(r"^(vv?|xx?|oo?|••?)$", pp, re.IGNORECASE):
            continue
        clean_parts.append(p.strip())
    return ", ".join(clean_parts).strip(" ,;|-")


def _label_kind(label: str) -> str:
    l = label.strip().lower()
    l = re.sub(r"\s+", " ", l)
    if l in VOICE_LABELS:
        return "voice"
    if l in SCREEN_LABELS:
        # "language(s)/idiomas" suelto = textos (dlpsgame usa Voice/Audio para doblaje)
        return "screen"
    return "screen"


def extract_voice_screen(decoded_html: str) -> dict:
    """Saca Voice y Screen/Textos cubriendo todas las variantes y typos del sitio."""
    lines = html_to_lines(decoded_html)
    full = "\n".join(lines)

    # Texto plano para regex global (con | ya separado)
    soup = BeautifulSoup(decoded_html, "lxml")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    plain = soup.get_text(separator="\n", strip=True).replace("|", "\n")

    voice_parts: list[str] = []
    screen_parts: list[str] = []
    found: list[dict] = []

    matches = list(_ALL_LABELS_RE.finditer(plain))
    for idx, m in enumerate(matches):
        label = m.group(1)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(plain)
        raw_val = plain[start:end].strip()
        # el valor puede traer saltos: quédate con la primera parte útil
        raw_val = re.split(r"\n", raw_val)[0] if "\n" in raw_val else raw_val
        val = _clean_value(raw_val)
        if not val or len(val) < 2:
            continue
        # ignora falsos positivos típicos
        if re.match(r"^(dlpsgame|downloadgameps3|guide|tool|multi\s*$)", val, re.IGNORECASE):
            continue
        kind = _label_kind(label)
        found.append({"label": label, "kind": kind, "value": val})
        if kind == "voice":
            voice_parts.append(val)
        else:
            screen_parts.append(val)

    # Fallback por líneas (por si el html venía muy roto)
    if not voice_parts and not screen_parts:
        for ln in lines:
            mm = re.match(r"^\s*(.+?)\s*[:：]\s*(.+)$", ln)
            if not mm:
                continue
            lab, val = mm.group(1).strip().lower(), _clean_value(mm.group(2))
            if len(val) < 2:
                continue
            # normaliza etiqueta: ¿contiene palabra de voz o de texto?
            if any(w in lab for w in ["voice", "voi", "void", "audio", "dub", "doblaje", "voz", "voces"]):
                voice_parts.append(val)
            elif any(w in lab for w in ["screen", "sub", "text", "lang", "idiom", "langu", "menu", "interface"]):
                screen_parts.append(val)

    voice = ", ".join(dict.fromkeys(voice_parts))
    screen = ", ".join(dict.fromkeys(screen_parts))
    return {"voice_raw": voice.strip(), "screen_raw": screen.strip(), "lines": lines, "full_text": full, "labels_found": found}


def spanish_flags(voice: str, screen: str) -> dict:
    combined = f"{voice}\n{screen}"
    low = combined.lower()
    vlow = voice.lower()
    slow = screen.lower()

    def has(*terms):
        return any(t.lower() in low for t in terms)

    def has_v(*terms):
        return any(t.lower() in vlow for t in terms)

    def has_s(*terms):
        return any(t.lower() in slow for t in terms)

    ES_TERMS = ("spanish", "español", "espanol", "españa", "espana", "castellano")
    # España: suele aparecer como "Spanish (Spain)" o "Spanish (España)".
    spain = has("spanish (spain)", "spanish(spain)", "español (españa)", "espanol (espana)", "spanish spain", "spain", "españa", "espana", "castellano", "es (es)", "es-es")
    # México / Latino
    mexico = has("spanish (mexico)", "spanish(mexico)", "español (méxico)", "español (mexico)", "espanol (mexico)", "mexico", "méxico", "latam", "latin", "latino", "es (mx)", "es-mx", "spanish (latam)", "latin american spanish")
    # Cualquier mención a español
    any_es = has(*ES_TERMS)

    # ¿En voz (doblaje) o solo en textos?
    es_in_voice = any(t in vlow for t in ES_TERMS)
    es_in_screen = any(t in slow for t in ES_TERMS)

    # Etiqueta rápida
    if es_in_voice and ("spain" in vlow or "españa" in vlow):
        resumen = "ES doblaje España"
    elif es_in_voice and ("mexico" in vlow or "méxico" in vlow or "latin" in vlow):
        resumen = "ES doblaje Mexicano/Latino"
    elif es_in_voice:
        resumen = "ES doblaje (variante sin especificar)"
    elif es_in_screen and ("spain" in slow or "españa" in slow):
        resumen = "ES solo textos España"
    elif es_in_screen and ("mexico" in slow or "méxico" in slow):
        resumen = "ES solo textos México"
    elif es_in_screen:
        resumen = "ES solo textos (variante sin especificar)"
    elif any_es:
        resumen = "Mención ES (revisar)"
    else:
        resumen = "Sin español"

    return {
        "has_spanish_any": bool(any_es),
        "has_spain": bool(spain),
        "has_mexico_latino": bool(mexico),
        "spanish_in_voice": bool(es_in_voice),
        "spanish_in_screen": bool(es_in_screen),
        "spanish_resumen": resumen,
    }


REGIONES_VALIDAS = {
    "EUR", "USA", "US", "EU", "PAL", "NTSC",
    "ASIA", "AS", "JPN", "JP", "JAP", "KOR", "KOREA",
    "CHN", "CHINA", "HK", "HKG", "TW", "TWN",
    "UK", "UE", "EUROPA", "AMERICA", "LATAM",
}

HEADER_RE_V2 = re.compile(
    r"((?:CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)\s*-?\s*\d{5})\s*[–\-—:]?\s*([A-Za-z]{2,4})?\s*(.*)",
    re.IGNORECASE,
)


def _parse_header_text(txt: str) -> list[dict]:
    out = []
    # solo una cabecera por <p> (la primera). finditer daría falsos con "Do..." etc.
    m = HEADER_RE_V2.match(txt.strip())
    if not m:
        return out
    raw_cusa = clean_cusa(m.group(1))
    region_raw = (m.group(2) or "").strip().upper()
    rest = (m.group(3) or "").strip()
    # valida región: si hay región pero no es conocida, no es bloque de descarga
    # ej: "CUSA00663- Do I need..." -> region DO -> descartar
    if region_raw and region_raw not in REGIONES_VALIDAS:
        # caso especial: "CUSA00663 – USA (v1.06)" ok; "CUSA00663- Do..." no
        # si rest empieza con versión/uploader válido pero región rara, igual descartamos
        return out
    # si no hay región pero el resto parece versión, igual lo aceptamos como CUSA sin región
    # pero si el resto es una frase larga ("Works PS4Pro..."), descartar
    if not region_raw and rest:
        if len(rest.split()) > 6 or re.match(r"^(Works|Please|can you|Do I|This is|Este es)", rest, re.IGNORECASE):
            return out
    out.append({
        "header_text": txt,
        "cusa": raw_cusa,
        "region": region_raw,
        "uploader": rest[:200],
    })
    return out


def _inner_cusa(decoded_html: str) -> tuple[str, str]:
    """CUSA + región que viene DENTRO del payload (siempre trae 'CUSAxxxxx – EUR')."""
    if not decoded_html:
        return "", ""
    soup = BeautifulSoup(decoded_html, "lxml")
    txt = soup.get_text(separator=" ", strip=True)
    m = re.search(
        r"\b((?:CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)\s*-?\s*\d{5})\s*[–\-—]?\s*([A-Za-z]{2,4})?",
        txt, re.IGNORECASE,
    )
    if not m:
        return "", ""
    cusa = clean_cusa(m.group(1))
    region = (m.group(2) or "").upper()
    if region and region not in REGIONES_VALIDAS:
        region = ""
    return cusa, region


def parse_game_page(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    # Título
    title_tag = soup.find("h1", class_=re.compile(r"post-title|entry-title"))
    if not title_tag:
        title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else urlparse(url).path.strip("/")

    # Portada: og:image, si no primera imagen de la ficha
    cover = ""
    try:
        og = soup.find("meta", attrs={"property": "og:image"})
        if og and og.get("content"):
            cover = og["content"].strip()
        if not cover:
            _post_img = soup.find("div", class_=re.compile(r"post-body|entry-content"))
            _im = _post_img.find("img", src=True) if _post_img else soup.find("img", src=True)
            if _im:
                cover = _im.get("src", "").strip()
    except Exception:
        cover = ""

    # Tabla NAME/LANGUAGE/RELEASE/GENRE (la de arriba, poco fiable para idiomas)
    ficha = {}
    for tr in soup.find_all("tr"):
        tds = [td.get_text(separator=" ", strip=True) for td in tr.find_all("td")]
        if len(tds) == 2:
            ficha[tds[0].upper()] = tds[1]
        elif len(tds) == 3:
            # primera es la imagen rowspan, ignorar
            pass

    # Bloques CUSA visibles: <p>CUSA43772 – EUR (@...)</p>
    # Solo dentro del contenido del post, NO en comentarios.
    post = soup.find("div", class_=re.compile(r"post-body|entry-content"))
    if not post:
        # fallback: el <div class="post"> pero recortando comentarios
        post = soup.find("div", class_=re.compile(r"post"))
        if post:
            # elimina comentarios / ratings para no contar los "Add CUSA..." de los comentarios
            for bad in post.find_all(id=re.compile(r"comments|respond|wpdcom|wpd-post-rating")):
                bad.decompose()
            for bad in post.find_all(class_=re.compile(r"wpdiscuz|comments-area|wpdcom")):
                bad.decompose()
    search_root = post if post else soup

    cusa_headers: list[dict] = []
    for p in search_root.find_all(["p", "h2", "h3", "strong", "span"]):
        txt = p.get_text(separator=" ", strip=True)
        if not txt:
            continue
        # evita los decodificados (están dentro de .secure-data, no aquí)
        if p.find_parent("div", class_="secure-data"):
            continue
        # Solo cabeceras reales de descarga: empiezan por CUSA/PLAS/...
        # Así ignoramos los logs tipo "8/10/2026 Add CUSA43772 – EUR..." que están
        # también en el post-body pero no tienen desplegable de idiomas.
        txt_stripped = txt.strip()
        if not re.match(r"^(?:CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)\s*-?\s*\d{5}", txt_stripped, re.IGNORECASE):
            continue
        for h in _parse_header_text(txt):
            cusa_headers.append(h)

    # Payloads base64
    payload_divs = soup.find_all("div", class_="secure-data")
    payloads = []
    for d in payload_divs:
        b64 = d.get("data-payload", "")
        if not b64:
            continue
        try:
            decoded = decode_payload(b64)
        except Exception as e:
            decoded = f"[ERROR decodificando base64: {e}]"
        payloads.append({"b64_len": len(b64), "decoded_html": decoded})

    # Bloques guiados por payload (el payload SIEMPRE trae los idiomas).
    # El header exterior aporta uploader/versión; el CUSA interior confirma.
    bloques = []
    for i, pl in enumerate(payloads):
        decoded = pl.get("decoded_html", "")
        vs = extract_voice_screen(decoded) if decoded else {"voice_raw": "", "screen_raw": "", "lines": [], "full_text": "", "labels_found": []}
        inner_cusa, inner_region = _inner_cusa(decoded)
        outer = cusa_headers[i] if i < len(cusa_headers) else {"header_text": "", "cusa": "", "region": "", "uploader": ""}
        cusa = outer.get("cusa") or inner_cusa
        region = outer.get("region") or inner_region
        # si ambos existen pero difieren, manda el exterior (es el título del bloque) pero deja rastro
        header_text = outer.get("header_text", "")
        uploader = outer.get("uploader", "")
        flags = spanish_flags(vs["voice_raw"], vs["screen_raw"])
        bloques.append({
            "indice": i + 1,
            "cusa": cusa,
            "region": region,
            "uploader": uploader,
            "header_text": header_text,
            "voice": vs["voice_raw"],
            "screen_languages": vs["screen_raw"],
            "bloque_texto": vs["full_text"],
            "etiquetas": vs.get("labels_found", []),
            "decoded_ok": bool(vs["voice_raw"] or vs["screen_raw"]),
            **flags,
        })
    # Headers sin payload (raro): consérvalos para no perder el CUSA
    for j in range(len(payloads), len(cusa_headers)):
        h = cusa_headers[j]
        flags = spanish_flags("", "")
        bloques.append({
            "indice": len(bloques) + 1,
            "cusa": h["cusa"],
            "region": h["region"],
            "uploader": h["uploader"],
            "header_text": h["header_text"],
            "voice": "",
            "screen_languages": "",
            "bloque_texto": "",
            "etiquetas": [],
            "decoded_ok": False,
            **flags,
        })

    # Resumen a nivel juego: CUSAs únicos
    cusas_unicos = sorted({b["cusa"] for b in bloques if b["cusa"]})

    return {
        "page_url": url,
        "game_title": title,
        "cover": cover,
        "ficha_tabla": ficha,
        "num_bloques": len(bloques),
        "cusas_unicos": cusas_unicos,
        "bloques": bloques,
    }


def verify_one(url: str, verbose: bool = True) -> dict:
    html = fetch(url)
    data = parse_game_page(html, url)
    if verbose:
        print(f"\n{'='*70}")
        print(f"Juego: {data['game_title']}")
        print(f"URL  : {data['page_url']}")
        print(f"Bloques encontrados: {data['num_bloques']} | CUSAs: {', '.join(data['cusas_unicos']) or 'NINGUNO'}")
        print(f"{'='*70}")
        if not data["bloques"]:
            print("!! No se encontró ningún CUSA ni payload. Revisar manual.")
        for b in data["bloques"]:
            print(f"\n--- Bloque {b['indice']} ---")
            print(f"{b['cusa'] or '?CUSA?'} – {b['region'] or '?REGION?'} {b['uploader']}")
            if not b["cusa"]:
                print("   [AVISO] Bloque sin CUSA detectable")
            print(f"Voice : {b['voice'] or '[NO ENCONTRADO]'}")
            print(f"Screen: {b['screen_languages'] or '[NO ENCONTRADO]'}")
            print(f"ES    : {b['spanish_resumen']}")
            if not b["decoded_ok"]:
                print("   [AVISO] payload vacío o sin Voice/Screen, verificar manual")
    return data


def extract_game_links_from_list(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    links: list[tuple[str, str]] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if "dlpsgame.com" not in href:
            continue
        if any(x in href for x in ("/category/", "/tag/", "/author/", "/page/", "wp-content", "wp-login", "#", "?s=", "/guide-", "/dmca", "/list-all-game-ps", "/list-game-ps")):
            # OJO: list-all-game-ps4 es la propia página índice, la excluimos,
            # pero las fichas sí nos valen aunque contengan "ps4"
            if "list-all-game" in href or "list-game-ps" in href:
                continue
        # nos quedamos con fichas: /algo-ps4.../ , /algo...pkg/ , etc.
        # La lista usa /nombre-ps4-pkg/ y /nombre-ps4-download-free/
        if not re.search(r"dlpsgame\.com/[^/]+/?$", href):
            continue
        txt = a.get_text(strip=True)
        if not txt or len(txt) < 2:
            continue
        if href in seen:
            continue
        seen.add(href)
        links.append((txt, href))
    return links


def crawl_all(out_dir: Path, delay: float = 1.2, limit: int = 0, offset: int = 0, resume: bool = True):
    out_dir.mkdir(parents=True, exist_ok=True)
    list_url = "https://dlpsgame.com/list-all-game-ps4/"
    print(f"Descargando índice: {list_url}")
    html = fetch(list_url)
    links = extract_game_links_from_list(html)
    print(f"Enlaces en índice: {len(links)}")
    if offset:
        links = links[offset:]
        print(f"Offset {offset} -> quedan {len(links)}")
    if limit:
        links = links[:limit]
        print(f"Limitado a: {len(links)} (offset {offset})")

    # progreso previo
    done_file = out_dir / "progreso.json"
    done: dict = {}
    if resume and done_file.exists():
        try:
            done = json.loads(done_file.read_text(encoding="utf-8"))
            print(f"Reanudando, ya hechos: {len(done)}")
        except Exception:
            done = {}

    rows: list[dict] = []
    # carga filas previas si existen para no perderlas
    csv_path = out_dir / "cusa_idiomas.csv"
    json_path = out_dir / "cusa_idiomas.json"

    for idx, (name, url) in enumerate(links, 1):
        if url in done and resume:
            # reconstruye fila desde done para el csv final
            for b in done[url].get("bloques", []):
                rows.append(flat_row(done[url], b))
            continue
        print(f"[{idx}/{len(links)}] {name} -> {url}")
        try:
            page_html = fetch(url)
            data = parse_game_page(page_html, url)
            # si el título de la lista es mejor, lo guardamos también
            if name and len(name) > len(data["game_title"]):
                data["game_title_lista"] = name
            done[url] = data
            for b in data["bloques"]:
                rows.append(flat_row(data, b))
            if not data["bloques"]:
                rows.append(flat_row(data, {"indice": 0, "cusa": "", "region": "", "uploader": "", "header_text": "", "voice": "", "screen_languages": "", "bloque_texto": "", "decoded_ok": False, "has_spanish_any": False, "has_spain": False, "has_mexico_latino": False, "spanish_in_voice": False, "spanish_in_screen": False, "spanish_resumen": "SIN DATOS"}))
        except Exception as e:
            print(f"  !! Error: {e}")
            err = {"page_url": url, "game_title": name, "error": str(e), "bloques": []}
            done[url] = err
            rows.append({"juego": name, "url": url, "cusa": "", "region": "", "uploader": "", "voice": "", "screen_languages": "", "es_resumen": f"ERROR: {e}", "bloque": 0})
        # guardado incremental cada 10
        if idx % 10 == 0:
            done_file.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
            write_csv_json(rows, csv_path, json_path)
        time.sleep(delay)

    done_file.write_text(json.dumps(done, ensure_ascii=False, indent=1), encoding="utf-8")
    write_csv_json(rows, csv_path, json_path)
    print(f"\nHecho. Filas: {len(rows)}")
    print(f"CSV : {csv_path}")
    print(f"JSON: {json_path}")
    print(f"Progreso: {done_file}")


def flat_row(data: dict, b: dict) -> dict:
    return {
        "juego": data.get("game_title", ""),
        "cover": data.get("cover", ""),
        "url": data.get("page_url", ""),
        "bloque": b.get("indice", ""),
        "cusa": b.get("cusa", ""),
        "region": b.get("region", ""),
        "uploader": b.get("uploader", ""),
        "voice": b.get("voice", ""),
        "screen_languages": b.get("screen_languages", ""),
        "es_resumen": b.get("spanish_resumen", ""),
        "es_any": b.get("has_spanish_any", False),
        "es_spain": b.get("has_spain", False),
        "es_mexico": b.get("has_mexico_latino", False),
        "es_en_voz": b.get("spanish_in_voice", False),
        "es_en_textos": b.get("spanish_in_screen", False),
    }


def build_agrupado(rows: list[dict]) -> dict:
    """Agrupa por CUSA colapsando duplicados: 3 bloques iguales -> 1 variante.
    Esto es lo que hace viable miles de juegos en GitHub Pages."""
    agg: dict = {}
    for r in rows:
        cusa = (r.get("cusa") or "").upper()
        if not cusa:
            continue
        e = agg.setdefault(cusa, {
            "cusa": cusa,
            "region": r.get("region", ""),
            "juegos": set(),
            "urls": set(),
            "variantes": {},
        })
        if not e["region"] and r.get("region"):
            e["region"] = r["region"]
        if r.get("juego"):
            e["juegos"].add(r["juego"])
        if r.get("url"):
            e["urls"].add(r["url"])
        key = ((r.get("voice") or "").strip(), (r.get("screen_languages") or "").strip())
        v = e["variantes"].setdefault(key, {
            "voice": r.get("voice", ""),
            "screen": r.get("screen_languages", ""),
            "es_resumen": r.get("es_resumen", ""),
            "es_any": r.get("es_any", False),
            "es_spain": r.get("es_spain", False),
            "es_mexico": r.get("es_mexico", False),
            "es_en_voz": r.get("es_en_voz", False),
            "es_en_textos": r.get("es_en_textos", False),
            "uploaders": set(),
            "ejemplos": set(),
        })
        if r.get("uploader"):
            v["uploaders"].add(r["uploader"][:120])
        if r.get("url"):
            v["ejemplos"].add(r["url"])
    # a listas ordenadas
    out = {}
    for cusa, e in sorted(agg.items()):
        out[cusa] = {
            "cusa": cusa,
            "region": e["region"],
            "juegos": sorted(e["juegos"]),
            "urls": sorted(e["urls"]),
            "num_variantes": len(e["variantes"]),
            "variantes": [
                {**v, "uploaders": sorted(v["uploaders"])[:6], "ejemplos": sorted(v["ejemplos"])[:3]}
                for v in e["variantes"].values()
            ],
        }
    return out


def write_csv_json(rows: list[dict], csv_path: Path, json_path: Path):
    if not rows:
        return
    fields = ["juego", "cover", "url", "bloque", "cusa", "region", "uploader", "voice", "screen_languages", "es_resumen", "es_any", "es_spain", "es_mexico", "es_en_voz", "es_en_textos"]
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    # JSON completo (bonito) + minificado (el que usa el sitio, pesa la mitad)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    min_path = json_path.with_name(json_path.stem + ".min.json")
    with open(min_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, separators=(",", ":"))
    # Agrupado por CUSA (ideal para miles: colapsa duplicados)
    agg = build_agrupado(rows)
    agg_path = json_path.with_name("cusa_agrupado.json")
    with open(agg_path, "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, indent=1)
    agg_min = json_path.with_name("cusa_agrupado.min.json")
    with open(agg_min, "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, separators=(",", ":"))
    print(f"Agrupados: {len(agg)} CUSAs únicos -> {agg_path.name} + {agg_min.name} (+ {min_path.name})")


def search_dlpsgame(query: str, max_results: int = 5) -> list[tuple[str, str]]:
    """Consulta en vivo a dlpsgame con ?s=CUSAxxxxx y devuelve [(titulo, url)]."""
    q = query.strip()
    # normaliza: 43772 -> CUSA43772 para buscar
    m = re.search(r"(CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)\s*-?\s*(\d{5})", q, re.IGNORECASE)
    if m:
        q = clean_cusa(m.group(1) + m.group(2))
        # asegura prefijo + dígitos juntos: CUSA43772
        q = re.sub(r"\s+", "", q.upper())
        if re.match(r"^\d{5}$", q):
            q = "CUSA" + q
    elif re.match(r"^\d{5}$", q.strip()):
        q = "CUSA" + q.strip()
    url = f"https://dlpsgame.com/?s={q}"
    html = fetch(url)
    soup = BeautifulSoup(html, "lxml")
    out: list[tuple[str, str]] = []
    seen = set()
    # resultados: h2/h3 con link, o cualquier link a ficha
    SKIP = ("/category/", "list-all", "list-game", "/daily-update", "/guide-", "/dmca", "/contact")
    for h in soup.find_all(["h2", "h3"]):
        a = h.find("a", href=True)
        if not a:
            continue
        href = a["href"].strip()
        if "dlpsgame.com" not in href or any(s in href for s in SKIP):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append((a.get_text(strip=True), href))
        if len(out) >= max_results:
            break
    if not out:
        # fallback: cualquier link a ficha con texto
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if "dlpsgame.com" not in href:
                continue
            if any(x in href for x in ("/category/", "/tag/", "/author/", "/page/", "wp-content", "wp-login", "#", "?s=", "/guide-", "/dmca", "/list-all-game", "/list-game-ps")):
                continue
            if not re.search(r"dlpsgame\.com/[^/]+/?$", href):
                continue
            txt = a.get_text(strip=True)
            if not txt or len(txt) < 3 or txt.lower().startswith(("ps5", "ps4", "ps3", "ps2")) and len(txt) < 6:
                continue
            if href in seen:
                continue
            seen.add(href)
            out.append((txt, href))
            if len(out) >= max_results:
                break
    return out


def live_lookup(cusa_query: str, verbose: bool = True) -> dict | None:
    nc = norm_cusa_query(cusa_query)
    if verbose:
        print(f"Buscando en vivo: {cusa_query} -> {nc} ...")
    cands = search_dlpsgame(nc, max_results=5)
    if not cands:
        if verbose:
            print(f"Sin resultados en dlpsgame para {nc}. Prueba en https://dlpsgame.com/?s={nc}")
        return None
    if verbose:
        print(f"Candidatas: {len(cands)}")
        for t, u in cands:
            print(f" - {t} -> {u}")
    # trae la primera y filtra por CUSA pedido
    all_data = []
    for title, url in cands[:3]:
        try:
            if verbose:
                print(f"\nDescargando ficha: {url}")
            data = verify_one(url, verbose=False)
            # filtra bloques al CUSA pedido (pero muestra aviso si hay otros)
            wanted = [b for b in data["bloques"] if b["cusa"].upper() == nc.upper()]
            resto = [b for b in data["bloques"] if b["cusa"].upper() != nc.upper()]
            data["bloques_filtrados"] = wanted
            data["otros_cusas"] = sorted({b["cusa"] for b in resto if b["cusa"]})
            all_data.append(data)
            if verbose:
                if not wanted:
                    print(f"!! La ficha {title} no trae {nc} (trae {', '.join(data['cusas_unicos'])}). Mostrando igual.")
                    for b in data["bloques"]:
                        print(f"  {b['cusa']} – {b['region']} | Voice:{b['voice'][:60]} | Screen:{b['screen_languages'][:80]} | {b['spanish_resumen']}")
                else:
                    print(f"== {nc} en {data['game_title']} ==")
                    for b in wanted:
                        print(f"  {b['cusa']} – {b['region']} {b['uploader']}")
                        print(f"  Voice : {b['voice'] or '[NO ENCONTRADO]'}")
                        print(f"  Screen: {b['screen_languages'] or '[NO ENCONTRADO]'}")
                        print(f"  ES    : {b['spanish_resumen']}")
            # si la primera ya dio el CUSA, basta
            if wanted:
                break
        except Exception as e:
            if verbose:
                print(f"  !! Error con {url}: {e}")
    return all_data[0] if all_data else None


def norm_cusa_query(s: str) -> str:
    s = (s or "").upper().strip().replace(" ", "").replace("-", "").replace("_", "")
    m = re.search(r"(CUSA|PLAS|PCAS|PLJM|PCJS|PPSA|PPAS)(\d{5})", s)
    if m:
        return m.group(1) + m.group(2)
    if re.match(r"^\d{5}$", s):
        return "CUSA" + s
    return s.upper()


def main():
    ap = argparse.ArgumentParser(description="Recompila CUSA + idiomas de dlpsgame PS4")
    ap.add_argument("--one", help="Verifica un solo juego (URL completa)")
    ap.add_argument("--all", action="store_true", help="Recompila todo desde list-all-game-ps4")
    ap.add_argument("--from-file", dest="from_file", help="Archivo con URLs (una por línea)")
    ap.add_argument("--out", default="data", help="Carpeta de salida (defecto: data)")
    ap.add_argument("--delay", type=float, default=1.2, help="Pausa entre descargas (seg)")
    ap.add_argument("--limit", type=int, default=0, help="Limita a N juegos (pruebas)")
    ap.add_argument("--offset", type=int, default=0, help="Empieza en N (lotes: 0-500, 500-1000...)")
    ap.add_argument("--no-resume", action="store_true", help="No reanudar, empezar de cero")
    ap.add_argument("--search", "--cusa", dest="search", help="Consulta en vivo por CUSA: busca en dlpsgame ?s=CUSA y filtra (ej. CUSA43772 o 43772)")
    ap.add_argument("--lista", action="store_true", help="Recopila lista sencilla juego+enlace a data/juegos.json")
    args = ap.parse_args()

    if args.lista:
        print("Descargando lista...")
        html = fetch("https://dlpsgame.com/list-all-game-ps4/")
        links = extract_game_links_from_list(html)
        # filtra portadas/guías
        links = [(t, u) for t, u in links if not any(b in u for b in ("/daily-update", "/guide-", "/dmca", "/contact"))]
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        rows = [{"juego": t, "url": u} for t, u in links]
        (out / "juegos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "juegos.min.json").write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"Juegos: {len(rows)} -> {out / 'juegos.json'}")
        return

    if args.search:
        data = live_lookup(args.search, verbose=True)
        if data:
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            p = out / f"vivo_{norm_cusa_query(args.search)}.json"
            p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"\nGuardado en: {p}")
        return

    if args.one:
        data = verify_one(args.one)
        # guarda también el detalle en json para tener la prueba exacta
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9]+", "_", data["game_title"])[:60] or "juego"
        p = out / f"uno_{safe}.json"
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nDetalle guardado en: {p}")
        return

    if args.from_file:
        urls = [l.strip() for l in Path(args.from_file).read_text(encoding="utf-8").splitlines() if l.strip().startswith("http")]
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        rows = []
        for i, u in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] {u}")
            try:
                d = verify_one(u, verbose=True)
                for b in d["bloques"]:
                    rows.append(flat_row(d, b))
            except Exception as e:
                print(f"  !! Error: {e}")
                rows.append({"juego": u, "url": u, "es_resumen": f"ERROR: {e}"})
            time.sleep(args.delay)
        write_csv_json(rows, out_dir / "cusa_idiomas.csv", out_dir / "cusa_idiomas.json")
        print(f"\nGuardado en {out_dir}")
        return

    if args.all:
        crawl_all(Path(args.out), delay=args.delay, limit=args.limit, offset=args.offset, resume=not args.no_resume)
        return

    ap.print_help()


if __name__ == "__main__":
    main()
