import { useEffect, useRef, useState } from "react";
import { FaFileExport, FaFileImport, FaXmark } from "react-icons/fa6";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";

/**
 * Compact bundle controls (export/import) intended to live inside the
 * Casting section header. Renders only the action buttons + an inline status
 * line; the parent owns the heading and intro copy.
 */
export default function ReferencesBundlePanel({ projectName, onImported }) {
  const { t } = useTranslation();
  const [exportOpen, setExportOpen] = useState(false);
  const [importing, setImporting] = useState(false);
  const [message, setMessage] = useState(null);
  const [error, setError] = useState(null);
  const fileRef = useRef(null);

  async function onPickImport(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setImporting(true);
    setMessage(null);
    setError(null);
    try {
      const result = await api.importReferencesBundle(projectName, file);
      const counts = ["characters", "locations", "objects"]
        .map((k) => `${t(`dialogs.referencesBundle.kinds.${k}`)} : ${result.imported[k].length}`)
        .join(" — ");
      const renamedCount = Object.keys(result.renamed || {}).length;
      const renamedNote = renamedCount
        ? t("dialogs.referencesBundle.renamedNote", { count: renamedCount })
        : "";
      setMessage(t("dialogs.referencesBundle.importSuccess", { counts, renamed: renamedNote }));
      if (onImported) await onImported();
    } catch (e) {
      setError(e.message || t("common.importFailed"));
    } finally {
      setImporting(false);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn btn-ghost text-sm inline-flex items-center gap-2"
          onClick={() => {
            setMessage(null);
            setError(null);
            setExportOpen(true);
          }}
          title={t("dialogs.referencesBundle.exportTitle")}
        >
          <FaFileExport aria-hidden /> {t("dialogs.referencesBundle.export")}
        </button>
        <button
          type="button"
          className="btn btn-ghost text-sm inline-flex items-center gap-2"
          onClick={() => fileRef.current?.click()}
          disabled={importing}
          title={t("dialogs.referencesBundle.importTitle")}
        >
          <FaFileImport aria-hidden />
          {importing ? t("dialogs.referencesBundle.importing") : t("dialogs.referencesBundle.import")}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".bdrefs,.zip"
          className="hidden"
          onChange={onPickImport}
        />
      </div>
      {message && (
        <p className="text-xs text-[var(--color-mint-500)]">{message}</p>
      )}
      {error && (
        <p className="text-xs text-[var(--color-rose-500)]">{error}</p>
      )}
      {exportOpen && (
        <ExportDialog
          projectName={projectName}
          onClose={() => setExportOpen(false)}
        />
      )}
    </div>
  );
}

function ExportDialog({ projectName, onClose }) {
  const { t } = useTranslation();
  const [available, setAvailable] = useState(null);
  const [picked, setPicked] = useState({
    characters: new Set(),
    locations: new Set(),
    objects: new Set(),
  });
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listExportableReferences(projectName)
      .then((data) => {
        if (cancelled) return;
        setAvailable(data);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [projectName]);

  function toggle(kind, id) {
    setPicked((prev) => {
      const next = { ...prev, [kind]: new Set(prev[kind]) };
      if (next[kind].has(id)) next[kind].delete(id);
      else next[kind].add(id);
      return next;
    });
  }

  function toggleAll(kind) {
    setPicked((prev) => {
      const items = available?.[kind] || [];
      const allPicked = items.every((it) => prev[kind].has(it.id));
      const next = { ...prev, [kind]: new Set(prev[kind]) };
      if (allPicked) {
        for (const it of items) next[kind].delete(it.id);
      } else {
        for (const it of items) next[kind].add(it.id);
      }
      return next;
    });
  }

  const totalPicked =
    picked.characters.size + picked.locations.size + picked.objects.size;

  async function onConfirm() {
    if (!totalPicked) return;
    setExporting(true);
    setError(null);
    try {
      const blob = await api.exportReferencesBundle(projectName, {
        characters: [...picked.characters],
        locations: [...picked.locations],
        objects: [...picked.objects],
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${projectName}.bdrefs`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      onClose();
    } catch (e) {
      setError(e.message || t("common.exportFailed"));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
      <div className="card max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6">
        <div className="flex items-baseline justify-between mb-2">
          <h3 className="text-lg font-semibold">{t("dialogs.referencesBundle.title")}</h3>
          <button
            type="button"
            className="btn btn-ghost text-sm"
            onClick={onClose}
            aria-label={t("dialogs.referencesBundle.closeAria")}
          >
            <FaXmark aria-hidden />
          </button>
        </div>
        <p className="text-sm text-[var(--color-mute)] mb-4">
          {t("dialogs.referencesBundle.intro")}
        </p>
        {available === null && !error && (
          <p className="text-sm text-[var(--color-mute)]">{t("dialogs.referencesBundle.loading")}</p>
        )}
        {error && (
          <p className="text-sm text-[var(--color-rose-500)] mb-3">{error}</p>
        )}
        {available && (
          <div className="space-y-5">
            {["characters", "locations", "objects"].map((kind) => {
              const items = available[kind] || [];
              if (items.length === 0) {
                return (
                  <Section
                    key={kind}
                    title={t(`dialogs.referencesBundle.kinds.${kind}`)}
                    empty={t("dialogs.referencesBundle.empty")}
                  />
                );
              }
              const allPicked = items.every((it) => picked[kind].has(it.id));
              return (
                <Section
                  key={kind}
                  title={t(`dialogs.referencesBundle.kinds.${kind}`)}
                  action={
                    <button
                      type="button"
                      className="btn btn-ghost text-xs"
                      onClick={() => toggleAll(kind)}
                    >
                      {allPicked
                        ? t("dialogs.referencesBundle.deselectAll")
                        : t("dialogs.referencesBundle.selectAll")}
                    </button>
                  }
                >
                  <ul className="space-y-1">
                    {items.map((it) => (
                      <li key={it.id}>
                        <label className="flex items-center gap-2 cursor-pointer text-sm">
                          <input
                            type="checkbox"
                            checked={picked[kind].has(it.id)}
                            onChange={() => toggle(kind, it.id)}
                          />
                          <span className="font-medium">{it.name}</span>
                          <span className="text-xs text-[var(--color-mute)]">
                            ({it.id})
                          </span>
                        </label>
                      </li>
                    ))}
                  </ul>
                </Section>
              );
            })}
          </div>
        )}
        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            className="btn btn-ghost"
            onClick={onClose}
            disabled={exporting}
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="btn btn-primary inline-flex items-center gap-2"
            onClick={onConfirm}
            disabled={!totalPicked || exporting}
          >
            <FaFileExport aria-hidden />
            {exporting
              ? t("common.exporting")
              : t("dialogs.referencesBundle.export", { count: totalPicked })}
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, action, empty, children }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <h4 className="text-sm font-semibold">{title}</h4>
        {action}
      </div>
      {empty ? (
        <p className="text-xs text-[var(--color-mute)]">{empty}</p>
      ) : (
        children
      )}
    </div>
  );
}
