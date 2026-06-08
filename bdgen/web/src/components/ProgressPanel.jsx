import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

export default function ProgressPanel({ title, job, events, onInterrupt, hint }) {
  const { t } = useTranslation();
  const logRef = useRef(null);
  const [interrupting, setInterrupting] = useState(false);
  const [interruptError, setInterruptError] = useState(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [events.length]);

  async function handleInterrupt() {
    if (interrupting) return;
    setInterruptError(null);
    setInterrupting(true);
    try {
      await onInterrupt();
      // Stay in the "interrupting" state until the panel unmounts (the
      // terminal event flips the parent to its post-run view). The engine
      // checks the flag between safe boundaries, so the actual stop can take
      // a few seconds — keeping the disabled state avoids double clicks.
    } catch (e) {
      setInterruptError(e.message || t("progressPanel.interruptFailed"));
      setInterrupting(false);
    }
  }

  const ratio =
    job?.progress_total && job?.progress_current
      ? Math.min(1, job.progress_current / job.progress_total)
      : null;

  return (
    <div className="card p-6">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-[var(--color-peach-500)] animate-pulse" />
            {title}
          </h2>
          {hint && (
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">{hint}</p>
          )}
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            className="btn btn-danger"
            onClick={handleInterrupt}
            disabled={interrupting}
          >
            {interrupting ? (
              <>
                <span className="inline-block w-3 h-3 rounded-full border-2 border-white/40 border-t-white animate-spin" />
                {t("progressPanel.interrupting")}
              </>
            ) : (
              t("progressPanel.interrupt")
            )}
          </button>
          {interrupting && (
            <span className="text-xs text-[var(--color-ink-soft)]">
              {t("progressPanel.interruptHint")}
            </span>
          )}
          {interruptError && (
            <span className="text-xs text-[var(--color-rose-500)]">
              {interruptError}
            </span>
          )}
        </div>
      </div>

      {ratio !== null && (
        <div className="mb-4">
          <div className="flex items-baseline justify-between text-xs text-[var(--color-ink-soft)] mb-1">
            <span>{job.last_message}</span>
            <span>
              {job.progress_current}/{job.progress_total}
            </span>
          </div>
          <div className="h-2 bg-[var(--color-paper-soft)] rounded-full overflow-hidden">
            <div
              className="h-full bg-[var(--color-primary-500)] transition-all"
              style={{ width: `${ratio * 100}%` }}
            />
          </div>
        </div>
      )}
      {ratio === null && job?.last_message && (
        <p className="text-sm text-[var(--color-ink-soft)] mb-4">
          {job.last_message}
        </p>
      )}

      <div
        ref={logRef}
        className="bg-[var(--color-paper-soft)] rounded-lg p-3 max-h-72 overflow-y-auto text-xs font-mono space-y-0.5"
      >
        {events.length === 0 && (
          <p className="text-[var(--color-mute)]">{t("progressPanel.empty")}</p>
        )}
        {events.map((e, i) => (
          <div key={i} className="text-[var(--color-ink-soft)]">
            {e.current && e.total ? (
              <span className="text-[var(--color-mute)]">
                [{e.current}/{e.total}]{" "}
              </span>
            ) : null}
            {e.message}
          </div>
        ))}
      </div>

      <p className="text-xs text-[var(--color-mute)] mt-3">
        {t("progressPanel.leaveHint")}
      </p>
    </div>
  );
}
