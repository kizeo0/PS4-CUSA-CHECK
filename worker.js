// CUSA CHECK — proxy propio en Cloudflare Workers (gratis)
// 1) Entra a dash.cloudflare.com → Workers & Pages → Create → Create Worker
// 2) Borra todo, pega este archivo, Deploy
// 3) Copia tu URL: https://TU-NOMBRE.TU-CUENTA.workers.dev
// 4) Abre tu sitio una vez así y queda guardado:
//    https://TU-USUARIO.github.io/TU-REPO/?worker=https://TU-NOMBRE.TU-CUENTA.workers.dev
// Desde entonces el botón Consultar usa tu worker (sin 401 ni límites).

export default {
  async fetch(req) {
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "*",
      "Access-Control-Max-Age": "86400",
    };
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

    const u = new URL(req.url);
    let target = u.searchParams.get("url");
    const s = u.searchParams.get("s");
    if (!target && s) target = "https://dlpsgame.com/?s=" + encodeURIComponent(s);

    if (!target) {
      return new Response(
        "CUSA CHECK worker OK. Usa ?url=https://dlpsgame.com/?s=CUSA43772",
        { status: 200, headers: { ...cors, "Content-Type": "text/plain; charset=utf-8" } }
      );
    }

    let t;
    try {
      t = new URL(target);
    } catch {
      return new Response("URL inválida", { status: 400, headers: cors });
    }
    if (t.protocol !== "https:" || !t.hostname.endsWith("dlpsgame.com")) {
      return new Response("Solo se permite dlpsgame.com", { status: 403, headers: cors });
    }

    try {
      const r = await fetch(t.href, {
        redirect: "follow",
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
          Referer: "https://dlpsgame.com/",
        },
      });
      const txt = await r.text();
      return new Response(txt, {
        status: r.status,
        headers: {
          ...cors,
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "public, max-age=300",
        },
      });
    } catch (e) {
      return new Response("Error proxy: " + (e && e.message ? e.message : e), {
        status: 500,
        headers: cors,
      });
    }
  },
};
