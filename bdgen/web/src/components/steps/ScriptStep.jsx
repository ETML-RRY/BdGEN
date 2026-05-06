import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api.js";
import useJobStream from "../useJobStream.js";
import ProgressPanel from "../ProgressPanel.jsx";
import RunningBanner from "../RunningBanner.jsx";
import ScriptBrowser from "../ScriptBrowser.jsx";
import ConfirmDialog from "../ConfirmDialog.jsx";

export default function ScriptStep({ project, onChanged }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const stream = useJobStream({ project: name, step: "script" });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const [confirmingRegenAll, setConfirmingRegenAll] = useState(false);
  const [checkingCoherence, setCheckingCoherence] = useState(false);
  const [coherenceError, setCoherenceError] = useState(null);

  const target = project.config?.structure?.page_count ?? null;
  const written = project.script?.pages?.length ?? 0;
  const isComplete = target !== null && written >= target && (project.script?.characters?.length ?? 0) > 0;
  const isRunning = stream.matchesThisStep && stream.job?.status === "running";
  const otherStepRunning = stream.job?.status === "running" && !stream.matchesThisStep;
  const blocked = otherStepRunning;

  async function start() {
    if (starting || isRunning) return;
    setError(null);
    setStarting(true);
    try {
      await api.startStep(name, "script");
      // Pull the fresh job snapshot so the progress panel renders immediately
      // — without this the UI keeps showing the start button until the first
      // SSE event lands, and the user can click again.
      await stream.refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  async function checkCoherence() {
    setCoherenceError(null);
    setCheckingCoherence(true);
    try {
      await api.checkScriptCoherence(name);
      await onChanged();
    } catch (e) {
      setCoherenceError(e.message);
    } finally {
      setCheckingCoherence(false);
    }
  }

  async function regenerateFlaggedPage(pageNumber) {
    const coherence = project.coherence || { issues: [], suggestions: [] };
    const pageIssues = (coherence.issues || []).filter((i) => i.page_number === pageNumber);
    const pageSuggestions = (coherence.suggestions || []).filter((s) => s.page_number === pageNumber);
    const all = [...pageIssues, ...pageSuggestions];
    const feedback =
      all.length > 0
        ? `Améliore cette planche en tenant compte de ces remarques de cohérence : ${all.map((i) => i.message).join(" ")}`
        : "Regénère cette planche pour renforcer la cohérence du scénario.";
    await api.refinePage(name, pageNumber, feedback, true);
    await onChanged();
  }

  async function applySuggestion(suggestionMessage) {
    await api.applyGlobalSuggestion(name, suggestionMessage);
    await onChanged();
  }

  // Refresh project after a terminal event so the script becomes browseable.
  useEffect(() => {
    if (stream.terminal) {
      onChanged();
    }
  }, [stream.terminal, onChanged]);

  // While the job is running, refresh the project whenever a milestone
  // event lands (setup_done, page_N_done, etc.) so the partial-script
  // browser shows the latest content the engine has saved to disk.
  useEffect(() => {
    if (!stream.events.length) return;
    const last = stream.events[stream.events.length - 1];
    if (last?.phase?.endsWith("_done") || last?.phase === "done") {
      onChanged();
    }
  }, [stream.events, onChanged]);

  if (isRunning) {
    const hasPartial = (project.script?.characters?.length ?? 0) > 0 || (project.script?.pages?.length ?? 0) > 0;
    return (
      <div className="space-y-6">
        <ProgressPanel
          title="Écriture du scénario en cours…"
          job={stream.job}
          events={stream.events}
          onInterrupt={stream.interrupt}
          hint="Vous pouvez consulter ce qui a déjà été écrit ci-dessous. Les retouches reviennent dès la fin de la génération."
        />
        {hasPartial && (
          <ScriptBrowser
            project={project}
            onChanged={onChanged}
            readOnly
            coherence={project.coherence}
            onRegeneratePage={regenerateFlaggedPage}
          />
        )}
      </div>
    );
  }

  // Show the post-run browser when a script exists with pages, even if not "complete"
  // (the user can iterate freely).
  if (project.script?.pages?.length > 0) {
    const coherence = project.coherence || { dirty: false, issues: [], suggestions: [], flagged_pages: [] };
    return (
      <div className="space-y-4">
        {blocked && <RunningBanner job={stream.job} />}
        {stream.terminal && stream.terminal.status !== "completed" && (
          <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
        )}
        {!isComplete && target !== null && !blocked && (
          <div className="card p-4 flex items-center justify-between gap-4 bg-[var(--color-peach-100)] border-[var(--color-peach-300)]">
            <span className="text-sm">
              Scénario partiel ({written}/{target} planches). Vous pouvez reprendre la génération.
            </span>
            <button className="btn btn-primary" onClick={start} disabled={starting}>
              Reprendre la génération
            </button>
          </div>
        )}
        <ScriptBrowser
          project={project}
          onChanged={onChanged}
          readOnly={blocked}
          coherence={coherence}
          onRegeneratePage={regenerateFlaggedPage}
          checking={checkingCoherence}
          coherenceError={coherenceError}
          onCheck={checkCoherence}
          onApplySuggestion={applySuggestion}
        />
        <div className="flex items-center justify-between">
          <button
            className="btn btn-ghost text-sm"
            onClick={() => setConfirmingRegenAll(true)}
            disabled={starting || blocked}
          >
            ↻ Régénérer tout le scénario
          </button>
          <button
            className="btn btn-primary"
            onClick={() => navigate(`/projects/${encodeURIComponent(name)}/references`)}
          >
            Continuer vers les références →
          </button>
        </div>
        {confirmingRegenAll && (
          <ConfirmDialog
            title="Régénérer tout le scénario ?"
            body="Le scénario entier (personnages, décors, objets, couvertures et toutes les planches) sera supprimé et réécrit de zéro par le LLM. Les images existantes (références, planches composées) seront marquées comme obsolètes. Cette action est longue et consomme des crédits API."
            confirmLabel="Régénérer tout"
            variant="danger"
            onConfirm={async () => {
              await api.regenerateAll(name, "script");
              await stream.refresh();
            }}
            onClose={() => setConfirmingRegenAll(false)}
          />
        )}
      </div>
    );
  }

  // No script yet → invitation to start
  return (
    <div className="space-y-4">
      {blocked && <RunningBanner job={stream.job} />}
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">Lancer l'écriture</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-6">
          Le LLM va développer le synopsis en un scénario complet&nbsp;: personnages, décors, couverture, 4ᵉ de
          couverture, puis chaque planche une à une. Vous pourrez consulter et retoucher chaque élément à la fin.
        </p>
        {error && <p className="text-[var(--color-rose-500)] text-sm mb-3">{error}</p>}
        <button className="btn btn-primary" onClick={start} disabled={starting || blocked}>
          {starting ? "Démarrage…" : "Lancer l'écriture"}
        </button>
      </div>
    </div>
  );
}

function TerminalBanner({ terminal, onClear }) {
  const tone =
    terminal.status === "completed" ? "chip-mint" : terminal.status === "interrupted" ? "chip-peach" : "chip-rose";
  return (
    <div className="card p-4 flex items-center justify-between gap-4">
      <div className="text-sm">
        <span className={"chip " + tone + " mr-2"}>{terminal.status}</span>
        {terminal.message}
      </div>
      <button className="btn btn-ghost text-sm" onClick={onClear}>
        OK
      </button>
    </div>
  );
}
