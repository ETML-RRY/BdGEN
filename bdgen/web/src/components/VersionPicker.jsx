import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";

// Inline version selector — visually matches the "Planche/Image" picker so
// the two read as a coherent row. Renders a fragment (no wrapper div) so the
// caller can drop it into an existing flex row alongside the page selector.
//
// Props:
//   - projectName: project this file belongs to
//   - filePath:    project-relative path (e.g. "pages/page_03.png")
//   - selectedVersionId / onSelectVersion(versionId, version): controlled
//     selection. `null` means the live file. The parent uses the version
//     object to swap the displayed image.
//   - onRestored: called after a successful restore so the parent can
//     reload its state (image_url, stale flags, etc.).
//   - disabled: passes through to the underlying controls.
export default function VersionPicker({
  projectName,
  filePath,
  selectedVersionId,
  onSelectVersion,
  onRestored,
  disabled = false,
}) {
  const { versions, current, loading, error, refresh } = useVersions(projectName, filePath);
  const [restoring, setRestoring] = useState(false);
  const [restoreError, setRestoreError] = useState(null);

  // Always present "Actuelle" as the first option so the dropdown stays
  // visible even before the first archive — the user can see the feature
  // exists.
  const all = current
    ? [{ ...current, version_id: null, kind: "current" }, ...versions]
    : versions;

  async function handleRestore() {
    if (!selectedVersionId) return;
    setRestoring(true);
    setRestoreError(null);
    try {
      await api.restoreVersion(projectName, filePath, selectedVersionId);
      onSelectVersion(null, null);
      await refresh();
      if (onRestored) await onRestored();
    } catch (e) {
      setRestoreError(e.message);
    } finally {
      setRestoring(false);
    }
  }

  if (loading) {
    return (
      <span className="text-sm text-[var(--color-mute)]">Chargement de l'historique…</span>
    );
  }
  if (error) {
    return <span className="text-sm text-[var(--color-rose-500)]">{error}</span>;
  }

  return (
    <>
      <label className="flex items-center gap-2 text-sm font-medium">
        <span>Version</span>
        <select
          className="select page-select"
          value={selectedVersionId || ""}
          onChange={(e) => {
            const id = e.target.value || null;
            onSelectVersion(id, all.find((x) => x.version_id === id) || null);
          }}
          disabled={disabled || restoring || all.length <= 1}
        >
          {all.map((v, idx) => (
            <option key={v.version_id || "current"} value={v.version_id || ""}>
              {labelFor(v, all.length, idx)}
            </option>
          ))}
        </select>
      </label>
      {selectedVersionId && (
        <button
          type="button"
          className="btn btn-ghost text-sm"
          onClick={handleRestore}
          disabled={disabled || restoring}
          title="Restaurer cette version comme version courante"
        >
          {restoring ? "Restauration…" : "Restaurer cette version"}
        </button>
      )}
      {restoreError && (
        <span className="text-sm text-[var(--color-rose-500)]">{restoreError}</span>
      )}
    </>
  );
}

// Build a short, readable label per option. `idx === 0` is the live file;
// `idx >= 1` are archived versions in newest-first order.
function labelFor(v, total, idx) {
  if (v.version_id === null) {
    return `Actuelle · ${formatModified(v.modified_at)}`;
  }
  const versionNumber = total - idx; // oldest = v1
  const kind = v.kind || "regen";
  const ts = formatVersionId(v.version_id);
  return `v${versionNumber} · ${ts} · ${kind}`;
}

function formatVersionId(versionId) {
  // 2026-05-22T14-30-15-123Z → 22 mai 14:30:15
  try {
    const iso = versionId
      .replace(/-(\d{2})-(\d{2})-(\d{3})Z$/, ":$1:$2.$3Z")
      .replace(/T(\d{2})-/, "T$1:");
    const d = new Date(iso);
    return d.toLocaleString("fr-FR", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return versionId;
  }
}

function formatModified(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("fr-FR", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function useVersions(projectName, filePath) {
  const [state, setState] = useState({
    versions: [],
    current: null,
    loading: true,
    error: null,
  });

  const refresh = useCallback(async () => {
    if (!projectName || !filePath) {
      setState({ versions: [], current: null, loading: false, error: null });
      return;
    }
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const res = await api.listVersions(projectName, filePath);
      setState({
        versions: res?.versions || [],
        current: res?.current || null,
        loading: false,
        error: null,
      });
    } catch (e) {
      if (e.status === 404) {
        setState({ versions: [], current: null, loading: false, error: null });
      } else {
        setState({ versions: [], current: null, loading: false, error: e.message });
      }
    }
  }, [projectName, filePath]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return { ...state, refresh };
}
