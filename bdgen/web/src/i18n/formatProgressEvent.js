// Translate a progress event coming from the Python engine.
//
// Backend events carry a French ``message`` for legacy CLI/log compatibility,
// but image-generation events also include an ``extra.i18n_key`` and any
// interpolation params alongside it (e.g. ``name``). When that key is
// present, we render the localized string for the current UI language and
// fall back to the raw ``event.message`` otherwise so unknown / not-yet-
// translated events keep working.
//
// Usage:
//   const { t } = useTranslation();
//   <div>{formatProgressEvent(event, t)}</div>
export function formatProgressEvent(event, t) {
  if (!event) return "";
  const extra = event.extra || {};
  const key = extra.i18n_key;
  if (key) {
    return t(key, { ...extra, defaultValue: event.message || "" });
  }
  return event.message || "";
}
