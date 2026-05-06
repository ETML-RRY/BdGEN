import { useEffect, useRef, useState, useCallback } from "react";
import { api, subscribeJobEvents } from "../api.js";

/**
 * Subscribes to the global job stream and tracks the current job state.
 *
 * Returns:
 *   { job, events, terminal, refresh, interrupt, clear }
 *
 * - job: latest snapshot of the running/finished job (null if none)
 * - events: array of progress events received in this session
 * - terminal: { status, message } once the job ended, or null
 * - refresh: re-fetch the current job snapshot
 * - interrupt: ask the server to stop the running job
 * - clear: forget a finished job so a new one can start cleanly
 */
export default function useJobStream({ project, step }) {
  const [job, setJob] = useState(null);
  const [events, setEvents] = useState([]);
  const [terminal, setTerminal] = useState(null);
  const closeRef = useRef(null);

  const refresh = useCallback(async () => {
    const { job } = await api.currentJob();
    setJob(job);
    return job;
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useEffect(() => {
    closeRef.current = subscribeJobEvents((payload) => {
      if (payload.type === "progress") {
        setEvents((evts) => {
          const next = [...evts, payload];
          return next.length > 200 ? next.slice(-200) : next;
        });
        // Update the cached job snapshot in place so the UI reacts.
        setJob((j) =>
          j
            ? {
                ...j,
                last_message: payload.message,
                last_event: payload,
                progress_current: payload.current ?? j.progress_current,
                progress_total: payload.total ?? j.progress_total,
              }
            : j,
        );
      } else if (payload.type === "terminal") {
        setTerminal(payload);
        refresh();
      }
    });
    return () => closeRef.current?.();
  }, [refresh]);

  const interrupt = useCallback(async () => {
    await api.interruptJob();
  }, []);

  const clear = useCallback(async () => {
    await api.clearJob();
    setJob(null);
    setEvents([]);
    setTerminal(null);
  }, []);

  // Convenience: belongs-to-this-step boolean.
  const matchesThisStep = job && job.project === project && job.step === step;

  return { job, events, terminal, refresh, interrupt, clear, matchesThisStep };
}
