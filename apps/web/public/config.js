// Overwritten at deploy time (S3 sync, SWA upload, or docker entrypoint).
// Keep the compose default here so `pnpm dev` works out of the box.
window.__CRV_CONFIG__ = { apiBaseUrl: "http://localhost:8080" };
