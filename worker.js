// CUSA CHECK — worker para Cloudflare (pegar tal cual y Deploy)
// Conecta el sitio una vez así:
// https://kizeo0.github.io/PS4-CUSA-CHECK/?worker=https://TU-WORKER.TU-CUENTA.workers.dev

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
    const s = u.searchParams.get("s") || u.searchParams.get("q");
    if (!target && s) target = "https://dlpsgame.com/?s=" + encodeURIComponent(s);

    if (!target) {
      return new Response("CUSA CHECK worker OK. Usa ?url=https://dlpsgame.com/?s=CUSA43772", {
        status: 200,
        headers: { ...cors, "Content-Type": "text/plain; charset=utf-8" },
      });
    }

    let t;
    try {
      t = new URL(target);
    } catch {
      return new Response("URL inválida", { status: 400, headers: cors });
    }
    if (t.protocol !== "https:" || !t.hostname.endsWith("dlpsgame.com")) {
      return new Response("Solo dlpsgame.com", { status: 403, headers: cors });
    }

    try {
      const ctrl = new AbortController();
      const to = setTimeout(() => ctrl.abort(), 20000);
      const r = await fetch(t.href, {
        redirect: "follow",
        signal: ctrl.signal,
        headers: {
          "User-Agent":
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
          Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
          "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
          Referer: "https://dlpsgame.com/",
        },
      }).finally(() => clearTimeout(to));
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
      const msg = e && e.name === "AbortError" ? "timeout" : (e && e.message) || e;
      return new Response("Error proxy: " + msg, { status: 500, headers: cors });
    }
  },
};
