const NON_MUTATING_METHODS = new Set(['GET', 'HEAD', 'OPTIONS']);

export function mutationRequestKey(path, init = {}) {
  const method = String(init?.method || 'GET').toUpperCase();
  if (NON_MUTATING_METHODS.has(method)) return null;

  const body = init?.body;
  if (body instanceof FormData) return null;
  if (typeof Blob !== 'undefined' && body instanceof Blob) return null;
  if (body != null && typeof body !== 'string') return null;

  const normalizedPath = String(path || '').startsWith('/') ? String(path || '') : `/${String(path || '')}`;
  return `${method}:${normalizedPath}:${body || ''}`;
}

export function createInFlightMutationRegistry() {
  const inFlight = new Map();

  return {
    get(key) {
      if (!key) return null;
      return inFlight.get(key) || null;
    },
    set(key, promise) {
      if (!key) return promise;
      inFlight.set(key, promise);
      return promise;
    },
    clear(key, promise) {
      if (!key) return;
      if (inFlight.get(key) === promise) inFlight.delete(key);
    },
    size() {
      return inFlight.size;
    },
  };
}
