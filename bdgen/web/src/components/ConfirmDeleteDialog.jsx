import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

/**
 * Confirmation dialog for destructive actions on script entities.
 *
 * Props:
 *   - title, body: text to display
 *   - loadPreview: optional async () => {pages_dropped, earliest_affected}
 *   - onConfirm: async () => any — actually deletes
 *   - onClose
 *   - confirmLabel
 */
export default function ConfirmDeleteDialog({
  title,
  body,
  loadPreview,
  onConfirm,
  onClose,
  confirmLabel,
}) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!loadPreview) return;
    setLoadingPreview(true);
    loadPreview()
      .then(setPreview)
      .catch((e) => setError(e.message))
      .finally(() => setLoadingPreview(false));
  }, [loadPreview]);

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

  const cascade = preview && preview.pages_dropped > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
      <div className="card p-6 w-full max-w-md space-y-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        {body && <p className="text-sm text-[var(--color-ink-soft)]">{body}</p>}

        {loadingPreview && (
          <p className="text-xs text-[var(--color-mute)]">
            {t("dialogs.confirmDelete.loadingImpact")}
          </p>
        )}

        {preview && (
          <div
            className={
              "text-sm rounded-md p-3 " +
              (cascade
                ? "bg-[var(--color-peach-100)] border border-[var(--color-peach-300)] text-[var(--color-peach-500)]"
                : "bg-[var(--color-mint-100)] border border-[var(--color-mint-200)] text-[var(--color-mint-700)]")
            }
          >
            {cascade ? (
              <>
                <div className="font-semibold mb-1">
                  {t("dialogs.confirmDelete.cascadeTitle")}
                </div>
                <div>
                  {t("dialogs.confirmDelete.cascadeBody", {
                    count: preview.pages_dropped,
                    from: preview.earliest_affected,
                  })}
                </div>
                <div className="mt-1 text-xs">
                  {t("dialogs.confirmDelete.cascadeFootnote")}
                </div>
              </>
            ) : (
              <>{t("dialogs.confirmDelete.noImpact")}</>
            )}
          </div>
        )}

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
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={handleConfirm}
            disabled={submitting || loadingPreview}
          >
            {submitting
              ? t("dialogs.confirmDelete.deleting")
              : cascade
              ? t("dialogs.confirmDelete.deleteAndRegen")
              : confirmLabel ?? t("common.delete")}
          </button>
        </div>
      </div>
    </div>
  );
}
