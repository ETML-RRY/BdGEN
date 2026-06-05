import { useState } from "react";
import { Link } from "react-router-dom";
import { FiChevronLeft, FiChevronRight } from "react-icons/fi";
import { api } from "../api.js";
import { useAppContext } from "../context/AppContext.jsx";

const STEP_LABELS = {
  preparation: "préparation",
  script: "écriture",
  references: "références",
  compose: "planches",
  upscale: "upscale",
};

export default function StatusBar() {
  const { runningJob, pager } = useAppContext();
  const [interrupting, setInterrupting] = useState(false);

  async function handleInterrupt() {
    if (interrupting) return;
    setInterrupting(true);
    try {
      await api.interruptJob();
    } catch {
      // best effort
    } finally {
      setInterrupting(false);
    }
  }

  const running = runningJob?.status === "running";

  let left;
  if (running) {
    const stepLabel = STEP_LABELS[runningJob.step] || runningJob.step;
    const progress =
      runningJob.progress_total > 0 ? ` · ${runningJob.progress_current}/${runningJob.progress_total}` : "";
    left = (
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="w-2 h-2 rounded-full bg-[var(--color-peach-500)] animate-pulse flex-shrink-0"
          aria-hidden="true"
        />
        <span className="truncate">
          Génération en cours — {stepLabel}
          {progress}
          {runningJob.last_message && (
            <span className="text-[var(--color-mute)] ml-1.5">· {runningJob.last_message}</span>
          )}
        </span>
      </div>
    );
  } else {
    left = <span>BdGEN · made with ❤ in Switzerland</span>;
  }

  return (
    <div className="status-bar">
      <div className="status-left min-w-0">{left}</div>
      <div className="status-right">
        {pager && pager.total > 1 && <StatusPager pager={pager} />}
        {running && (
          <div className="flex items-center gap-3 flex-shrink-0">
            {runningJob.project && (
              <Link
                to={`/projects/${encodeURIComponent(runningJob.project)}/${runningJob.step}`}
                className="text-[var(--color-primary-600)] hover:underline"
              >
                Suivre
              </Link>
            )}
            <button
              type="button"
              className="text-[var(--color-rose-500)] hover:underline disabled:opacity-50"
              onClick={handleInterrupt}
              disabled={interrupting}
            >
              {interrupting ? "…" : "Interrompre"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPager({ pager }) {
  const { index, total, onPrev, onNext, label } = pager;
  return (
    <div className="status-pager" aria-label="Pagination">
      <button
        type="button"
        className="status-pager-btn"
        onClick={onPrev}
        disabled={index <= 0}
        title="Précédent"
        aria-label="Précédent"
      >
        <FiChevronLeft aria-hidden />
      </button>
      <span className="status-pager-label">{label || `${index + 1} / ${total}`}</span>
      <button
        type="button"
        className="status-pager-btn"
        onClick={onNext}
        disabled={index >= total - 1}
        title="Suivant"
        aria-label="Suivant"
      >
        <FiChevronRight aria-hidden />
      </button>
    </div>
  );
}
