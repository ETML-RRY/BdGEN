import { Link } from "react-router-dom";

const STEP_LABEL = {
  script: "écriture",
  references: "références",
  compose: "planches",
  upscale: "upscale",
};

export default function RunningBanner({ job, className = "" }) {
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
            Génération en cours sur «&nbsp;{job.project}&nbsp;»
            <span className="text-[var(--color-ink-soft)] font-normal">
              {" "}
              — étape «&nbsp;{STEP_LABEL[job.step] || job.step}&nbsp;»
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
        Suivre
      </Link>
    </div>
  );
}
