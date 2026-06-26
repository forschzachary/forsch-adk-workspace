/**
 * Cloudflare Worker — graph.forschfrontiers.com edge router
 *
 * Routes:
 *   /chat/*  → http://87.99.149.222:8800  (ADK bridge / Gradio)
 *   /*        → http://87.99.149.222:8888  (Live Agent Graph server)
 *
 * CHAT_TOKEN is injected server-side (Worker env var) — the browser never sees it.
 * WebSocket passthrough is native to Cloudflare Workers — no special handling needed.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/chat')) {
      const target = new URL(url.pathname + url.search, 'http://87.99.149.222:8800');

      // Inject CHAT_TOKEN as query param (bridge token-bridge middleware reads it)
      if (env.CHAT_TOKEN) {
        target.searchParams.set('chat_token', env.CHAT_TOKEN);
      }

      return fetch(target.toString(), request);
    }

    // Everything else → graph server
    const target = new URL(url.pathname + url.search, 'http://87.99.149.222:8888');
    return fetch(target.toString(), request);
  }
};
