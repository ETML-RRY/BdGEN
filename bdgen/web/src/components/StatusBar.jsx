import { useState } from "react";
import { Link } from "react-router-dom";
import { FiChevronLeft, FiChevronRight } from "react-icons/fi";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { useAppContext } from "../context/AppContext.jsx";
import { useStepLabelMap } from "../hooks/useTranslatedSteps.js";

export default function StatusBar() {
  const { t } = useTranslation();
  const { runningJob, pager } = useAppContext();
  const [interrupting, setInterrupting] = useState(false);
  const stepLabels = useStepLabelMap();

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
    const stepLabel = stepLabels[runningJob.step] || runningJob.step;
    const progress =
      runningJob.progress_total > 0 ? ` · ${runningJob.progress_current}/${runningJob.progress_total}` : "";
    left = (
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="w-2 h-2 rounded-full bg-[var(--color-peach-500)] animate-pulse flex-shrink-0"
          aria-hidden="true"
        />
        <span className="truncate">
          {t("statusBar.running", { stepLabel, progress })}
          {runningJob.last_message && (
            <span className="text-[var(--color-mute)] ml-1.5">
              {t("statusBar.runningMessage", { message: runningJob.last_message })}
            </span>
          )}
        </span>
      </div>
    );
  } else {
    left = <span>{t("statusBar.idle")}</span>;
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
                {t("statusBar.follow")}
              </Link>
            )}
            <button
              type="button"
              className="text-[var(--color-rose-500)] hover:underline disabled:opacity-50"
              onClick={handleInterrupt}
              disabled={interrupting}
            >
              {interrupting ? t("statusBar.interrupting") : t("statusBar.interrupt")}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPager({ pager }) {
  const { t } = useTranslation();
  const { index, total, onPrev, onNext, label } = pager;
  return (
    <div className="status-pager" aria-label={t("statusBar.pagerAria")}>
      <button
        type="button"
        className="status-pager-btn"
        onClick={onPrev}
        disabled={index <= 0}
        title={t("statusBar.previousAria")}
        aria-label={t("statusBar.previousAria")}
      >
        <FiChevronLeft aria-hidden />
      </button>
      <span className="status-pager-label">{label || `${index + 1} / ${total}`}</span>
      <button
        type="button"
        className="status-pager-btn"
        onClick={onNext}
        disabled={index >= total - 1}
        title={t("statusBar.nextAria")}
        aria-label={t("statusBar.nextAria")}
      >
        <FiChevronRight aria-hidden />
      </button>
    </div>
  );
}
