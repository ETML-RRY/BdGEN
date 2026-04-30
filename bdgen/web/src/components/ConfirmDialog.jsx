import { useState } from "react";

export default function ConfirmDialog({
  title,
  body,
  confirmLabel = "Confirmer",
  cancelLabel = "Annuler",
  variant = "primary",
  onConfirm,
  onClose,
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  async function handleConfirm() {
    setError(null);
    setSubmitting(true);
    try {
      await onConfirm();
      onClose();
    } catch (e) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
      <div className="card p-6 w-full max-w-md space-y-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        {body && <p className="text-sm text-[var(--color-ink-soft)]">{body}</p>}
        {error && (
          <p className="text-sm text-[var(--color-rose-500)]">{error}</p>
        )}
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            disabled={submitting}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            className={`btn ${variant === "danger" ? "btn-danger" : "btn-primary"}`}
            onClick={handleConfirm}
            disabled={submitting}
          >
            {submitting ? "En cours…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
