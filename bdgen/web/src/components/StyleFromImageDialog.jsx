import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";

export default function StyleFromImageDialog({ language = "fr", onApply, onClose }) {
  const { t } = useTranslation();
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
            {t("dialogs.styleFromImage.title")}
          </h3>
          <p className="text-sm text-[var(--color-ink-soft)] mt-1">
            {t("dialogs.styleFromImage.body")}
            <br />
            <em className="text-[var(--color-mute)]">
              {t("dialogs.styleFromImage.caveat")}
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
                alt={t("dialogs.styleFromImage.previewAlt")}
                className="max-h-full max-w-full object-contain"
              />
            ) : (
              <div className="text-center text-sm text-[var(--color-mute)] p-6">
                {t("dialogs.styleFromImage.dropzone")}
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
                {t("dialogs.styleFromImage.preResult")}
              </p>
            )}
            {extracting && (
              <div className="text-sm text-[var(--color-ink-soft)]">
                <span className="inline-block w-3 h-3 rounded-full border-2 border-[var(--color-primary-200)] border-t-[var(--color-primary-500)] animate-spin mr-2" />
                {t("dialogs.styleFromImage.extracting")}
              </div>
            )}
            {result && (
              <div className="space-y-2 text-sm">
                <SectionTitle>{t("dialogs.styleFromImage.visualStyle")}</SectionTitle>
                <Field label={t("dialogs.styleFromImage.artStyle")} value={result.style.art_style} />
                <Field label={t("dialogs.styleFromImage.colorPalette")} value={result.style.color_palette} />
                <Field label={t("dialogs.styleFromImage.lineWork")} value={result.style.line_work} />
                <Field label={t("dialogs.styleFromImage.mood")} value={result.style.mood} />
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
                {t("dialogs.styleFromImage.charactersDetected", { count: characters.length })}
              </SectionTitle>
              <span className="text-xs text-[var(--color-mute)]">
                {t("dialogs.styleFromImage.selectHint")}
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
                          {t("stepsUi.compose.cover")} — {c.outfit}
                        </span>
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
                {t("dialogs.styleFromImage.locationsDetected", { count: locations.length })}
              </SectionTitle>
              <span className="text-xs text-[var(--color-mute)]">
                {t("dialogs.styleFromImage.selectHint")}
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
            {t("dialogs.styleFromImage.noCharactersOrLocations")}
          </p>
        )}

        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            {t("common.cancel")}
          </button>
          {!result ? (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!file || extracting}
              onClick={extract}
            >
              {extracting ? t("dialogs.styleFromImage.analyzing") : t("dialogs.styleFromImage.analyze")}
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
                {t("common.restart")}
              </button>
              <button type="button" className="btn btn-primary" onClick={apply}>
                {applyButtonLabel({ anyCharSelected, anyLocSelected, t })}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function applyButtonLabel({ anyCharSelected, anyLocSelected, t }) {
  const extras = [];
  if (anyCharSelected) extras.push(t("dialogs.styleFromImage.extras.characters"));
  if (anyLocSelected) extras.push(t("dialogs.styleFromImage.extras.locations"));
  if (extras.length === 0) return t("dialogs.styleFromImage.applyStyle");
  return t("dialogs.styleFromImage.applyStyleAnd", { extras: extras.join(" + ") });
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
