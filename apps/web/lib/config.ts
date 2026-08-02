// Runtime config injected via /config.js at deploy time.
// Never bake API URL into the build — one image serves every deployment.

declare global {
  interface Window { __CRV_CONFIG__?: { apiBaseUrl?: string }; }
}

export function apiBaseUrl(): string {
  if (typeof window === "undefined") return "";
  return window.__CRV_CONFIG__?.apiBaseUrl ?? "http://localhost:8080";
}
