/**
 * Service Worker — cache de assets estáticos do Next.js.
 *
 * Motivação:
 * A volta do fluxo OAuth (gov.br → Keycloak → callback) deixa a conexão
 * HTTP/2 do browser com o origin idle por dezenas de segundos. A camada de
 * borda (gateway/edge) encerra essa conexão; o browser então reutiliza a
 * conexão morta para buscar os chunks `/_next/static/chunks/*.js` e recebe
 * 503 (text/plain), impedindo a hidratação do React e causando loading
 * infinito. Conexões novas (curl, navegação direta) funcionam normalmente.
 *
 * Estratégia:
 * - `/_next/static/*` são assets com hash de conteúdo imutável → cache-first
 *   é 100% seguro e elimina a dependência de rede após o primeiro sucesso.
 * - Cache miss → busca na rede, grava no cache.
 * - Cache hit → responde instantaneamente do cache (e atualiza em background).
 *
 * Cache versionado: bump em CACHE_VERSION invalida o cache antigo no activate.
 */

const CACHE_VERSION = "pic-static-v1";
const CACHE_NAME = `pic-static-${CACHE_VERSION}`;
const STATIC_PATHS = ["/_next/static/"];

function isStaticRequest(url) {
  return STATIC_PATHS.some((p) => url.pathname.startsWith(p));
}

self.addEventListener("install", () => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => key.startsWith("pic-static-") && key !== CACHE_NAME)
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Somente GET de assets estáticos imutáveis do Next.js.
  // Todo o restante (documentos, API, auth) passa direto pela rede.
  if (event.request.method !== "GET" || !isStaticRequest(url)) {
    return;
  }

  event.respondWith(
    (async () => {
      const cache = await caches.open(CACHE_NAME);

      const cached = await cache.match(event.request);
      if (cached) {
        // Cache hit: responde já do cache. Atualiza em background sem
        // bloquear a resposta (stale-while-revalidate para segurança extra).
        event.waitUntil(
          fetch(event.request)
            .then((response) => {
              if (response.ok) {
                cache.put(event.request, response.clone());
              }
            })
            .catch(() => {}),
        );
        return cached;
      }

      // Cache miss (primeiro acesso ou novo deploy com hash novo):
      // tenta a rede com um retry curto antes de desistir.
      try {
        const response = await fetch(event.request);
        if (response.ok) {
          cache.put(event.request, response.clone());
        }
        return response;
      } catch (firstError) {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        try {
          const response = await fetch(event.request);
          if (response.ok) {
            cache.put(event.request, response.clone());
          }
          return response;
        } catch (secondError) {
          const fallback = await cache.match(event.request);
          if (fallback) {
            return fallback;
          }
          throw secondError;
        }
      }
    })(),
  );
});
