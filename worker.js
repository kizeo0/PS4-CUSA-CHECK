// worker.js — Proxy mínimo para consulta CUSA en vivo (Cloudflare Workers, gratis)
// Despliegue: workers.dev → New Worker → pega esto → Deploy
// Uso desde el sitio: https://TU-WORKER.workers.dev?url=https://dlpsgame.com/?s=CUSA43772
// O guarda la URL en el sitio con ?worker=https://TU-WORKER.workers.dev
export default {
  async fetch(req) {
    const u = new URL(req.url);
    const cors = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, OPTIONS",
      "Access-Control-Allow-Headers": "*",
    };
    if (req.method === "OPTIONS") return new Response(null, { headers: cors });
    let target = u.searchParams.get("url");
    const s = u.searchParams.get("s");
    if (!target && s) target = "https://dlpsgame.com/?s=" + encodeURIComponent(s);
    if (!target) return new Response("Falta ?url=", { status: 400, headers: cors });
    try {
      const allowed = /^https:\/\/(dlpsgame\.com|downloadgameps3\.net)(\/|$|\?)/;
      const t = new URL(target);
      if (!allowed.test(t.href) && !t.href.startsWith("https://dlpsgame.com/")) {
        // por seguridad solo dlpsgame + filecrypt espejos de la ficha
        if (!t.hostname.endsWith("dlpsgame.com")) {
          return new Response("Dominio no permitido", { status: 403, headers: cors });
        }
      }
      const r = await fetch(target, {
        headers: {
          "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124 Safari/537.36",
          "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
          "Accept": "text/html,*/*",
          "Referer": "https://dlpsgame.com/",
        },
      });
      const txt = await r.text();
      return new Response(txt, {
        status: r.status,
        headers: { ...cors, "Content-Type": "text/html; charset=utf-8", "Cache-Control": "public, max-age=300" },
      });
    } catch (e) {
      return new Response("Error proxy: " + e.message, { status: 500, headers: cors });
    }
  },
};
