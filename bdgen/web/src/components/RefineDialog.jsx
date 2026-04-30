import { useState } from "react";

export default function RefineDialog({
  title,
  hint,
  extraField,
  onClose,
  onSubmit,
}) {
  const [text, setText] = useState("");
  const [extras, setExtras] = useState({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!text.trim()) return;
    setError(null);
    setSubmitting(true);
    try {
      await onSubmit(text.trim(), extras);
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
      <form
        onSubmit={handleSubmit}
        className="card p-6 w-full max-w-lg space-y-4"
      >
        <div>
          <h3 className="text-lg font-semibold">{title}</h3>
          {hint && (
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">{hint}</p>
          )}
        </div>
        <textarea
          autoFocus
          className="textarea min-h-[8rem]"
          placeholder="Décrivez la modification souhaitée…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />

        {extraField?.type === "checkbox" && (
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!extras[extraField.id]}
              onChange={(e) =>
                setExtras((x) => ({ ...x, [extraField.id]: e.target.checked }))
              }
            />
            <span>{extraField.label}</span>
          </label>
        )}

        {error && (
          <p className="text-sm text-[var(--color-rose-500)]">{error}</p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            disabled={submitting}
          >
            Annuler
          </button>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting || !text.trim()}
          >
            {submitting ? "Application…" : "Appliquer la retouche"}
          </button>
        </div>
      </form>
    </div>
  );
}
