// Translate a thrown error from the API client. Known kinds:
//   - "unknownEndpoint": SPA fallback served HTML (route doesn't exist yet)
//   - "wrongPassword": /api/secrets/unlock returned 401
// Everything else falls back to the raw `e.message` the server returned.
//
// Usage:
//   const { t } = useTranslation();
//   catch (e) { setError(formatError(e, t)); }
export function formatError(err, t) {
  if (err && err.kind === "unknownEndpoint") {
    return t("api.unknownEndpoint", { path: err.path });
  }
  if (err && err.kind === "wrongPassword") {
    return t("secrets.wrongPassword");
  }
  return err?.message || String(err);
}
