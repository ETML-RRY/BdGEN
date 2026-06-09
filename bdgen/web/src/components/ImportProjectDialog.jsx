import { useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { slugify, sanitizeSlugInput } from "../utils/slugify.js";

/**
 * Dialog shown after the user picks a .bdgen file, letting them optionally
 * override the title and/or slug before the archive is actually imported.
 *
 * Props:
 *   - fileName: original filename shown as hint
 *   - onClose: () => void
 *   - onConfirm: async ({ newTitle, newProject }) => void
 */
export default function ImportProjectDialog({ fileName, onClose, onConfirm }) {
  const { t } = useTranslation();
  const [newTitle, setNewTitle] = useState("");
  const [manualSlug, setManualSlug] = useState("");
  const [slugIsManual, setSlugIsManual] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const derivedSlug = newTitle.trim() ? slugify(newTitle) : "";
  const slugValue = slugIsManual ? manualSlug : derivedSlug;

  function handleTitleChange(e) {
    setNewTitle(e.target.value);
  }

  function handleSlugChange(e) {
    const sanitized = sanitizeSlugInput(e.target.value);
    if (sanitized === "") {
      setSlugIsManual(false);
      setManualSlug("");
    } else {
      setSlugIsManual(true);
      setManualSlug(sanitized);
    }
  }

  async function handleConfirm() {
    setError(null);
    setSubmitting(true);
    try {
      await onConfirm({
        newTitle: newTitle.trim() || null,
        newProject: slugValue || null,
      });
      onClose();
    } catch (e) {
      setError(e.message);
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
      <div className="card p-6 w-full max-w-lg space-y-4">
        <div>
          <h3 className="text-lg font-semibold">{t("dialogs.import.title")}</h3>
          {fileName && (
            <p className="text-sm text-[var(--color-ink-soft)] mt-1 font-mono truncate">
              {fileName}
            </p>
          )}
        </div>

        <p className="text-sm text-[var(--color-ink-soft)]">
          {t("dialogs.import.body")}
        </p>

        <fieldset className="space-y-3">
          <legend className="sr-only">{t("dialogs.import.identityLegend")}</legend>

          <div>
            <label className="block text-xs font-medium mb-1" htmlFor="imp-title">
              <Trans
                i18nKey="dialogs.import.titleLabel"
                components={{ span: <span className="text-[var(--color-mute)] font-normal" /> }}
              />
            </label>
            <input
              id="imp-title"
              type="text"
              className="input w-full"
              placeholder={t("dialogs.import.titlePlaceholder")}
              value={newTitle}
              onChange={handleTitleChange}
              disabled={submitting}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1" htmlFor="imp-slug">
              <Trans
                i18nKey="dialogs.import.slugLabel"
                components={{ span: <span className="text-[var(--color-mute)] font-normal" /> }}
              />
            </label>
            <input
              id="imp-slug"
              type="text"
              className="input w-full font-mono text-sm"
              placeholder={t("dialogs.import.slugPlaceholder")}
              value={slugValue}
              onChange={handleSlugChange}
              disabled={submitting}
            />
            <p className="mt-1 text-xs text-[var(--color-mute)]">
              {t("dialogs.import.slugHint")}
              {!slugIsManual && derivedSlug && t("dialogs.import.slugDerived")}
            </p>
          </div>
        </fieldset>

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
            className="btn btn-primary"
            onClick={handleConfirm}
            disabled={submitting}
          >
            {submitting ? t("dialogs.import.importing") : t("dialogs.import.import")}
          </button>
        </div>
      </div>
    </div>
  );
}
