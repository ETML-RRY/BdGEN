import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useStepLabelMap } from "../hooks/useTranslatedSteps.js";

export default function RunningBanner({ job, className = "" }) {
  const { t } = useTranslation();
  const stepLabels = useStepLabelMap();
  const stepLabel = stepLabels[job.step] || job.step;
  return (
    <div
      className={
        "card p-4 flex items-center justify-between gap-4 border-l-4 " +
        className
      }
      style={{ borderLeftColor: "var(--color-peach-500)" }}
    >
      <div className="flex items-center gap-3">
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--color-peach-500)] animate-pulse" />
        <div className="text-sm">
          <div className="font-medium">
            {t("runningBanner.title", { project: job.project })}
            <span className="text-[var(--color-ink-soft)] font-normal">
              {t("runningBanner.stepSuffix", { step: stepLabel })}
            </span>
          </div>
          {job.last_message && (
            <div className="text-[var(--color-ink-soft)] text-xs mt-0.5">
              {job.last_message}
              {job.progress_total ? (
                <>
                  {" "}
                  ({job.progress_current}/{job.progress_total})
                </>
              ) : null}
            </div>
          )}
        </div>
      </div>
      <Link
        to={`/projects/${encodeURIComponent(job.project)}`}
        className="btn btn-secondary text-sm"
      >
        {t("runningBanner.follow")}
      </Link>
    </div>
  );
}
