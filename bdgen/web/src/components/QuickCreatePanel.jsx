import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { presetsFor } from "./projectFormPresets.js";
import { formatError } from "../i18n/formatError.js";

const ACCEPTED = ".txt,.text,.md,.markdown,.rst,.csv,.log,.docx,.pdf";
const MAX_FILES = 5;

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} o`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function useStageMessages() {
  const { t } = useTranslation();
  return [
    t("quickCreate.stageAnalyze"),
    t("quickCreate.stageStory"),
    t("quickCreate.stageCasting"),
    t("quickCreate.stageFormat"),
  ];
}

export default function QuickCreatePanel({ onGenerated, onSkip }) {
  const { t, i18n } = useTranslation();
  const STAGES = useStageMessages();
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
  }, [loading, STAGES]);

  function addFiles(selected) {
    if (!selected || selected.length === 0) return;
    setError(null);
    setFiles((prev) => {
      const merged = [...prev];
      for (const f of selected) {
        if (!merged.some((e) => e.name === f.name && e.size === f.size)) merged.push(f);
      }
      if (merged.length > MAX_FILES) {
        setError(t("quickCreate.maxFiles", { max: MAX_FILES }));
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
      // Pass the current UI language so the backend quick-create prompt is
      // written in the user's language (not always French).
      const draft = await api.quickCreate(prompt.trim(), {
        language: i18n.language,
        files,
        artStyle,
      });
      // Awaited: onGenerated saves the project and navigates, so keep the
      // spinner up until it resolves (or throws back here).
      await onGenerated(draft);
    } catch (e) {
      setError(formatError(e, t) || t("quickCreate.failed"));
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

  const artStyleOptions = presetsFor("styleArtStyle", i18n.language);

  return (
    <div className="card p-6 space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold">{t("quickCreate.title")}</h2>
        <p className="text-sm text-[var(--color-ink-soft)]">
          {t("quickCreate.body")}
        </p>
      </div>

      <textarea
        className="textarea min-h-[14rem] resize-y leading-relaxed"
        rows={8}
        placeholder={t("quickCreate.placeholder")}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={loading}
        autoFocus
      />

      {/* Visual style */}
      <div className="space-y-1">
        <label htmlFor="qc-style" className="block text-sm font-medium">
          {t("quickCreate.styleLabel")}
        </label>
        <select
          id="qc-style"
          className="select"
          value={artStyle}
          onChange={(e) => setArtStyle(e.target.value)}
          disabled={loading}
        >
          <option value="">{t("quickCreate.styleAiOption")}</option>
          {artStyleOptions.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <p className="text-xs text-[var(--color-ink-soft)]">
          {t("quickCreate.styleHint")}
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
          {t("quickCreate.addDocs")}
        </button>
        <span className="ml-2 text-xs text-[var(--color-ink-soft)]">
          {t("quickCreate.docsHint", { max: MAX_FILES })}
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
                  aria-label={t("quickCreate.removeFileAria", { name: f.name })}
                  title={t("quickCreate.removeFileTitle")}
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
          {loading ? t("quickCreate.generating") : t("quickCreate.generate")}
        </button>
        <button
          type="button"
          className="btn btn-ghost text-sm"
          onClick={onSkip}
          disabled={loading}
        >
          {t("quickCreate.manual")}
        </button>
      </div>
    </div>
  );
}
