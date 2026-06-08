import { useState } from "react";
import { useTranslation, Trans } from "react-i18next";
import { slugify, sanitizeSlugInput } from "../utils/slugify.js";

/**
 * Dialog asking the user which elements of the source project to carry over
 * into the duplicate. The script, pages, PDF and feedback are never copied
 * — the duplicate restarts at the "Preparation" step.
 *
 * Props:
 *   - sourceLabel: friendly name shown in the title
 *   - onClose: () => void
 *   - onConfirm: async ({ newTitle, newProject, includePhotos, includeStyleReference, includeReferences }) => void
 */
export default function DuplicateProjectDialog({
  sourceLabel,
  onClose,
  onConfirm,
}) {
  const { t } = useTranslation();
  const [newTitle, setNewTitle] = useState("");
  const [manualSlug, setManualSlug] = useState("");
  const [slugIsManual, setSlugIsManual] = useState(false);
  const [includePhotos, setIncludePhotos] = useState(true);
  const [includeStyleReference, setIncludeStyleReference] = useState(true);
  const [includeReferences, setIncludeReferences] = useState(false);
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
        includePhotos,
        includeStyleReference,
        includeReferences,
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
          <h3 className="text-lg font-semibold">{t("dialogs.duplicate.title")}</h3>
          {sourceLabel && (
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              <Trans
                i18nKey="dialogs.duplicate.source"
                values={{ label: sourceLabel }}
                components={{ em: <span className="italic" /> }}
              />
            </p>
          )}
        </div>

        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold mb-1">
            {t("dialogs.duplicate.identityLegend")}
          </legend>

          <div>
            <label className="block text-xs font-medium mb-1" htmlFor="dup-title">
              <Trans
                i18nKey="dialogs.duplicate.titleLabel"
                components={{ span: <span className="text-[var(--color-mute)] font-normal" /> }}
              />
            </label>
            <input
              id="dup-title"
              type="text"
              className="input w-full"
              placeholder={sourceLabel ? t("dialogs.duplicate.titlePlaceholderWithSource", { source: sourceLabel }) : t("dialogs.duplicate.titlePlaceholder")}
              value={newTitle}
              onChange={handleTitleChange}
              disabled={submitting}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1" htmlFor="dup-slug">
              <Trans
                i18nKey="dialogs.duplicate.slugLabel"
                components={{ span: <span className="text-[var(--color-mute)] font-normal" /> }}
              />
            </label>
            <input
              id="dup-slug"
              type="text"
              className="input w-full font-mono text-sm"
              placeholder={t("dialogs.duplicate.slugPlaceholder")}
              value={slugValue}
              onChange={handleSlugChange}
              disabled={submitting}
            />
            <p className="mt-1 text-xs text-[var(--color-mute)]">
              {t("dialogs.duplicate.slugHint")}
              {!slugIsManual && derivedSlug && t("dialogs.duplicate.slugDerived")}
            </p>
          </div>
        </fieldset>

        <div className="text-sm rounded-md p-3 bg-[var(--color-mint-100)] border border-[var(--color-mint-200)] text-[var(--color-mint-700)]">
          <div className="font-semibold mb-1">{t("dialogs.duplicate.alwaysIncluded")}</div>
          <ul className="list-disc list-inside space-y-0.5">
            <li>{t("dialogs.duplicate.alwaysListMeta")}</li>
            <li>{t("dialogs.duplicate.alwaysListStyle")}</li>
            <li>{t("dialogs.duplicate.alwaysListCasting")}</li>
          </ul>
          <div className="mt-2 text-xs">{t("dialogs.duplicate.alwaysNote")}</div>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold mb-1">
            {t("dialogs.duplicate.optionalLegend")}
          </legend>

          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={includePhotos}
              onChange={(e) => setIncludePhotos(e.target.checked)}
            />
            <span>
              <span className="font-medium">{t("dialogs.duplicate.photosLabel")}</span>
              <span className="block text-xs text-[var(--color-ink-soft)]">
                {t("dialogs.duplicate.photosDesc")}
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={includeStyleReference}
              onChange={(e) => setIncludeStyleReference(e.target.checked)}
            />
            <span>
              <span className="font-medium">{t("dialogs.duplicate.styleRefLabel")}</span>
              <span className="block text-xs text-[var(--color-ink-soft)]">
                {t("dialogs.duplicate.styleRefDesc")}
              </span>
            </span>
          </label>

          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={includeReferences}
              onChange={(e) => setIncludeReferences(e.target.checked)}
            />
            <span>
              <span className="font-medium">{t("dialogs.duplicate.aiRefsLabel")}</span>
              <span className="block text-xs text-[var(--color-ink-soft)]">
                {t("dialogs.duplicate.aiRefsDesc")}
              </span>
            </span>
          </label>
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
            {submitting ? t("dialogs.duplicate.duplicating") : t("dialogs.duplicate.duplicate")}
          </button>
        </div>
      </div>
    </div>
  );
}
