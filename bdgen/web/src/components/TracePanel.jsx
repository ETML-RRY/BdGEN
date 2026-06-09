import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import TraceGraph from "./TraceGraph.jsx";
import TraceNodeDrawer from "./TraceNodeDrawer.jsx";

// Full-width debug panel: a toolbar with two session dropdowns on top
// (Session A is the primary view, Session B enables the diff overlay) and
// the dagre-laid-out graph occupying the remaining space. Node detail is
// shown in a centered modal — the rest of the surface stays uncluttered.
export default function TracePanel({ projectName }) {
  const { t, i18n } = useTranslation();
  const [sessions, setSessions] = useState(null);
  const [error, setError] = useState(null);
  const [primaryId, setPrimaryId] = useState(null);
  const [compareId, setCompareId] = useState(null);
  const [traces, setTraces] = useState({});
  const [selectedNodeId, setSelectedNodeId] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api
      .listTraces(projectName)
      .then((res) => {
        if (cancelled) return;
        const list = res?.sessions || [];
        setSessions(list);
        if (list.length > 0) setPrimaryId(list[0].session_id);
      })
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [projectName]);

  // Lazy-fetch trace nodes for whichever session is currently selected.
  useEffect(() => {
    let cancelled = false;
    const ids = [primaryId, compareId].filter((id) => id && !traces[id]);
    if (ids.length === 0) return;
    Promise.all(
      ids.map((sid) =>
        api
          .getTrace(projectName, sid)
          .then((res) => [sid, res?.nodes || []])
          .catch(() => [sid, []]),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setTraces((prev) => {
        const next = { ...prev };
        for (const [sid, nodes] of pairs) next[sid] = nodes;
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
  }, [primaryId, compareId, projectName, traces]);

  // Esc closes the node modal.
  useEffect(() => {
    if (!selectedNodeId) return;
    const handler = (e) => {
      if (e.key === "Escape") setSelectedNodeId(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedNodeId]);

  const primaryNodes = primaryId ? traces[primaryId] : null;
  const compareNodes = compareId ? traces[compareId] : null;
  const selectedNode =
    selectedNodeId && primaryNodes
      ? primaryNodes.find((n) => n.node_id === selectedNodeId)
      : null;
  const selectedCompareNode =
    selectedNode && compareNodes
      ? compareNodes.find((n) => n.name === selectedNode.name) || null
      : null;

  return (
    <div className="flex flex-col h-[calc(100vh-220px)] min-h-[520px] gap-3">
      <Toolbar
        sessions={sessions || []}
        primaryId={primaryId}
        compareId={compareId}
        onChangePrimary={(v) => {
          setPrimaryId(v);
          setSelectedNodeId(null);
          if (v && v === compareId) setCompareId(null);
        }}
        onChangeCompare={(v) => setCompareId(v)}
        language={i18n.language}
        t={t}
      />

      <section className="card p-0 overflow-hidden flex-1 relative">
        {error && <p className="p-4 text-xs text-[var(--color-rose-500)]">{error}</p>}
        {!error && sessions === null && (
          <p className="p-4 text-xs text-[var(--color-mute)]">{t("trace.panel.loading")}</p>
        )}
        {!error && sessions && sessions.length === 0 && (
          <p className="p-4 text-xs text-[var(--color-mute)]">
            {t("trace.panel.empty")}
          </p>
        )}
        {primaryId && primaryNodes === undefined && (
          <p className="p-4 text-xs text-[var(--color-mute)]">{t("trace.panel.loadingGraph")}</p>
        )}
        {primaryNodes && primaryNodes.length === 0 && (
          <p className="p-4 text-xs text-[var(--color-mute)]">{t("trace.panel.emptySession")}</p>
        )}
        {primaryNodes && primaryNodes.length > 0 && (
          <TraceGraph
            primaryNodes={primaryNodes}
            compareNodes={compareNodes}
            selectedNodeId={selectedNodeId}
            onSelect={setSelectedNodeId}
          />
        )}
      </section>

      {selectedNode && (
        <NodeDetailModal
          node={selectedNode}
          compareNode={selectedCompareNode}
          projectName={projectName}
          onClose={() => setSelectedNodeId(null)}
        />
      )}
    </div>
  );
}

function Toolbar({ sessions, primaryId, compareId, onChangePrimary, onChangeCompare, language, t }) {
  return (
    <div className="card p-3 flex flex-wrap items-center gap-4 text-sm">
      <label className="flex items-center gap-2">
        <span className="text-[var(--color-mute)] text-xs uppercase tracking-wide">{t("trace.panel.session")}</span>
        <select
          className="form-control text-sm"
          value={primaryId || ""}
          onChange={(e) => onChangePrimary(e.target.value || null)}
        >
          <option value="">{t("trace.panel.noneOption")}</option>
          {sessions.map((s) => (
            <option key={s.session_id} value={s.session_id}>
              {t("trace.panel.sessionOpt", { ts: formatTs(s.started_at, language), count: s.node_count })}
            </option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-2">
        <span className="text-[var(--color-mute)] text-xs uppercase tracking-wide">
          {t("trace.panel.compareWith")}
        </span>
        <select
          className="form-control text-sm"
          value={compareId || ""}
          onChange={(e) => onChangeCompare(e.target.value || null)}
          disabled={!primaryId}
        >
          <option value="">{t("trace.panel.noneOption")}</option>
          {sessions
            .filter((s) => s.session_id !== primaryId)
            .map((s) => (
              <option key={s.session_id} value={s.session_id}>
                {t("trace.panel.sessionOpt", { ts: formatTs(s.started_at, language), count: s.node_count })}
              </option>
            ))}
        </select>
      </label>
      {compareId && (
        <span className="text-[10px] px-2 py-0.5 rounded bg-purple-100 text-purple-700">
          {t("trace.panel.diffActive")}
        </span>
      )}
    </div>
  );
}

function NodeDetailModal({ node, compareNode, projectName, onClose }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="card w-full max-w-3xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <TraceNodeDrawer
          node={node}
          compareNode={compareNode}
          projectName={projectName}
          onClose={onClose}
        />
      </div>
    </div>
  );
}

function formatTs(ts, language) {
  if (!ts) return "—";
  try {
    const d = new Date(ts);
    return d.toLocaleString(language || "en", {
      year: "2-digit",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return ts;
  }
}
