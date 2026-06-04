import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api.js";
import ProjectForm from "../ProjectForm.jsx";

function _hasDiff(diff) {
  if (!diff) return false;
  return (
    diff.new?.characters?.length > 0 ||
    diff.new?.locations?.length > 0 ||
    diff.new?.objects?.length > 0 ||
    diff.modified?.characters?.length > 0 ||
    diff.modified?.locations?.length > 0 ||
    diff.modified?.objects?.length > 0
  );
}

function _diffSummaryLines(diff) {
  const lines = [];
  const { new: added, modified } = diff;
  if (added.characters?.length) {
    const names = added.characters.map((c) => c.name).join(", ");
    lines.push(
      `${added.characters.length} personnage${added.characters.length > 1 ? "s" : ""} ajouté${added.characters.length > 1 ? "s" : ""} : ${names}`,
    );
  }
  if (added.locations?.length) {
    const names = added.locations.map((l) => l.name).join(", ");
    lines.push(
      `${added.locations.length} décor${added.locations.length > 1 ? "s" : ""} ajouté${added.locations.length > 1 ? "s" : ""} : ${names}`,
    );
  }
  if (added.objects?.length) {
    const names = added.objects.map((o) => o.name).join(", ");
    lines.push(
      `${added.objects.length} objet${added.objects.length > 1 ? "s" : ""} ajouté${added.objects.length > 1 ? "s" : ""} : ${names}`,
    );
  }
  if (modified.characters?.length) {
    const names = modified.characters.map((c) => c.name).join(", ");
    lines.push(
      `${modified.characters.length} personnage${modified.characters.length > 1 ? "s" : ""} modifié${modified.characters.length > 1 ? "s" : ""} : ${names}`,
    );
  }
  if (modified.locations?.length) {
    const names = modified.locations.map((l) => l.name).join(", ");
    lines.push(
      `${modified.locations.length} décor${modified.locations.length > 1 ? "s" : ""} modifié${modified.locations.length > 1 ? "s" : ""} : ${names}`,
    );
  }
  if (modified.objects?.length) {
    const names = modified.objects.map((o) => o.name).join(", ");
    lines.push(
      `${modified.objects.length} objet${modified.objects.length > 1 ? "s" : ""} modifié${modified.objects.length > 1 ? "s" : ""} : ${names}`,
    );
  }
  return lines;
}

function SyncDialog({ diff, onSync, onSkip, syncing, syncError, syncResult }) {
  const lines = _diffSummaryLines(diff);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="card w-full max-w-lg p-6 space-y-4">
        <h2 className="text-lg font-semibold">Scénario existant détecté</h2>
        <p className="text-sm text-[var(--color-mute)]">
          La configuration a changé depuis la dernière écriture du scénario. Le modèle peut intégrer ces changements
          sans réécrire l'histoire ni modifier les dialogues existants.
        </p>

        <ul className="space-y-1">
          {lines.map((l, i) => (
            <li key={i} className="text-sm flex items-start gap-2">
              <span className="text-[var(--color-accent)] mt-0.5">•</span>
              <span>{l}</span>
            </li>
          ))}
        </ul>

        {syncResult && (
          <div className="rounded-lg bg-green-50 border border-green-200 p-3 text-sm text-green-800">
            Synchronisation appliquée.{" "}
            {syncResult.changes &&
              (() => {
                const c = syncResult.changes;
                const parts = [];
                if (c.character_additions)
                  parts.push(
                    `${c.character_additions} personnage${c.character_additions > 1 ? "s" : ""} ajouté${c.character_additions > 1 ? "s" : ""}`,
                  );
                if (c.character_updates) parts.push(`${c.character_updates} mis à jour`);
                if (c.location_additions)
                  parts.push(
                    `${c.location_additions} décor${c.location_additions > 1 ? "s" : ""} ajouté${c.location_additions > 1 ? "s" : ""}`,
                  );
                if (c.location_updates)
                  parts.push(`${c.location_updates} décor${c.location_updates > 1 ? "s" : ""} mis à jour`);
                if (c.object_additions)
                  parts.push(
                    `${c.object_additions} objet${c.object_additions > 1 ? "s" : ""} ajouté${c.object_additions > 1 ? "s" : ""}`,
                  );
                if (c.object_updates)
                  parts.push(`${c.object_updates} objet${c.object_updates > 1 ? "s" : ""} mis à jour`);
                if (c.page_updates)
                  parts.push(
                    `${c.page_updates} planche${c.page_updates > 1 ? "s" : ""} mise${c.page_updates > 1 ? "s" : ""} à jour`,
                  );
                return parts.length ? parts.join(", ") + "." : "";
              })()}
          </div>
        )}

        {syncError && <p className="text-sm text-[var(--color-rose-500)]">{syncError}</p>}

        <div className="flex justify-end gap-3 pt-2">
          <button type="button" className="btn btn-ghost text-sm" onClick={onSkip} disabled={syncing}>
            Continuer sans synchroniser
          </button>
          {!syncResult && (
            <button type="button" className="btn btn-primary text-sm" onClick={onSync} disabled={syncing}>
              {syncing ? "Synchronisation…" : "Synchroniser le scénario"}
            </button>
          )}
          {syncResult && (
            <button type="button" className="btn btn-primary text-sm" onClick={onSkip}>
              Continuer
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function PreparationStep({ project, onSaved }) {
  const navigate = useNavigate();
  const { name } = useParams();

  const [pendingDiff, setPendingDiff] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncError, setSyncError] = useState(null);
  const [syncResult, setSyncResult] = useState(null);

  if (!project.config) {
    return <div className="card p-6 text-[var(--color-mute)]">Pas de configuration enregistrée pour ce projet.</div>;
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

  async function handleSync() {
    setSyncing(true);
    setSyncError(null);
    try {
      const result = await api.syncScriptWithConfig(name);
      await onSaved(); // Reload project state to reflect script changes.
      setSyncResult(result);
    } catch (e) {
      setSyncError(e.message || "La synchronisation a échoué.");
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
        submitLabel="Enregistrer & passer à l'écriture"
        onApplyStyleOnly={hasScript ? onApplyStyleOnly : null}
        applyStyleOnlyLabel="Restyler sans réécrire"
      />
    </>
  );
}
