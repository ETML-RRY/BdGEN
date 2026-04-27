import { useRef, useState } from "react";
import { api } from "../api.js";

export default function StyleFromImageDialog({ language = "fr", onApply, onClose }) {
  const [file, setFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState(null);
  const [extracting, setExtracting] = useState(false);
  const [result, setResult] = useState(null); // {style, characters, locations}
  const [selectedChars, setSelectedChars] = useState({});
  const [selectedLocs, setSelectedLocs] = useState({});
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  function pickFile(f) {
    setError(null);
    setResult(null);
    setSelectedChars({});
    setSelectedLocs({});
    setFile(f);
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  }

  async function extract() {
    if (!file) return;
    setError(null);
    setExtracting(true);
    try {
      const r = await api.styleFromImage(file, language);
      setResult(r);
      const charSel = {};
      (r.characters || []).forEach((_, i) => (charSel[i] = true));
      setSelectedChars(charSel);
      const locSel = {};
      (r.locations || []).forEach((_, i) => (locSel[i] = true));
      setSelectedLocs(locSel);
    } catch (e) {
      setError(e.message);
    } finally {
      setExtracting(false);
    }
  }

  function apply() {
    if (!result) return;
    const chosenChars = (result.characters || []).filter((_, i) => selectedChars[i]);
    const chosenLocs = (result.locations || []).filter((_, i) => selectedLocs[i]);
    onApply({ style: result.style, characters: chosenChars, locations: chosenLocs, file });
    onClose();
  }

  const characters = result?.characters || [];
  const locations = result?.locations || [];
  const hasCharacters = characters.length > 0;
  const hasLocations = locations.length > 0;
  const anyCharSelected = characters.some((_, i) => selectedChars[i]);
  const anyLocSelected = locations.some((_, i) => selectedLocs[i]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm">
      <div className="card p-6 w-full max-w-3xl space-y-4 max-h-[90vh] overflow-y-auto">
        <div>
          <h3 className="text-lg font-semibold">
            Inspirez-vous d'une image
          </h3>
          <p className="text-sm text-[var(--color-ink-soft)] mt-1">
            Téléchargez une image (JPEG, PNG, WEBP). Un modèle de vision en
            extrait le style visuel et, si des personnages sont visibles, leurs
            descriptions — pour pré-remplir le formulaire.
            <br />
            <em className="text-[var(--color-mute)]">
              Aucune référence à des auteurs, studios ou personnages
              protégés ne sera produite — seulement des descripteurs
              génériques.
            </em>
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div
            className="rounded-lg bg-[var(--color-paper-soft)] aspect-square flex items-center justify-center overflow-hidden cursor-pointer border border-dashed border-[var(--color-line)] hover:border-[var(--color-primary-300)]"
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault();
              const dropped = e.dataTransfer.files?.[0];
              if (dropped) pickFile(dropped);
            }}
          >
            {previewUrl ? (
              <img
                src={previewUrl}
                alt="Aperçu"
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <div className="text-center text-sm text-[var(--color-mute)] p-6">
                Cliquez ou déposez une image ici
              </div>
            )}
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0] || null)}
          />

          <div className="space-y-3">
            {!result && !extracting && (
              <p className="text-sm text-[var(--color-ink-soft)]">
                Une fois l'image choisie, lancez l'analyse. Vous pourrez relire
                la description avant de l'appliquer au formulaire.
              </p>
            )}
            {extracting && (
              <div className="text-sm text-[var(--color-ink-soft)]">
                <span className="inline-block w-3 h-3 rounded-full border-2 border-[var(--color-primary-200)] border-t-[var(--color-primary-500)] animate-spin mr-2" />
                Analyse de l'image…
              </div>
            )}
            {result && (
              <div className="space-y-2 text-sm">
                <SectionTitle>Style visuel</SectionTitle>
                <Field label="Style artistique" value={result.style.art_style} />
                <Field label="Palette de couleurs" value={result.style.color_palette} />
                <Field label="Encrage / traits" value={result.style.line_work} />
                <Field label="Atmosphère" value={result.style.mood} />
              </div>
            )}
            {error && (
              <p className="text-sm text-[var(--color-rose-500)]">{error}</p>
            )}
          </div>
        </div>

        {result && hasCharacters && (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <SectionTitle>
                Personnages détectés ({characters.length})
              </SectionTitle>
              <span className="text-xs text-[var(--color-mute)]">
                Cochez ceux à ajouter au projet.
              </span>
            </div>
            <ul className="space-y-2">
              {characters.map((c, i) => (
                <li
                  key={i}
                  className={
                    "card p-3 flex gap-3 items-start cursor-pointer transition " +
                    (selectedChars[i]
                      ? "border-[var(--color-primary-300)]"
                      : "opacity-60")
                  }
                  onClick={() =>
                    setSelectedChars((s) => ({ ...s, [i]: !s[i] }))
                  }
                >
                  <input
                    type="checkbox"
                    checked={!!selectedChars[i]}
                    onChange={() =>
                      setSelectedChars((s) => ({ ...s, [i]: !s[i] }))
                    }
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1"
                  />
                  <div className="flex-1 text-sm">
                    <div className="font-semibold">{c.name}</div>
                    {c.role && (
                      <div className="text-xs text-[var(--color-mute)]">
                        {c.role}
                      </div>
                    )}
                    <p className="mt-1 whitespace-pre-wrap">
                      {c.physical_description}
                    </p>
                    {c.outfit && (
                      <p className="text-[var(--color-ink-soft)] mt-1">
                        <span className="text-xs uppercase tracking-wide text-[var(--color-mute)]">
                          Tenue —{" "}
                        </span>
                        {c.outfit}
                      </p>
                    )}
                    {c.personality && (
                      <p className="text-[var(--color-ink-soft)] italic mt-1">
                        {c.personality}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {result && hasLocations && (
          <div className="space-y-2">
            <div className="flex items-baseline justify-between">
              <SectionTitle>
                Décors détectés ({locations.length})
              </SectionTitle>
              <span className="text-xs text-[var(--color-mute)]">
                Cochez ceux à ajouter au projet.
              </span>
            </div>
            <ul className="space-y-2">
              {locations.map((l, i) => (
                <li
                  key={i}
                  className={
                    "card p-3 flex gap-3 items-start cursor-pointer transition " +
                    (selectedLocs[i]
                      ? "border-[var(--color-primary-300)]"
                      : "opacity-60")
                  }
                  onClick={() =>
                    setSelectedLocs((s) => ({ ...s, [i]: !s[i] }))
                  }
                >
                  <input
                    type="checkbox"
                    checked={!!selectedLocs[i]}
                    onChange={() =>
                      setSelectedLocs((s) => ({ ...s, [i]: !s[i] }))
                    }
                    onClick={(e) => e.stopPropagation()}
                    className="mt-1"
                  />
                  <div className="flex-1 text-sm">
                    <div className="font-semibold">{l.name}</div>
                    <p className="mt-1 whitespace-pre-wrap">
                      {l.description}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}
        {result && !hasCharacters && !hasLocations && (
          <p className="text-sm text-[var(--color-mute)]">
            Aucun personnage ni décor identifié — seuls les champs de style
            seront appliqués.
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Annuler
          </button>
          {!result ? (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!file || extracting}
              onClick={extract}
            >
              {extracting ? "Analyse…" : "Analyser l'image"}
            </button>
          ) : (
            <>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  setResult(null);
                  setSelectedChars({});
                  setError(null);
                }}
              >
                Recommencer
              </button>
              <button type="button" className="btn btn-primary" onClick={apply}>
                {applyButtonLabel({
                  anyCharSelected,
                  anyLocSelected,
                })}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function applyButtonLabel({ anyCharSelected, anyLocSelected }) {
  const extras = [];
  if (anyCharSelected) extras.push("personnages");
  if (anyLocSelected) extras.push("décors");
  if (extras.length === 0) return "Appliquer le style";
  return `Appliquer style + ${extras.join(" + ")}`;
}

function SectionTitle({ children }) {
  return (
    <div className="text-xs font-semibold uppercase tracking-wide text-[var(--color-ink-soft)]">
      {children}
    </div>
  );
}

function Field({ label, value }) {
  return (
    <div>
      <div className="text-[0.72rem] font-semibold text-[var(--color-ink-soft)] uppercase tracking-wide">
        {label}
      </div>
      <div className="text-sm whitespace-pre-wrap">{value}</div>
    </div>
  );
}
