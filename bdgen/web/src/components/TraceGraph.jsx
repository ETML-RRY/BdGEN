import { useMemo, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Dagre from "@dagrejs/dagre";
import { useTranslation } from "react-i18next";

const NODE_WIDTH = 230;
const NODE_HEIGHT = 110;

// Build a lookup of i18n labels for the node kind ("flow" / "LLM" / "image" /
// "?"). The visual style is fixed (no need to translate colors); only the
// short kind tag is shown to the user.
function useKindStyle() {
  const { t } = useTranslation();
  return useMemo(
    () => ({
      flow: { bg: "#eef2ff", border: "#6366f1", label: t("trace.kind.flow") },
      llm_call: { bg: "#ecfdf5", border: "#10b981", label: t("trace.kind.llm") },
      image_call: { bg: "#fff7ed", border: "#f97316", label: t("trace.kind.image") },
      default: { bg: "#f8fafc", border: "#64748b", label: t("trace.kind.default") },
    }),
    [t],
  );
}

const COMPARE_BORDER = "#a855f7"; // node differs vs compare session

// Convert the linear node list (with parent_id) into React Flow nodes + edges
// and apply a dagre top-down layout. Roots (parent_id == null) sit at the top;
// each call hangs under its parent flow.
function buildGraph(primaryNodes, compareNodes, kindStyle) {
  const compareByName = new Map();
  if (compareNodes) {
    for (const n of compareNodes) compareByName.set(n.name, n);
  }

  const flowNodes = primaryNodes.map((n) => {
    const counterpart = compareByName.get(n.name);
    const diffStatus = computeDiff(n, counterpart);
    return {
      id: n.node_id,
      type: "trace",
      position: { x: 0, y: 0 },
      data: { node: n, diffStatus, pills: extractPills(n) },
    };
  });

  const idSet = new Set(primaryNodes.map((n) => n.node_id));
  const edges = [];
  // Call edges: parent/child relation from `parent_id` written by the tracer.
  for (const n of primaryNodes) {
    if (n.parent_id && idSet.has(n.parent_id)) {
      edges.push({
        id: `call:${n.parent_id}->${n.node_id}`,
        source: n.parent_id,
        target: n.node_id,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#94a3b8" },
        style: { stroke: "#94a3b8", strokeWidth: 1.2 },
        data: { kind: "call" },
      });
    }
  }
  // Data edges: inferred producer→consumer relations by node name.
  for (const e of inferDataEdges(primaryNodes, kindStyle)) edges.push(e);

  // Dagre layout — give each node a height proportional to how many pill
  // rows it ends up showing, so neighbours don't overlap.
  const g = new Dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 28, ranksep: 64, marginx: 16, marginy: 16 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const fn of flowNodes) {
    const extra =
      (fn.data.pills.inputs.length > 0 ? 16 : 0) +
      (fn.data.pills.outputs.length > 0 ? 16 : 0);
    g.setNode(fn.id, { width: NODE_WIDTH, height: NODE_HEIGHT + extra });
  }
  for (const e of edges) g.setEdge(e.source, e.target);
  Dagre.layout(g);

  for (const fn of flowNodes) {
    const pos = g.node(fn.id);
    fn.position = { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 };
  }

  return { nodes: flowNodes, edges };
}

// Build data-flow edges by convention of node names. Each rule below
// encodes a real producer→consumer relationship in the pipeline (see
// generate_script + compose_output). When the tracer later supports
// explicit `produces`/`consumes` declarations, this whole function can be
// dropped — until then, the names are the source of truth.
function inferDataEdges(nodes, kindStyle) {
  const byName = new Map(nodes.map((n) => [n.name, n]));
  const t = kindStyle && (kindStyle.__t || null); // optional i18n
  const out = [];

  function add(srcName, dstName, label, color) {
    const src = byName.get(srcName);
    const dst = byName.get(dstName);
    if (!src || !dst) return;
    out.push(buildDataEdge(src.node_id, dst.node_id, label, color));
  }

  // setup → every per-page LLM call + cover/back image calls
  if (byName.has("call_llm:setup")) {
    for (const n of nodes) {
      if (/^call_llm:page_\d+$/.test(n.name)) {
        out.push(
          buildDataEdge(
            byName.get("call_llm:setup").node_id,
            n.node_id,
            "BdGenScript",
            "green",
          ),
        );
      }
    }
    add("call_llm:setup", "compose_cover", "BdGenScript", "green");
    add("call_llm:setup", "compose_back", "BdGenScript", "green");
  }

  // Sequential page LLM calls — page N's prompt embeds page N-1.
  for (const n of nodes) {
    const m = n.name.match(/^call_llm:page_(\d+)$/);
    if (!m) continue;
    const next = byName.get(`call_llm:page_${parseInt(m[1], 10) + 1}`);
    if (next) out.push(buildDataEdge(n.node_id, next.node_id, "Page", "green"));
  }

  // call_llm:page_N → compose_page_N (the page becomes the image prompt)
  for (const n of nodes) {
    const m = n.name.match(/^call_llm:page_(\d+)$/);
    if (!m) continue;
    const compose = byName.get(`compose_page_${m[1]}`);
    if (compose) out.push(buildDataEdge(n.node_id, compose.node_id, "Page", "green"));
  }

  // ref_* → compose_* : match by the actual path each reference image produced
  // and each compose call consumed. The tracer records `outputs.artifact.path`
  // on every ref_* and `inputs.refs[i].path` on every compose_*, so this
  // connects the right reference sheet to the right page/cover/back.
  for (const e of inferRefEdges(nodes)) out.push(e);

  return out;
}

// Build amber edges from ref_character/location/object producers to the
// compose_* consumers that actually picked up the produced PNG.
function inferRefEdges(nodes) {
  const producers = new Map(); // normalized path → ref node
  for (const n of nodes) {
    if (!/^ref_(character|location|object):/.test(n.name)) continue;
    const path = artifactPath(n);
    if (path) producers.set(path, n);
  }
  if (producers.size === 0) return [];

  const edges = [];
  for (const n of nodes) {
    if (!/^compose_/.test(n.name)) continue;
    const refs = n.inputs?.refs;
    if (!Array.isArray(refs)) continue;
    for (const ref of refs) {
      const path = pathOf(ref);
      if (!path) continue;
      const producer = producers.get(path);
      if (!producer) continue;
      const kind = producer.name.split(":")[0];
      const label =
        kind === "ref_character" ? "character" :
        kind === "ref_location" ? "location" :
        kind === "ref_object" ? "object" : "ref";
      edges.push(buildDataEdge(producer.node_id, n.node_id, label, "amber"));
    }
  }
  return edges;
}

function artifactPath(node) {
  return pathOf(node.outputs?.artifact);
}
function pathOf(value) {
  if (!value) return null;
  if (typeof value === "string") return value;
  if (typeof value === "object" && value.path) return value.path;
  return null;
}

function buildDataEdge(source, target, label, color) {
  const palette = {
    green: { stroke: "#10b981" },
    amber: { stroke: "#f59e0b" },
    purple: { stroke: "#a855f7" },
  };
  const p = palette[color] || palette.green;
  return {
    id: `data:${source}->${target}:${label}`,
    source,
    target,
    label,
    labelStyle: { fontSize: 10, fill: p.stroke, fontFamily: "ui-monospace, monospace" },
    labelBgStyle: { fill: "white", fillOpacity: 0.85 },
    labelBgPadding: [2, 4],
    labelBgBorderRadius: 3,
    markerEnd: { type: MarkerType.ArrowClosed, color: p.stroke },
    style: { stroke: p.stroke, strokeWidth: 1.4, strokeDasharray: "5 4" },
    data: { kind: "data", color },
  };
}

// Pull short, typed badges from a node's inputs/outputs so the user can see
// what is flowing through the pipeline without opening the drawer. Convention
// based — when the Python tracer learns more types (later phase), this is the
// single place to extend.
function extractPills(node) {
  const ins = [];
  const outs = [];

  if (node.kind === "llm_call") {
    if (node.prompt) ins.push({ label: `prompt ${shortLen(node.prompt.length)}`, color: "blue" });
    if (node.extra?.system_prompt) {
      ins.push({ label: `system ${shortLen(node.extra.system_prompt.length)}`, color: "slate" });
    }
    if (node.outputs?.value_type) {
      outs.push({ label: node.outputs.value_type, color: "green" });
    }
    const tok =
      (node.usage?.input_tokens || 0) +
      (node.usage?.output_tokens || 0);
    if (tok > 0) outs.push({ label: `${shortNum(tok)} tok`, color: "slate" });
  } else if (node.kind === "image_call") {
    // refs[] convention is used by compose.py (collected per page/cover/back).
    if (Array.isArray(node.inputs?.refs) && node.inputs.refs.length > 0) {
      ins.push({ label: `${node.inputs.refs.length} refs`, color: "amber" });
    }
    // The references.py path passes named photos individually.
    if (node.inputs?.style_ref?.path) ins.push({ label: "style", color: "purple" });
    if (node.inputs?.character_photo?.path) ins.push({ label: "photo character", color: "blue" });
    if (node.inputs?.location_photo?.path) ins.push({ label: "photo location", color: "blue" });
    if (node.inputs?.object_photo?.path) ins.push({ label: "photo object", color: "blue" });
    if (node.prompt) ins.push({ label: "prompt", color: "slate" });

    const art = node.outputs?.artifact;
    const artPath =
      typeof art === "string" ? art : art && typeof art === "object" ? art.path : null;
    if (artPath) {
      const base = artPath.split("/").pop() || "image";
      outs.push({ label: base, color: "amber" });
    }
  }

  return { inputs: cap(ins), outputs: cap(outs) };
}

function shortLen(n) {
  if (n >= 1000) return `${Math.round(n / 100) / 10}k`;
  return `${n}`;
}
function shortNum(n) {
  if (n >= 1000) return `${Math.round(n / 100) / 10}k`;
  return `${n}`;
}
function cap(arr) {
  if (arr.length <= 3) return arr;
  return [...arr.slice(0, 2), { label: `+${arr.length - 2}`, color: "slate" }];
}

// What changed between the primary node and its named counterpart in session B.
function computeDiff(node, counterpart) {
  if (!counterpart) return null;
  const changes = [];
  if (node.prompt !== counterpart.prompt) changes.push("prompt");
  if (node.model !== counterpart.model) changes.push("model");
  if (node.provider !== counterpart.provider) changes.push("provider");
  if (changes.length === 0) return { kind: "unchanged" };
  return { kind: "changed", changes };
}

const PILL_COLORS = {
  blue: { bg: "#dbeafe", fg: "#1e40af" },
  amber: { bg: "#fef3c7", fg: "#92400e" },
  purple: { bg: "#ede9fe", fg: "#6b21a8" },
  green: { bg: "#d1fae5", fg: "#065f46" },
  slate: { bg: "#e2e8f0", fg: "#475569" },
};

function Pill({ label, color }) {
  const c = PILL_COLORS[color] || PILL_COLORS.slate;
  return (
    <span
      style={{
        fontSize: 9,
        padding: "1px 5px",
        borderRadius: 3,
        background: c.bg,
        color: c.fg,
        fontFamily: "ui-monospace, monospace",
        lineHeight: 1.2,
      }}
    >
      {label}
    </span>
  );
}

function PillRow({ pills, label, t }) {
  if (!pills || pills.length === 0) return null;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 3, marginTop: 3, alignItems: "center" }}>
      <span style={{ fontSize: 8, color: "#94a3b8", marginRight: 2, letterSpacing: 0.5 }}>
        {label ?? t("trace.pill.in")}
      </span>
      {pills.map((p, i) => (
        <Pill key={i} {...p} />
      ))}
    </div>
  );
}

// Custom node renderer with input/output pills.
function TraceNodeView({ data, selected }) {
  const { t } = useTranslation();
  const kindStyle = useKindStyle();
  const { node, diffStatus, pills } = data;
  const style = kindStyle[node.kind] || kindStyle.default;
  const borderColor =
    diffStatus?.kind === "changed" ? COMPARE_BORDER : style.border;
  return (
    <div
      style={{
        width: NODE_WIDTH,
        background: style.bg,
        border: `${selected ? 2 : 1.4}px solid ${borderColor}`,
        borderRadius: 6,
        padding: "6px 8px",
        fontSize: 11,
        lineHeight: 1.25,
        color: "#0f172a",
        boxShadow: selected ? "0 0 0 2px rgba(99,102,241,0.35)" : "none",
      }}
    >
      <Handle type="target" position={Position.Top} style={{ opacity: 0 }} />
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
        <span style={{ fontWeight: 600, color: style.border }}>{style.label}</span>
        <span style={{ color: "#64748b" }}>
          {node.elapsed_seconds != null ? `${node.elapsed_seconds}s` : ""}
        </span>
      </div>
      <div style={{ fontFamily: "ui-monospace, monospace", fontWeight: 500, wordBreak: "break-all" }}>
        {node.name}
      </div>
      {(node.model || node.provider) && (
        <div style={{ color: "#64748b", fontSize: 10, marginTop: 2 }}>
          {node.provider}/{node.model}
        </div>
      )}

      <PillRow pills={pills.inputs} label={t("trace.pill.in")} t={t} />
      <PillRow pills={pills.outputs} label={t("trace.pill.out")} t={t} />

      {diffStatus?.kind === "changed" && (
        <div style={{ color: COMPARE_BORDER, fontSize: 10, marginTop: 3 }}>
          Δ {diffStatus.changes.join(", ")}
        </div>
      )}
      {node.status === "error" && (
        <div style={{ color: "#dc2626", fontSize: 10, marginTop: 2 }}>{t("trace.pill.error")}</div>
      )}
      <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
    </div>
  );
}

const nodeTypes = { trace: TraceNodeView };

export default function TraceGraph({ primaryNodes, compareNodes, selectedNodeId, onSelect }) {
  const { t } = useTranslation();
  const kindStyle = useKindStyle();
  const [showData, setShowData] = useState(true);

  const { nodes, edges } = useMemo(
    () => buildGraph(primaryNodes, compareNodes, kindStyle),
    [primaryNodes, compareNodes, kindStyle],
  );

  // Hide data edges entirely when the toggle is off so the user can fall
  // back to a clean call-only graph if the data lines feel too busy.
  const visibleEdges = useMemo(
    () => edges.filter((e) => showData || e.data?.kind !== "data"),
    [edges, showData],
  );

  // Lineage of the selected node = every node reachable through visible
  // edges, in either direction. Used to dim everything else so the
  // contribution path stands out without hiding the rest of the graph.
  const lineage = useMemo(() => {
    if (!selectedNodeId) return null;
    const outAdj = new Map();
    const inAdj = new Map();
    for (const e of visibleEdges) {
      if (!outAdj.has(e.source)) outAdj.set(e.source, new Set());
      outAdj.get(e.source).add(e.target);
      if (!inAdj.has(e.target)) inAdj.set(e.target, new Set());
      inAdj.get(e.target).add(e.source);
    }
    const reach = new Set([selectedNodeId]);
    const queue = [selectedNodeId];
    while (queue.length) {
      const id = queue.shift();
      const neighbours = [
        ...(outAdj.get(id) || []),
        ...(inAdj.get(id) || []),
      ];
      for (const nb of neighbours) {
        if (!reach.has(nb)) {
          reach.add(nb);
          queue.push(nb);
        }
      }
    }
    return reach;
  }, [selectedNodeId, visibleEdges]);

  const decoratedNodes = useMemo(
    () =>
      nodes.map((n) => {
        const inLineage = !lineage || lineage.has(n.id);
        return {
          ...n,
          selected: n.id === selectedNodeId,
          style: { opacity: inLineage ? 1 : 0.25 },
        };
      }),
    [nodes, selectedNodeId, lineage],
  );

  const decoratedEdges = useMemo(
    () =>
      visibleEdges.map((e) => {
        const inLineage =
          !lineage || (lineage.has(e.source) && lineage.has(e.target));
        const dim = !inLineage;
        return {
          ...e,
          style: { ...e.style, opacity: dim ? 0.12 : 1 },
          labelStyle: e.labelStyle
            ? { ...e.labelStyle, opacity: dim ? 0.2 : 1 }
            : undefined,
          labelBgStyle: e.labelBgStyle
            ? { ...e.labelBgStyle, fillOpacity: dim ? 0.2 : 0.85 }
            : undefined,
        };
      }),
    [visibleEdges, lineage],
  );

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <DataFlowToggle showData={showData} onToggle={setShowData} title={t("trace.dataFlow.title")} label={t("trace.dataFlow.label")} />
      <ReactFlow
        nodes={decoratedNodes}
        edges={decoratedEdges}
        nodeTypes={nodeTypes}
        onNodeClick={(_evt, n) => onSelect(n.id)}
        onPaneClick={() => onSelect(null)}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.2}
        maxZoom={2}
      >
        <Background gap={16} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} />
        <MiniMap pannable zoomable />
      </ReactFlow>
    </div>
  );
}

function DataFlowToggle({ showData, onToggle, title, label }) {
  return (
    <div
      style={{
        position: "absolute",
        top: 8,
        right: 8,
        zIndex: 5,
        display: "flex",
        gap: 6,
        alignItems: "center",
        background: "white",
        border: "1px solid #e2e8f0",
        borderRadius: 6,
        padding: "4px 8px",
        fontSize: 11,
        boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
      }}
      title={title}
    >
      <span
        style={{
          width: 14,
          height: 2,
          background: "#10b981",
          backgroundImage:
            "repeating-linear-gradient(90deg, #10b981 0 4px, transparent 4px 8px)",
        }}
      />
      <label style={{ display: "flex", alignItems: "center", gap: 4, cursor: "pointer" }}>
        <input
          type="checkbox"
          checked={showData}
          onChange={(e) => onToggle(e.target.checked)}
          style={{ margin: 0 }}
        />
        {label}
      </label>
    </div>
  );
}
