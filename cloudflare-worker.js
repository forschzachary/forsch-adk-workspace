/**
 * Cloudflare Worker — graph.forschfrontiers.com edge router
 *
 * Routes:
 *   /chat/*  → http://87.99.149.222:8888  (serve.py — Hubert chat)
 *   /*        → http://87.99.149.222:8888  (serve.py — Live Agent Graph)
 *
 * CHAT_TOKEN is injected server-side (Worker env var) — the browser never sees it.
 * WebSocket passthrough is native to Cloudflare Workers — no special handling needed.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // All traffic → serve.py on port 8888
    const target = new URL(url.pathname + url.search, 'http://87.99.149.222:8888');

    // Inject CHAT_TOKEN for /chat endpoints
    if (url.pathname.startsWith('/chat') && env.CHAT_TOKEN) {
      target.searchParams.set('chat_token', env.CHAT_TOKEN);
    }

    return fetch(target.toString(), request);
  }
};
