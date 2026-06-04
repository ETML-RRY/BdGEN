import { useState } from "react";
import { slugify, sanitizeSlugInput } from "../utils/slugify.js";

/**
 * Dialog asking the user which elements of the source project to carry over
 * into the duplicate. The script, planches, PDF and feedback are never copied
 * — the duplicate restarts at the "Préparation" step.
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
          <h3 className="text-lg font-semibold">Dupliquer ce projet</h3>
          {sourceLabel && (
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              Source&nbsp;: <span className="italic">« {sourceLabel} »</span>
            </p>
          )}
        </div>

        <fieldset className="space-y-3">
          <legend className="text-sm font-semibold mb-1">
            Identité de la copie
          </legend>

          <div>
            <label className="block text-xs font-medium mb-1" htmlFor="dup-title">
              Titre <span className="text-[var(--color-mute)] font-normal">(affiché dans la liste)</span>
            </label>
            <input
              id="dup-title"
              type="text"
              className="input w-full"
              placeholder={sourceLabel ? `${sourceLabel} (copie)` : "Titre de la copie"}
              value={newTitle}
              onChange={handleTitleChange}
              disabled={submitting}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1" htmlFor="dup-slug">
              Identifiant{" "}
              <span className="text-[var(--color-mute)] font-normal">(slug du dossier)</span>
            </label>
            <input
              id="dup-slug"
              type="text"
              className="input w-full font-mono text-sm"
              placeholder="Identifiant du dossier"
              value={slugValue}
              onChange={handleSlugChange}
              disabled={submitting}
            />
            <p className="mt-1 text-xs text-[var(--color-mute)]">
              Lettres minuscules, chiffres et underscores uniquement.
              {!slugIsManual && derivedSlug && " Dérivé du titre — modifiable."}
            </p>
          </div>
        </fieldset>

        <div className="text-sm rounded-md p-3 bg-[var(--color-mint-100)] border border-[var(--color-mint-200)] text-[var(--color-mint-700)]">
          <div className="font-semibold mb-1">Toujours repris</div>
          <ul className="list-disc list-inside space-y-0.5">
            <li>Métadonnées, options de génération</li>
            <li>Style et description du scénario</li>
            <li>Personnages, décors et objets (définitions)</li>
          </ul>
          <div className="mt-2 text-xs">
            Le scénario, les planches, le PDF et les retours ne sont jamais
            copiés&nbsp;: la copie redémarre à l'étape «&nbsp;Préparation&nbsp;».
          </div>
        </div>

        <fieldset className="space-y-2">
          <legend className="text-sm font-semibold mb-1">
            Éléments optionnels à reprendre
          </legend>

          <label className="flex items-start gap-2 text-sm cursor-pointer">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={includePhotos}
              onChange={(e) => setIncludePhotos(e.target.checked)}
            />
            <span>
              <span className="font-medium">Photos importées</span>
              <span className="block text-xs text-[var(--color-ink-soft)]">
                Photos de référence des personnages, décors et objets
                téléversées par l'utilisateur.
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
              <span className="font-medium">Image de référence du style</span>
              <span className="block text-xs text-[var(--color-ink-soft)]">
                Image associée au style graphique (si elle existe).
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
              <span className="font-medium">
                Images de référence générées par l'IA
              </span>
              <span className="block text-xs text-[var(--color-ink-soft)]">
                Conserver les références déjà générées (utile pour un
                Tome&nbsp;2 — pas besoin de les régénérer).
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
            Annuler
          </button>
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleConfirm}
            disabled={submitting}
          >
            {submitting ? "Duplication…" : "Dupliquer"}
          </button>
        </div>
      </div>
    </div>
  );
}
