# Verifica CUSA PS4 — qué idiomas trae

Sitio sencillo de consulta por CUSA. Pones el CUSA y te dice qué puede traer según la info de dlpsgame (Voice/Audio + Screen/Subtitles decodificados tal cual, verificación exacta).

- `index.html` → sitio para GitHub Pages (base local + botón **En vivo**)
- `worker.js` → proxy propio para En vivo en GitHub (Cloudflare Workers, gratis)
- `data/cusa_idiomas.json` → base local que lee el sitio
- `verify_cusa.py` → recompila + consulta en vivo exacta en local

## Sitio: base + en vivo

1. **Base sencilla (lista + enlace):** `data/juegos.json` con 6488 juegos. Al escribir un nombre salen 30 con botón **Ver idiomas**: carga su ficha de dlpsgame, filtra la sección CUSA y tira nombre + idiomas en vivo.
2. **Por CUSA directo:** escribe `CUSA43772` → **Consultar** (caché) o **En vivo** (ficha actual, filtra al CUSA pedido).
3. Refresca la lista con `py verify_cusa.py --lista --out data`.

## Usar el sitio en local

```powershell
cd "C:\Users\WinterOS\Desktop\verify cusa ps4"
py -m http.server 8000
# abre http://localhost:8000
```

Busca `CUSA43772`, `43772`, `CUSA00605`, o por nombre `mortuary`.

## Recompilar más juegos

Verificación exacta de uno:

```powershell
py verify_cusa.py --one "https://dlpsgame.com/the-mortuary-assistant-ps4-pkg/" --out data
```

Varios desde archivo:

```powershell
py verify_cusa.py --from-file urls.txt --out data --delay 1.2
```

Todo PS4 (tarda, son miles; reanuda solo con `data/progreso.json`):

```powershell
py verify_cusa.py --all --out data --delay 1.2
# prueba con 20 primero:
py verify_cusa.py --all --out data --limit 20
```

Después de recompilar, regenera el JSON del sitio:

```powershell
py -c "import json,pathlib,glob; from verify_cusa import flat_row; rows=[]; [rows.extend([flat_row(d,b) for b in (json.loads(pathlib.Path(f).read_text(encoding='utf-8'))).get('bloques',[]))]) or True for f in [0] ]; "
```

Mejor: el `--all` y `--from-file` ya escriben `data/cusa_idiomas.json` solos. El `--one` escribe `data/uno_*.json`; júntalos así:

```powershell
py -c "import json,pathlib,glob; from verify_cusa import flat_row; rows=[]; exec(\"for f in glob.glob('data/uno_*.json'):\n d=json.loads(pathlib.Path(f).read_text(encoding='utf-8'))\n for b in d.get('bloques',[]): rows.append(flat_row(d,b))\npathlib.Path('data/cusa_idiomas.json').write_text(json.dumps(rows,ensure_ascii=False,indent=1),encoding='utf-8')\nprint(len(rows))\")"
```

## Variantes cubiertas

Voz (doblaje): `voice, voices, voise, voi, void, audio, audios, dub, doblaje, voz, voces, sound`
Textos: `screen languages, screen, subtitles, subs, texts, languages, lenguages (typo), idiomas, menus, interface`

Si sale `[NO ENCONTRADO]`, hay que revisar manual en la ficha original (link incluido en el resultado).

## Subir a GitHub Pages

1. Crea repo nuevo (ej. `verifica-cusa-ps4`), sube `index.html`, `data/cusa_idiomas.json`, `.nojekyll`.
2. En GitHub: Settings → Pages → Deploy from branch → `main` / `/ (root)`.
3. Abre `https://TU-USUARIO.github.io/verifica-cusa-ps4/` y busca por CUSA.

Cada vez que recompiles, sube el `data/cusa_idiomas.json` actualizado y la web se actualiza sola.
