import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api.js";
import useJobStream from "../useJobStream.js";
import ProgressPanel from "../ProgressPanel.jsx";
import ScriptBrowser from "../ScriptBrowser.jsx";

export default function ScriptStep({ project, onChanged }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const stream = useJobStream({ project: name, step: "script" });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);

  const target = project.config?.structure?.page_count ?? null;
  const written = project.script?.pages?.length ?? 0;
  const isComplete = target !== null && written >= target && (project.script?.characters?.length ?? 0) > 0;
  const isRunning = stream.matchesThisStep && stream.job?.status === "running";
  const otherStepRunning = stream.job?.status === "running" && !stream.matchesThisStep;

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
  }, [stream.events.length, onChanged]);

  if (otherStepRunning) {
    return (
      <BlockedByOtherStep job={stream.job} />
    );
  }

  if (isRunning) {
    const hasPartial =
      (project.script?.characters?.length ?? 0) > 0 ||
      (project.script?.pages?.length ?? 0) > 0;
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
          <ScriptBrowser project={project} onChanged={onChanged} readOnly />
        )}
      </div>
    );
  }

  // Show the post-run browser when a script exists with pages, even if not "complete"
  // (the user can iterate freely).
  if (project.script?.pages?.length > 0) {
    return (
      <div className="space-y-6">
        {stream.terminal && stream.terminal.status !== "completed" && (
          <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
        )}
        {!isComplete && target !== null && (
          <div className="card p-4 flex items-center justify-between gap-4 bg-[var(--color-peach-100)] border-[var(--color-peach-300)]">
            <span className="text-sm">
              Scénario partiel ({written}/{target} planches). Vous pouvez
              reprendre la génération.
            </span>
            <button className="btn btn-primary" onClick={start} disabled={starting}>
              Reprendre la génération
            </button>
          </div>
        )}
        <ScriptBrowser
          project={project}
          onChanged={onChanged}
        />
        <div className="flex justify-end">
          <button
            className="btn btn-primary"
            onClick={() => navigate(`/projects/${encodeURIComponent(name)}/references`)}
          >
            Continuer vers les références →
          </button>
        </div>
      </div>
    );
  }

  // No script yet → invitation to start
  return (
    <div className="card p-8 text-center">
      <h2 className="text-lg font-semibold mb-2">Lancer l'écriture</h2>
      <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-6">
        Le LLM va développer le synopsis en un scénario complet&nbsp;: personnages,
        décors, couverture, 4ᵉ de couverture, puis chaque planche une à une.
        Vous pourrez consulter et retoucher chaque élément à la fin.
      </p>
      {error && (
        <p className="text-[var(--color-rose-500)] text-sm mb-3">{error}</p>
      )}
      <button className="btn btn-primary" onClick={start} disabled={starting}>
        {starting ? "Démarrage…" : "Lancer l'écriture"}
      </button>
    </div>
  );
}

function BlockedByOtherStep({ job }) {
  return (
    <div className="card p-6 text-sm">
      Une autre génération est en cours&nbsp;: étape «&nbsp;{job.step}&nbsp;» sur le
      projet «&nbsp;{job.project}&nbsp;». Patientez ou interrompez-la avant de
      lancer l'écriture.
    </div>
  );
}

function TerminalBanner({ terminal, onClear }) {
  const tone =
    terminal.status === "completed"
      ? "chip-mint"
      : terminal.status === "interrupted"
      ? "chip-peach"
      : "chip-rose";
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
