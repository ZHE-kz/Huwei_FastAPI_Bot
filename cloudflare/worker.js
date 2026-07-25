export default {
  async fetch(request, env) {
    const incoming = new URL(request.url);
    const origin = new URL(env.ORIGIN_URL);
    origin.pathname = incoming.pathname;
    origin.search = incoming.search;
    return fetch(new Request(origin, request));
  },
};