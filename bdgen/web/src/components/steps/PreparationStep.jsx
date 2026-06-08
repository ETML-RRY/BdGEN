import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api.js";
import ProjectForm from "../ProjectForm.jsx";
import { formatError } from "../../i18n/formatError.js";

function _hasDiff(diff) {
  if (!diff) return false;
  return (
    diff.new?.characters?.length > 0 ||
    diff.new?.locations?.length > 0 ||
    diff.new?.objects?.length > 0 ||
    diff.modified?.characters?.length > 0 ||
    diff.modified?.locations?.length > 0 ||
    diff.modified?.objects?.length > 0 ||
    diff.removed?.characters?.length > 0 ||
    diff.removed?.locations?.length > 0 ||
    diff.removed?.objects?.length > 0
  );
}

// Flatten removed entities into rows tagged with their entity kind (plural,
// matching the backend removals payload keys).
function _removalRows(diff, t) {
  const removed = diff.removed || {};
  const kindLabels = {
    characters: t("stepsUi.preparation.kindCharacter"),
    locations: t("stepsUi.preparation.kindLocation"),
    objects: t("stepsUi.preparation.kindObject"),
  };
  const rows = [];
  for (const kind of ["characters", "locations", "objects"]) {
    for (const e of removed[kind] || []) {
      rows.push({ ...e, kind, kindLabel: kindLabels[kind] });
    }
  }
  return rows;
}

function _diffSummaryLines(diff, t) {
  const lines = [];
  const { new: added, modified } = diff;
  if (added.characters?.length) {
    const names = added.characters.map((c) => c.name).join(", ");
    lines.push(t("stepsUi.preparation.diffCharactersAdded", { count: added.characters.length, names }));
  }
  if (added.locations?.length) {
    const names = added.locations.map((l) => l.name).join(", ");
    lines.push(t("stepsUi.preparation.diffLocationsAdded", { count: added.locations.length, names }));
  }
  if (added.objects?.length) {
    const names = added.objects.map((o) => o.name).join(", ");
    lines.push(t("stepsUi.preparation.diffObjectsAdded", { count: added.objects.length, names }));
  }
  if (modified.characters?.length) {
    const names = modified.characters.map((c) => c.name).join(", ");
    lines.push(t("stepsUi.preparation.diffCharactersModified", { count: modified.characters.length, names }));
  }
  if (modified.locations?.length) {
    const names = modified.locations.map((l) => l.name).join(", ");
    lines.push(t("stepsUi.preparation.diffLocationsModified", { count: modified.locations.length, names }));
  }
  if (modified.objects?.length) {
    const names = modified.objects.map((o) => o.name).join(", ");
    lines.push(t("stepsUi.preparation.diffObjectsModified", { count: modified.objects.length, names }));
  }
  return lines;
}

function SyncDialog({ diff, onSync, onSkip, syncing, syncError, syncResult }) {
  const { t } = useTranslation();
  const lines = _diffSummaryLines(diff, t);
  const removalRows = _removalRows(diff, t);
  // Removals are destructive (they drop & regenerate pages), so each is an
  // explicit opt-in — nothing is removed unless the user ticks it.
  const [selected, setSelected] = useState({});

  function toggle(key) {
    setSelected((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  function buildRemovals() {
    const out = { characters: [], locations: [], objects: [] };
    for (const row of removalRows) {
      if (selected[`${row.kind}:${row.id}`]) out[row.kind].push(row.id);
    }
    const total = out.characters.length + out.locations.length + out.objects.length;
    return total > 0 ? out : null;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="card w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">{t("stepsUi.preparation.syncTitle")}</h2>
        <p className="text-sm text-[var(--color-mute)]">{t("stepsUi.preparation.syncBody")}</p>

        {lines.length > 0 && (
          <ul className="space-y-1">
            {lines.map((l, i) => (
              <li key={i} className="text-sm flex items-start gap-2">
                <span className="text-[var(--color-accent)] mt-0.5">•</span>
                <span>{l}</span>
              </li>
            ))}
          </ul>
        )}

        {!syncResult && removalRows.length > 0 && (
          <div className="rounded-lg bg-[var(--color-peach-100)] border border-[var(--color-peach-300)] p-3 space-y-2">
            <p className="text-sm font-semibold text-[var(--color-peach-500)]">
              {t("stepsUi.preparation.removedTitle")}
            </p>
            <p className="text-xs text-[var(--color-mute)]">{t("stepsUi.preparation.removedBody")}</p>
            <ul className="space-y-1">
              {removalRows.map((row) => {
                const key = `${row.kind}:${row.id}`;
                return (
                  <li key={key}>
                    <label className="flex items-start gap-2 text-sm cursor-pointer">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={!!selected[key]}
                        onChange={() => toggle(key)}
                        disabled={syncing}
                      />
                      <span>
                        <span className="font-medium">{row.name}</span>{" "}
                        <span className="text-xs text-[var(--color-mute)]">({row.kindLabel})</span>
                        <span className="block text-xs text-[var(--color-mute)]">
                          {row.pages_dropped > 0
                            ? t("stepsUi.preparation.removedImpact", {
                                count: row.pages_dropped,
                                from: row.earliest_affected,
                              })
                            : t("stepsUi.preparation.removedNoImpact")}
                        </span>
                      </span>
                    </label>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {syncResult && (
          <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-800">
            {t("stepsUi.preparation.syncSuccess")}{" "}
            {syncResult.changes &&
              (() => {
                const c = syncResult.changes;
                const parts = [];
                if (c.character_additions)
                  parts.push(t("stepsUi.preparation.syncCounts.charsAdded", { count: c.character_additions }));
                if (c.character_updates) parts.push(t("stepsUi.preparation.syncCounts.charsUpdated", { count: c.character_updates }));
                if (c.location_additions)
                  parts.push(t("stepsUi.preparation.syncCounts.locsAdded", { count: c.location_additions }));
                if (c.location_updates) parts.push(t("stepsUi.preparation.syncCounts.locsUpdated", { count: c.location_updates }));
                if (c.object_additions)
                  parts.push(t("stepsUi.preparation.syncCounts.objsAdded", { count: c.object_additions }));
                if (c.object_updates) parts.push(t("stepsUi.preparation.syncCounts.objsUpdated", { count: c.object_updates }));
                if (c.character_removals)
                  parts.push(t("stepsUi.preparation.syncCounts.charsRemoved", { count: c.character_removals }));
                if (c.location_removals)
                  parts.push(t("stepsUi.preparation.syncCounts.locsRemoved", { count: c.location_removals }));
                if (c.object_removals)
                  parts.push(t("stepsUi.preparation.syncCounts.objsRemoved", { count: c.object_removals }));
                if (c.page_updates)
                  parts.push(t("stepsUi.preparation.syncCounts.pagesUpdated", { count: c.page_updates }));
                return parts.length ? parts.join(", ") + "." : "";
              })()}
            {syncResult.pages_dropped > 0 && (
              <span className="block mt-1">
                {t("stepsUi.preparation.regenPending", { count: syncResult.pages_dropped })}
              </span>
            )}
          </div>
        )}

        {syncError && <p className="text-sm text-[var(--color-rose-500)]">{syncError}</p>}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn btn-ghost text-sm" onClick={onSkip} disabled={syncing}>
            {t("stepsUi.preparation.skipSync")}
          </button>
          {!syncResult && (
            <button
              type="button"
              className="btn btn-primary text-sm"
              onClick={() => onSync(buildRemovals())}
              disabled={syncing || (lines.length === 0 && !buildRemovals())}
            >
              {syncing ? t("stepsUi.preparation.syncing") : t("stepsUi.preparation.syncSubmit")}
            </button>
          )}
          {syncResult && (
            <button type="button" className="btn btn-primary text-sm" onClick={onSkip}>
              {t("stepsUi.preparation.continueAfter")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PreparationStep({ project, onSaved }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { name } = useParams();

  const [pendingDiff, setPendingDiff] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  if (!project.config) {
    return <div className="card p-6 text-[var(--color-mute)]">{t("stepsUi.preparation.noConfig")}</div>;
  }

  function navigateToScript() {
    navigate(`/projects/${encodeURIComponent(name)}/script`);
  }

  async function onSubmit(config) {
    await api.updateProject(name, config);
    await onSaved();

    // If the script already exists, check for config↔script drift.
    if (project.script) {
      try {
        const diff = await api.getConfigScriptDiff(name);
        if (_hasDiff(diff)) {
          setPendingDiff(diff);
          setSyncError(null);
          setSyncResult(null);
          return; // Wait for user choice before navigating.
        }
      } catch {
        // Non-blocking: diff check failure does not prevent saving.
      }
    }
    navigateToScript();
  }

  async function handleSync(removals = null) {
    setSyncing(true);
    setSyncError(null);
    try {
      const result = await api.syncScriptWithConfig(name, removals);
      await onSaved(); // Reload project state to reflect script changes.
      setSyncResult(result);
    } catch (e) {
      setSyncError(formatError(e, t) || t("stepsUi.preparation.syncFailed"));
    } finally {
      setSyncing(false);
    }
  }

  function handleSkip() {
    setPendingDiff(null);
    setSyncResult(null);
    navigateToScript();
  }

  const hasScript = Boolean(project.script);

  async function onApplyStyleOnly(config) {
    await api.updateProject(name, config);
    await api.restyleProject(name, config.style);
    await onSaved();
    navigate(`/projects/${encodeURIComponent(name)}/references`);
  }

  return (
    <>
      {pendingDiff && (
        <SyncDialog
          diff={pendingDiff}
          onSync={handleSync}
          onSkip={handleSkip}
          syncing={syncing}
          syncError={syncError}
          syncResult={syncResult}
        />
      )}
      <ProjectForm
        initial={project.config}
        projectName={name}
        initialCharacterPhotos={project.character_photos || {}}
        initialLocationPhotos={project.location_photos || {}}
        initialObjectPhotos={project.object_photos || {}}
        initialReferenceImages={project.reference_images || {}}
        onSubmit={onSubmit}
        onReferencesImported={onSaved}
        submitLabel={t("stepsUi.preparation.submitLabel")}
        onApplyStyleOnly={hasScript ? onApplyStyleOnly : null}
        applyStyleOnlyLabel={t("stepsUi.preparation.applyStyleOnlyLabel")}
      />
    </>
  );
}
