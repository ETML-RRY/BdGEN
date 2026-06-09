import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";

// Detail view for the node selected in TraceGraph. Shows the full prompt,
// system prompt, model/usage, inputs and outputs. When a `compareNode` is
// provided (B session match-by-name), renders a side-by-side prompt diff
// and a small badge listing the changed fields. The optional `onClose` adds
// a close button so the component can be rendered inside a modal.
export default function TraceNodeDrawer({ node, compareNode, projectName, onClose }) {
  const { t } = useTranslation();
  const [tab, setTab] = useState("prompt");

  if (!node) {
    return (
      <div className="p-4 text-xs text-[var(--color-mute)]">
        {t("trace.nodeDrawer.empty")}
      </div>
    );
  }

  const tabs = [
    { id: "prompt", label: t("trace.nodeDrawer.tabPrompt") },
    { id: "io", label: t("trace.nodeDrawer.tabIo") },
    { id: "raw", label: t("trace.nodeDrawer.tabRaw") },
  ];

  return (
    <div className="flex flex-col h-full">
      <header className="p-3 border-b border-[var(--color-line)]">
        <div className="flex items-center justify-between gap-2 mb-1">
          <h4 className="font-mono text-sm font-semibold break-all">{node.name}</h4>
          <div className="flex items-center gap-2 shrink-0">
            {node.status === "error" && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-rose-100)] text-[var(--color-rose-700)]">
                {t("trace.nodeDrawer.errorBadge")}
              </span>
            )}
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                className="text-[var(--color-mute)] hover:text-[var(--color-ink)] text-lg leading-none px-1"
                aria-label={t("trace.nodeDrawer.closeAria")}
                title={t("trace.nodeDrawer.closeTitle")}
              >
                ×
              </button>
            )}
          </div>
        </div>
        <p className="text-[11px] text-[var(--color-mute)]">
          {node.kind}
          {node.provider || node.model
            ? ` · ${node.provider || "?"}/${node.model || "?"}`
            : ""}
          {node.elapsed_seconds != null
            ? t("trace.nodeDrawer.elapsed", { seconds: node.elapsed_seconds })
            : ""}
        </p>
        {compareNode && (
          <DiffBadge primary={node} compare={compareNode} t={t} />
        )}
      </header>

      <ArtifactPreview node={node} projectName={projectName} />

      <nav className="px-3 pt-2 flex gap-1 text-[11px] border-b border-[var(--color-line)]">
        {tabs.map((tb) => (
          <button
            key={tb.id}
            type="button"
            onClick={() => setTab(tb.id)}
            className={
              "px-2 py-1 rounded-t-md " +
              (tab === tb.id
                ? "bg-[var(--color-paper-soft)] text-[var(--color-ink)] font-medium"
                : "text-[var(--color-mute)] hover:text-[var(--color-ink)]")
            }
          >
            {tb.label}
          </button>
        ))}
      </nav>

      <div className="p-3 overflow-auto flex-1 text-[11px]">
        {tab === "prompt" && (
          <PromptTab node={node} compareNode={compareNode} t={t} />
        )}
        {tab === "io" && <IOTab node={node} projectName={projectName} t={t} />}
        {tab === "raw" && <RawTab node={node} t={t} />}
      </div>
    </div>
  );
}

// Convert an absolute path recorded by the tracer into a project-relative
// path by splitting on the `/{projectName}/` marker — this matches the
// on-disk layout (output_root / project_name / ...).
function projectRelPath(absPath, projectName) {
  if (!absPath || !projectName) return null;
  const path = typeof absPath === "string" ? absPath : absPath.path;
  if (!path) return null;
  const marker = `/${projectName}/`;
  const idx = path.indexOf(marker);
  if (idx === -1) return null;
  return path.substring(idx + marker.length);
}

// Same-origin URL to download a project-relative file via the existing
// /api/projects/{name}/files/{path:path} endpoint.
function fileUrl(projectName, relPath) {
  if (!relPath || !projectName) return null;
  const encoded = relPath.split("/").map(encodeURIComponent).join("/");
  return `/api/projects/${encodeURIComponent(projectName)}/files/${encoded}`;
}

function projectFileUrl(absPath, projectName) {
  return fileUrl(projectName, projectRelPath(absPath, projectName));
}

function isImagePath(value) {
  const p = typeof value === "string" ? value : value?.path;
  return typeof p === "string" && /\.(png|jpe?g|webp|gif)(\?|$)/i.test(p);
}

function basename(value) {
  const p = typeof value === "string" ? value : value?.path;
  if (!p) return "";
  return p.split("/").pop();
}

// Path-ref shape as written by trace.py::_path_ref. We treat both the dict
// form (with .path/.sha256_12) and the bare string form as image candidates.
function isPathRef(value) {
  if (typeof value === "string") return value.includes("/");
  return value && typeof value === "object" && typeof value.path === "string";
}

function ArtifactPreview({ node, projectName }) {
  const art = node.outputs?.artifact;
  if (!isImagePath(art)) return null;
  return <ArtifactPreviewBody art={art} projectName={projectName} />;
}

// The artefact on disk may have been overwritten since this node ran. We
// look up the per-file version history via /api/projects/{name}/versions and
// match the node's recorded sha256_12 against either the current file or one
// of the archived versions. The matched version is selected by default and
// flagged with a "produced by this node" badge; the user can still switch to
// any other version via the dropdown.
function ArtifactPreviewBody({ art, projectName }) {
  const { t, i18n } = useTranslation();
  const relPath = projectRelPath(art, projectName);
  const nodeSha12 = typeof art === "object" ? art.sha256_12 || null : null;
  const { loading, current, versions, error } = useArtifactVersions(projectName, relPath);

  const options = useMemo(() => {
    const out = [];
    if (current) {
      out.push({
        label: t("trace.nodeDrawer.currentVersion"),
        relPath: current.relpath || relPath,
        sha256: current.sha256,
      });
    }
    for (const v of versions) {
      out.push({
        label: t("trace.nodeDrawer.versionOpt", {
          id: formatVersionId(v.version_id, i18n.language),
          kind: v.kind || "regen",
        }),
        relPath: v.relpath,
        sha256: v.sha256,
      });
    }
    return out;
  }, [current, versions, relPath, t, i18n.language]);

  const matchingIdx = useMemo(() => {
    if (!nodeSha12) return -1;
    return options.findIndex((o) => o.sha256 && o.sha256.startsWith(nodeSha12));
  }, [options, nodeSha12]);

  const [selectedIdx, setSelectedIdx] = useState(0);
  useEffect(() => {
    setSelectedIdx(matchingIdx >= 0 ? matchingIdx : 0);
  }, [matchingIdx]);

  const selected = options[selectedIdx] || null;
  const fallbackUrl = projectFileUrl(art, projectName);
  const url = selected ? fileUrl(projectName, selected.relPath) : fallbackUrl;
  if (!url) return null;

  const showSelector = !loading && !error && options.length > 1;
  const isMatchSelected = matchingIdx >= 0 && selectedIdx === matchingIdx;
  const archiveMissing = !loading && !error && nodeSha12 && matchingIdx < 0;

  return (
    <div className="px-3 pt-3 flex flex-col items-center">
      <a href={url} target="_blank" rel="noopener noreferrer" title="Open in full size">
        <img
          src={url}
          alt={basename(art)}
          className="max-h-48 rounded border border-[var(--color-line)] bg-white object-contain"
        />
      </a>
      <p className="text-[10px] text-[var(--color-mute)] mt-1 font-mono">
        {basename(art)}
      </p>
      {loading && (
        <p className="text-[9px] text-[var(--color-mute)] mt-1">{t("trace.nodeDrawer.loadingVersions")}</p>
      )}
      {error && (
        <p className="text-[9px] text-[var(--color-rose-500)] mt-1">{error}</p>
      )}
      {showSelector && (
        <div className="mt-2 flex items-center gap-2 flex-wrap justify-center">
          <select
            className="form-control text-[10px] py-0.5"
            value={selectedIdx}
            onChange={(e) => setSelectedIdx(Number(e.target.value))}
          >
            {options.map((o, i) => (
              <option key={i} value={i}>
                {o.label}
                {i === matchingIdx ? t("trace.nodeDrawer.versionOptCurrent") : ""}
              </option>
            ))}
          </select>
          {isMatchSelected && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-mint-100)] text-[var(--color-mint-700)]">
              {t("trace.nodeDrawer.producedBy")}
            </span>
          )}
        </div>
      )}
      {archiveMissing && (
        <span
          className="mt-2 text-[10px] px-1.5 py-0.5 rounded bg-[var(--color-peach-100)] text-[var(--color-ink-soft)]"
          title={t("trace.nodeDrawer.shaNotFound", { sha: nodeSha12 })}
        >
          {t("trace.nodeDrawer.archiveMissing")}
        </span>
      )}
    </div>
  );
}

function useArtifactVersions(projectName, relPath) {
  const [state, setState] = useState({
    loading: true,
    current: null,
    versions: [],
    error: null,
  });
  useEffect(() => {
    if (!projectName || !relPath) {
      setState({ loading: false, current: null, versions: [], error: null });
      return undefined;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    api
      .listVersions(projectName, relPath)
      .then((res) => {
        if (cancelled) return;
        setState({
          loading: false,
          current: res?.current || null,
          versions: res?.versions || [],
          error: null,
        });
      })
      .catch((e) => {
        if (cancelled) return;
        if (e.status === 404) {
          setState({ loading: false, current: null, versions: [], error: null });
        } else {
          setState({ loading: false, current: null, versions: [], error: e.message });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [projectName, relPath]);
  return state;
}

// Same compact format as VersionPicker: "2026-05-22T14-30-15-123Z" →
// "22 May 14:30:15" (in the current UI language). Kept local to avoid
// coupling TraceNodeDrawer to the VersionPicker module.
function formatVersionId(versionId, language) {
  try {
    const iso = versionId
      .replace(/-(\d{2})-(\d{2})-(\d{3})Z$/, ":$1:$2.$3Z")
      .replace(/T(\d{2})-/, "T$1:");
    const d = new Date(iso);
    return d.toLocaleString(language || "en", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return versionId;
  }
}

function DiffBadge({ primary, compare, t }) {
  const fields = [];
  if (primary.prompt !== compare.prompt) fields.push(t("trace.nodeDrawer.diffField.prompt"));
  if (primary.model !== compare.model) fields.push(t("trace.nodeDrawer.diffField.model"));
  if (primary.provider !== compare.provider) fields.push(t("trace.nodeDrawer.diffField.provider"));
  if (JSON.stringify(primary.usage) !== JSON.stringify(compare.usage)) fields.push(t("trace.nodeDrawer.diffField.usage"));
  if (JSON.stringify(primary.outputs) !== JSON.stringify(compare.outputs)) fields.push(t("trace.nodeDrawer.diffField.outputs"));
  const label = fields.length === 0
    ? t("trace.nodeDrawer.diffIdentical")
    : t("trace.nodeDrawer.diffChanged", { fields: fields.join(", ") });
  const cls =
    fields.length === 0
      ? "bg-[var(--color-mint-100)] text-[var(--color-mint-700)]"
      : "bg-purple-100 text-purple-700";
  return (
    <span className={"inline-block mt-1.5 text-[10px] px-1.5 py-0.5 rounded " + cls}>
      {label}
    </span>
  );
}

function PromptTab({ node, compareNode, t }) {
  const systemPrompt = node.extra?.system_prompt;
  return (
    <div className="space-y-3">
      {systemPrompt && (
        <CollapsibleBlock label={t("trace.nodeDrawer.systemPrompt")} content={systemPrompt} />
      )}
      {node.prompt ? (
        compareNode ? (
          <PromptDiff a={node.prompt} b={compareNode.prompt} t={t} />
        ) : (
          <CodeBlock content={node.prompt} label={t("trace.nodeDrawer.promptLabel")} copy />
        )
      ) : (
        <p className="text-[var(--color-mute)]">{t("trace.nodeDrawer.noPrompt")}</p>
      )}
    </div>
  );
}

function IOTab({ node, projectName, t }) {
  return (
    <div className="space-y-3">
      <Section label={t("trace.nodeDrawer.inputs")}>
        <IOValue value={node.inputs} projectName={projectName} />
      </Section>
      <Section label={t("trace.nodeDrawer.outputs")}>
        <IOValue value={node.outputs} projectName={projectName} />
      </Section>
      {node.usage && Object.keys(node.usage).length > 0 && (
        <Section label={t("trace.nodeDrawer.usage")}>
          <JsonView value={node.usage} />
        </Section>
      )}
      {node.extra && Object.keys(node.extra).filter((k) => k !== "system_prompt").length > 0 && (
        <Section label={t("trace.nodeDrawer.extra")}>
          <JsonView
            value={Object.fromEntries(
              Object.entries(node.extra).filter(([k]) => k !== "system_prompt"),
            )}
          />
        </Section>
      )}
    </div>
  );
}

// Render an inputs/outputs payload by walking its keys: image paths become
// thumbnails, the rest stays as JSON. Keeps the structural keys (e.g.
// `style_ref`, `refs`, `artifact`) so the user can still see what slot each
// image came from.
function IOValue({ value, projectName }) {
  if (value == null || (typeof value === "object" && Object.keys(value).length === 0)) {
    return <p className="text-[var(--color-mute)]">∅</p>;
  }
  if (!isPlainObject(value)) return <JsonView value={value} />;

  const entries = Object.entries(value);
  return (
    <div className="space-y-2">
      {entries.map(([key, val]) => (
        <IOField key={key} label={key} value={val} projectName={projectName} />
      ))}
    </div>
  );
}

function IOField({ label, value, projectName }) {
  // Array of path-refs (e.g. `refs` on a compose node).
  if (Array.isArray(value) && value.length > 0 && value.every(isPathRef)) {
    return (
      <div>
        <KeyLabel name={label} count={value.length} />
        <div className="flex flex-wrap gap-2 mt-1">
          {value.map((v, i) => (
            <Thumbnail key={i} value={v} projectName={projectName} />
          ))}
        </div>
      </div>
    );
  }
  // Single path-ref.
  if (isPathRef(value)) {
    return (
      <div>
        <KeyLabel name={label} />
        <div className="mt-1">
          <Thumbnail value={value} projectName={projectName} />
        </div>
      </div>
    );
  }
  // Null / undefined — show as muted dash so the slot is still visible.
  if (value == null) {
    return (
      <div className="flex items-baseline gap-2">
        <KeyLabel name={label} />
        <span className="text-[var(--color-mute)]">—</span>
      </div>
    );
  }
  // Fallback: render as compact JSON.
  return (
    <div>
      <KeyLabel name={label} />
      <JsonView value={value} />
    </div>
  );
}

function KeyLabel({ name, count }) {
  return (
    <span className="text-[10px] uppercase tracking-wide text-[var(--color-mute)] font-mono">
      {name}
      {count != null ? ` · ${count}` : ""}
    </span>
  );
}

function Thumbnail({ value, projectName }) {
  const url = projectFileUrl(value, projectName);
  const name = basename(value);
  const sha = typeof value === "object" ? value?.sha256_12 : null;
  if (url && isImagePath(value)) {
    return (
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        className="block group"
        title={typeof value === "object" ? value.path : value}
      >
        <img
          src={url}
          alt={name}
          className="h-20 w-20 object-cover rounded border border-[var(--color-line)] bg-white"
        />
        <div className="text-[9px] text-[var(--color-mute)] font-mono mt-0.5 max-w-[80px] truncate">
          {name}
        </div>
      </a>
    );
  }
  // Non-image path or no projectName mapping: show the basename only.
  return (
    <div
      className="text-[10px] font-mono px-2 py-1 rounded bg-[var(--color-paper-soft)] border border-[var(--color-line)]"
      title={typeof value === "object" ? value.path : value}
    >
      {name || "?"}
      {sha && <span className="text-[var(--color-mute)] ml-1">{sha}</span>}
    </div>
  );
}

function isPlainObject(v) {
  return v != null && typeof v === "object" && !Array.isArray(v);
}

function RawTab({ node, t }) {
  return <CodeBlock content={JSON.stringify(node, null, 2)} label={t("trace.nodeDrawer.rawNode")} copy />;
}

function Section({ label, children }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-mute)] mb-1">
        {label}
      </div>
      {children}
    </div>
  );
}

function JsonView({ value }) {
  if (value == null || (typeof value === "object" && Object.keys(value).length === 0)) {
    return <p className="text-[var(--color-mute)]">∅</p>;
  }
  return (
    <pre className="bg-[var(--color-paper-soft)] p-2 rounded text-[10px] whitespace-pre-wrap break-words max-h-60 overflow-auto">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function CodeBlock({ content, label, copy }) {
  const { t } = useTranslation();
  return (
    <div className="relative">
      {copy && (
        <button
          type="button"
          onClick={() => navigator.clipboard.writeText(content)}
          className="absolute right-1 top-1 text-[10px] px-1.5 py-0.5 rounded bg-white border border-[var(--color-line)] hover:bg-[var(--color-paper-soft)]"
          title={t("common.copyLabel", { label })}
        >
          {t("trace.nodeDrawer.copy")}
        </button>
      )}
      <pre className="bg-[var(--color-paper-soft)] p-2 pr-12 rounded text-[10px] whitespace-pre-wrap break-words max-h-[60vh] overflow-auto">
        {content}
      </pre>
    </div>
  );
}

function CollapsibleBlock({ label, content }) {
  return (
    <details>
      <summary className="cursor-pointer text-[10px] uppercase tracking-wide text-[var(--color-mute)]">
        {label}
      </summary>
      <pre className="mt-1 bg-[var(--color-paper-soft)] p-2 rounded text-[10px] whitespace-pre-wrap break-words max-h-40 overflow-auto">
        {content}
      </pre>
    </details>
  );
}

// Naive line-aligned diff: zip the two prompts by line index, mark each line
// as added / removed / unchanged. Not LCS-correct for shifts in the middle,
// but readable for the common case where generation parameters change a few
// lines of a stable template.
function PromptDiff({ a, b, t }) {
  const linesA = (a || "").split("\n");
  const linesB = (b || "").split("\n");
  const max = Math.max(linesA.length, linesB.length);
  const rows = [];
  for (let i = 0; i < max; i++) {
    const la = linesA[i];
    const lb = linesB[i];
    if (la === lb) rows.push({ kind: "same", la, lb });
    else if (la !== undefined && lb !== undefined) rows.push({ kind: "changed", la, lb });
    else if (la !== undefined) rows.push({ kind: "removed", la });
    else rows.push({ kind: "added", lb });
  }
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-[var(--color-mute)] mb-1">
        {t("trace.nodeDrawer.diffPrompt")}
      </div>
      <div className="bg-[var(--color-paper-soft)] rounded text-[10px] font-mono leading-snug max-h-[60vh] overflow-auto">
        {rows.map((row, i) => {
          if (row.kind === "same") {
            return (
              <div key={i} className="px-2 py-px text-[var(--color-mute)] whitespace-pre-wrap break-words">
                {row.la || " "}
              </div>
            );
          }
          if (row.kind === "changed") {
            return (
              <div key={i}>
                <div className="px-2 py-px bg-[var(--color-rose-100)] whitespace-pre-wrap break-words">
                  − {row.la}
                </div>
                <div className="px-2 py-px bg-[var(--color-mint-100)] whitespace-pre-wrap break-words">
                  + {row.lb}
                </div>
              </div>
            );
          }
          if (row.kind === "removed") {
            return (
              <div
                key={i}
                className="px-2 py-px bg-[var(--color-rose-100)] whitespace-pre-wrap break-words"
              >
                − {row.la}
              </div>
            );
          }
          return (
            <div
              key={i}
              className="px-2 py-px bg-[var(--color-mint-100)] whitespace-pre-wrap break-words"
            >
              + {row.lb}
            </div>
          );
        })}
      </div>
    </div>
  );
}
