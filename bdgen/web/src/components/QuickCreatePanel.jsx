import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { STYLE_ART_STYLE_PRESETS } from "./projectFormPresets.js";

const PLACEHOLDER = `Décrivez votre envie, du plus vague au plus précis. Par exemple :

• « Surprends-moi avec une histoire de SF »
• « La fondation d'une entreprise informatique par deux amis dans un garage, en manga »
• « Transforme mon support de cours de biologie ci-joint en BD pédagogique »`;

// Formats accepted by the backend (see document_text.SUPPORTED_EXTENSIONS).
const ACCEPTED = ".txt,.text,.md,.markdown,.rst,.csv,.log,.docx,.pdf";
const MAX_FILES = 5;

// Reassuring staged messages shown during the (non-streamed) LLM call. The
// request is a single round-trip, so we can't show true progress — we cycle
// through plausible stages and a live elapsed counter instead.
const STAGES = [
  "Analyse de votre demande…",
  "Construction de l'histoire…",
  "Création du casting et du style visuel…",
  "Mise en forme du formulaire…",
];

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

export default function QuickCreatePanel({ onGenerated, onSkip }) {
  const [prompt, setPrompt] = useState("");
  const [artStyle, setArtStyle] = useState("");
  const [files, setFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [stage, setStage] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const fileInputRef = useRef(null);

  const hasFiles = files.length > 0;
  const canGenerate = (prompt.trim().length > 0 || hasFiles) && !loading;

  // Drive the staged messages + elapsed timer while a request is in flight.
  useEffect(() => {
    if (!loading) return;
    setStage(0);
    setElapsed(0);
    const started = Date.now();
    const timer = setInterval(() => {
      const secs = Math.floor((Date.now() - started) / 1000);
      setElapsed(secs);
      // Advance one stage roughly every 4s, holding on the last.
      setStage(Math.min(STAGES.length - 1, Math.floor(secs / 4)));
    }, 500);
    return () => clearInterval(timer);
  }, [loading]);

  function addFiles(selected) {
    if (!selected || selected.length === 0) return;
    setError(null);
    setFiles((prev) => {
      const merged = [...prev];
      for (const f of selected) {
        if (!merged.some((e) => e.name === f.name && e.size === f.size)) merged.push(f);
      }
      if (merged.length > MAX_FILES) {
        setError(`Maximum ${MAX_FILES} documents.`);
        return merged.slice(0, MAX_FILES);
      }
      return merged;
    });
  }

  function onPick(e) {
    addFiles(Array.from(e.target.files || []));
    // Reset so picking the same file again still fires onChange.
    e.target.value = "";
  }

  function removeFile(idx) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function generate() {
    if (!canGenerate) return;
    setLoading(true);
    setError(null);
    try {
      const draft = await api.quickCreate(prompt.trim(), { files, artStyle });
      onGenerated(draft);
    } catch (e) {
      setError(e.message || "La génération a échoué.");
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    // Ctrl/Cmd + Enter submits, like most prompt boxes.
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      generate();
    }
  }

  return (
    <div className="card p-6 space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">Création rapide</h2>
        <p className="text-sm text-[var(--color-ink-soft)]">
          Décrivez votre idée en une phrase ou un paragraphe, et/ou ajoutez des
          documents de référence (cours, notes…). Nous pré-remplissons le
          formulaire (histoire, style, structure et casting) ; vous pourrez tout
          relire et ajuster ensuite.
        </p>
      </div>

      <textarea
        className="textarea min-h-[14rem] resize-y leading-relaxed"
        rows={8}
        placeholder={PLACEHOLDER}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={loading}
        autoFocus
      />

      {/* Visual style */}
      <div className="space-y-1">
        <label htmlFor="qc-style" className="block text-sm font-medium">
          Style visuel
        </label>
        <select
          id="qc-style"
          className="select"
          value={artStyle}
          onChange={(e) => setArtStyle(e.target.value)}
          disabled={loading}
        >
          <option value="">Laisser l'IA choisir selon l'histoire</option>
          {STYLE_ART_STYLE_PRESETS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <p className="text-xs text-[var(--color-ink-soft)]">
          Vous pourrez l'affiner en détail dans le formulaire.
        </p>
      </div>

      {/* Reference documents */}
      <div className="space-y-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED}
          className="hidden"
          onChange={onPick}
        />
        <button
          type="button"
          className="btn btn-ghost text-sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={loading || files.length >= MAX_FILES}
        >
          + Ajouter des documents
        </button>
        <span className="ml-2 text-xs text-[var(--color-ink-soft)]">
          Word, PDF, texte (.docx, .pdf, .txt, .md…) — max {MAX_FILES}
        </span>

        {hasFiles && (
          <ul className="space-y-1">
            {files.map((f, i) => (
              <li
                key={`${f.name}-${f.size}-${i}`}
                className="flex items-center justify-between gap-3 rounded-lg border border-[var(--color-line)] px-3 py-1.5 text-sm"
              >
                <span className="truncate">
                  📄 {f.name}{" "}
                  <span className="text-[var(--color-ink-soft)]">({formatSize(f.size)})</span>
                </span>
                <button
                  type="button"
                  className="text-[var(--color-ink-soft)] hover:text-[var(--color-rose-500)]"
                  onClick={() => removeFile(i)}
                  disabled={loading}
                  aria-label={`Retirer ${f.name}`}
                  title="Retirer"
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}

      {loading && (
        <div className="flex items-center gap-3 rounded-lg bg-[var(--color-primary-100)] px-4 py-3 text-sm">
          <span
            className="inline-block h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-[var(--color-primary-300)] border-t-transparent"
            aria-hidden
          />
          <span>
            {STAGES[stage]} <span className="text-[var(--color-ink-soft)]">({elapsed} s)</span>
          </span>
        </div>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          className="btn btn-primary"
          onClick={generate}
          disabled={!canGenerate}
        >
          {loading ? "Génération en cours…" : "Générer le brouillon"}
        </button>
        <button
          type="button"
          className="btn btn-ghost text-sm"
          onClick={onSkip}
          disabled={loading}
        >
          Remplir manuellement
        </button>
      </div>
    </div>
  );
}
