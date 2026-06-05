import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useParams } from "react-router-dom";
import {
  FaWandMagicSparkles,
  FaArrowRotateRight,
  FaPaintbrush,
  FaForward,
  FaCheck,
  FaImages,
} from "react-icons/fa6";
import { api } from "../api.js";
import { useAppContext } from "../context/AppContext.jsx";
import useRegisterShell from "../hooks/useRegisterShell.js";
import { projectRibbonGroup } from "./shell/ribbonModel.js";
import useJobStream from "./useJobStream.js";
import ProgressPanel from "./ProgressPanel.jsx";
import RunningBanner from "./RunningBanner.jsx";
import RefineDialog from "./RefineDialog.jsx";
import ConfirmDialog from "./ConfirmDialog.jsx";
import VersionPicker from "./VersionPicker.jsx";

// Extract the project-relative path from a /api/projects/{name}/files/{path}
// URL — needed to query the version history of the same file.
function filePathFromUrl(url) {
  if (!url || typeof url !== "string") return null;
  const marker = "/files/";
  const idx = url.indexOf(marker);
  if (idx === -1) return null;
  const tail = url.substring(idx + marker.length).split("?")[0];
  return tail.split("/").map(decodeURIComponent).join("/");
}

const MIN_BRUSH = 8;
const MAX_BRUSH = 80;
const DEFAULT_BRUSH = 24;
const IDLE_PHASE_SUFFIXES = ["_done", "_skipped"];

const LAYOUT_CLASS = {
  portrait: "aspect-[2/3]",
  landscape: "aspect-[3/2]",
  strip: "aspect-[3/2]",
  square: "aspect-square",
};

function generationTargetId(job) {
  if (!job || job.status !== "running") return null;
  const event = job.last_event;
  const phase = event?.phase || "";
  if (!event?.extra?.id) return null;
  if (phase === "assembling" || phase === "done") return null;
  if (IDLE_PHASE_SUFFIXES.some((suffix) => phase.endsWith(suffix))) return null;
  return event.extra.id;
}

/**
 * Reusable shell for the image-generation steps (references, compose).
 *
 * The reading zone here stays intentionally bare — just the current image,
 * its busy overlay, the optional inpaint canvas and the description. Every
 * action and the pager are published to the desktop chrome (ribbon / sidebar /
 * status-bar pager) via `useRegisterShell`, so nothing stacks above and below
 * the image anymore.
 *
 * Items: [{ id, label, image_url, description?, stale?,
 *           group?, shortLabel? }]
 */
export default function ImageStep({
  onChanged,
  stepId,
  title,
  intro,
  feedbackStep = stepId,
  allowRefine = true,
  allowSkip = false,
  onSkip,
  onContinue,
  continueLabel = "Continuer →",
  projectExtraCommands = null,
  genGroupLabel = "Génération",
  startLabel = "Lancer la génération",
  items,
  emptyLabel,
  layout = "portrait",
}) {
  const { name } = useParams();
  const { projectActions } = useAppContext();
  const stream = useJobStream({ project: name, step: stepId });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const [refining, setRefining] = useState(null);
  const [idx, setIdx] = useState(0);
  const [confirmingRegenAll, setConfirmingRegenAll] = useState(false);
  const [confirmingRegen, setConfirmingRegen] = useState(false);

  // Inpaint + version-history state (lifted from the old flipper so the ribbon
  // can drive them).
  const [inpaintActive, setInpaintActive] = useState(false);
  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasMask, setHasMask] = useState(false);
  const [inpaintPrompt, setInpaintPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [inpaintError, setInpaintError] = useState(null);
  const [selectedVersion, setSelectedVersion] = useState({ id: null, version: null });
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const lastPos = useRef(null);
  // The retouche popover is anchored under its ribbon icon (rendered by the
  // shell). We hand the button a ref through the ribbon command and read its
  // on-screen rect to place a non-modal panel just below it.
  const inpaintBtnRef = useRef(null);
  const [inpaintPos, setInpaintPos] = useState(null);
  // Once the user drags the popover, stop auto-anchoring it under the icon.
  const inpaintMovedRef = useRef(false);

  const isRunning = stream.matchesThisStep && stream.job?.status === "running";
  const otherStepRunning = stream.job?.status === "running" && !stream.matchesThisStep;
  const blocked = otherStepRunning;
  const hasAnyImage = items.some((it) => it.image_url);
  // Only treat the running job as "ours" when it belongs to this project AND
  // step. Otherwise navigating to another comic (a different project) whose
  // board shares the same item id (e.g. "p2") would light up the busy overlay
  // as if that already-ready board were regenerating.
  const activeGenerationId = stream.matchesThisStep ? generationTargetId(stream.job) : null;

  const staleItems = items.filter((it) => it.stale && it.image_url);

  const safeIdx = Math.max(0, Math.min(idx, items.length - 1));
  const item = items[safeIdx];
  const filePath = item ? filePathFromUrl(item.image_url) : null;
  const viewingHistory = !!selectedVersion.id;
  const archivedUrl =
    viewingHistory && selectedVersion.version?.relpath && name
      ? `/api/projects/${encodeURIComponent(name)}/files/${selectedVersion.version.relpath
          .split("/")
          .map(encodeURIComponent)
          .join("/")}`
      : null;
  const displayedUrl = archivedUrl || item?.image_url;
  const isStale = !!item?.stale && !!item?.image_url;
  const canRefresh = !viewingHistory && item?.image_url;
  const itemBusy = starting || submitting || activeGenerationId === item?.id;
  const readerBusyLabel = submitting ? "Retouche en cours..." : isRunning ? "Génération en cours..." : "Préparation...";

  useEffect(() => {
    if (stream.terminal) onChanged();
  }, [stream.terminal, onChanged]);

  useEffect(() => {
    if (!stream.events.length) return;
    const last = stream.events[stream.events.length - 1];
    if (last?.artifact) onChanged();
  }, [stream.events, onChanged]);

  // Reset inpaint/version state when switching items.
  useEffect(() => {
    setInpaintActive(false);
    setHasMask(false);
    setInpaintPrompt("");
    setInpaintError(null);
    setSelectedVersion({ id: null, version: null });
    lastPos.current = null;
  }, [safeIdx]);

  // Keep the retouche popover anchored under the ribbon icon. It is non-modal:
  // closing happens via the icon, Annuler or Échap — never on outside click,
  // so painting the mask on the image never dismisses it.
  useEffect(() => {
    if (!inpaintActive) {
      setInpaintPos(null);
      return;
    }
    inpaintMovedRef.current = false;
    function place() {
      const btn = inpaintBtnRef.current;
      if (!btn || inpaintMovedRef.current) return;
      const rect = btn.getBoundingClientRect();
      const width = 340;
      let left = rect.left;
      // Keep the panel off the image so it never blocks painting the mask:
      // if it would overlap, tuck it into the free space left of the image
      // when there's room there.
      const img = imgRef.current;
      if (img) {
        const ir = img.getBoundingClientRect();
        if (left + width > ir.left && ir.left - width - 12 >= 8) {
          left = ir.left - width - 12;
        }
      }
      left = Math.max(8, Math.min(left, window.innerWidth - width - 8));
      setInpaintPos({ top: rect.bottom + 6, left, width });
    }
    function onKey(e) {
      if (e.key === "Escape") closeInpaint();
    }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("keydown", onKey);
    };
    // closeInpaint is a stable handler; re-running on it would needlessly
    // rebind listeners on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inpaintActive]);

  async function start({ force_ids } = {}) {
    if (starting || isRunning) return;
    setError(null);
    setStarting(true);
    try {
      const payload = {};
      if (force_ids) payload.force_ids = force_ids;
      await api.startStep(name, stepId, payload);
      await stream.refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  // ── Inpaint canvas helpers ────────────────────────────────────────────
  function syncCanvas() {
    const img = imgRef.current;
    const cvs = canvasRef.current;
    if (!img || !cvs) return;
    const rect = img.getBoundingClientRect();
    if (cvs.width !== rect.width || cvs.height !== rect.height) {
      const tmp = document.createElement("canvas");
      tmp.width = cvs.width;
      tmp.height = cvs.height;
      tmp.getContext("2d").drawImage(cvs, 0, 0);
      cvs.width = rect.width;
      cvs.height = rect.height;
      cvs.getContext("2d").drawImage(tmp, 0, 0, rect.width, rect.height);
    }
  }

  function getPos(e) {
    const cvs = canvasRef.current;
    if (!cvs) return null;
    const rect = cvs.getBoundingClientRect();
    const client = e.touches ? e.touches[0] : e;
    return { x: client.clientX - rect.left, y: client.clientY - rect.top };
  }

  function paint(pos) {
    const cvs = canvasRef.current;
    if (!cvs || !pos) return;
    const ctx = cvs.getContext("2d");
    ctx.globalCompositeOperation = "source-over";
    ctx.fillStyle = "rgba(220, 50, 50, 0.55)";
    ctx.lineWidth = brushSize;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";
    if (lastPos.current) {
      ctx.beginPath();
      ctx.moveTo(lastPos.current.x, lastPos.current.y);
      ctx.lineTo(pos.x, pos.y);
      ctx.strokeStyle = "rgba(220, 50, 50, 0.55)";
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(pos.x, pos.y, brushSize / 2, 0, Math.PI * 2);
    ctx.fill();
    lastPos.current = pos;
    setHasMask(true);
  }

  function onPointerDown(e) {
    e.preventDefault();
    syncCanvas();
    setIsDrawing(true);
    const pos = getPos(e);
    lastPos.current = pos;
    paint(pos);
  }

  function onPointerMove(e) {
    if (!isDrawing) return;
    e.preventDefault();
    paint(getPos(e));
  }

  function onPointerUp() {
    setIsDrawing(false);
    lastPos.current = null;
  }

  function clearMask() {
    const cvs = canvasRef.current;
    if (!cvs) return;
    cvs.getContext("2d").clearRect(0, 0, cvs.width, cvs.height);
    setHasMask(false);
  }

  function closeInpaint() {
    setInpaintActive(false);
    clearMask();
  }

  // Drag the retouche popover by its header so the user can move it off the
  // image while painting the mask.
  function startInpaintDrag(e) {
    if (e.button !== undefined && e.button !== 0) return;
    e.preventDefault();
    const startX = e.clientX;
    const startY = e.clientY;
    const orig = inpaintPos;
    if (!orig) return;
    inpaintMovedRef.current = true;
    function move(ev) {
      const width = orig.width;
      const left = Math.max(8, Math.min(orig.left + ev.clientX - startX, window.innerWidth - width - 8));
      const top = Math.max(8, Math.min(orig.top + ev.clientY - startY, window.innerHeight - 60));
      setInpaintPos({ ...orig, top, left });
    }
    function up() {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    }
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  }

  async function buildMaskBlob() {
    const cvs = canvasRef.current;
    return new Promise((resolve) => {
      const offscreen = document.createElement("canvas");
      offscreen.width = cvs.width;
      offscreen.height = cvs.height;
      const ctx = offscreen.getContext("2d");
      const drawData = cvs.getContext("2d").getImageData(0, 0, cvs.width, cvs.height);
      const maskData = ctx.createImageData(cvs.width, cvs.height);
      for (let i = 0; i < drawData.data.length; i += 4) {
        if (drawData.data[i + 3] > 10) {
          maskData.data[i] = 0;
          maskData.data[i + 1] = 0;
          maskData.data[i + 2] = 0;
          maskData.data[i + 3] = 0;
        } else {
          maskData.data[i] = 255;
          maskData.data[i + 1] = 255;
          maskData.data[i + 2] = 255;
          maskData.data[i + 3] = 255;
        }
      }
      ctx.putImageData(maskData, 0, 0);
      offscreen.toBlob(resolve, "image/png");
    });
  }

  async function submitInpaint() {
    if (!hasMask) {
      setInpaintError("Dessinez d'abord la zone à retoucher.");
      return;
    }
    if (!inpaintPrompt.trim()) {
      setInpaintError("Décrivez ce que vous souhaitez changer.");
      return;
    }
    setInpaintError(null);
    setSubmitting(true);
    try {
      const maskBlob = await buildMaskBlob();
      await api.inpaintImage(name, feedbackStep, item.id, maskBlob, inpaintPrompt.trim());
      onChanged();
      setInpaintActive(false);
      clearMask();
    } catch (e) {
      setInpaintError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  // ── Shell model (ribbon / sidebar / pager) ────────────────────────────
  const ribbon = buildRibbon();
  const sidebar = buildSidebar();
  const pager =
    items.length > 1 && hasAnyImage
      ? {
          index: safeIdx,
          total: items.length,
          onPrev: () => setIdx(Math.max(0, safeIdx - 1)),
          onNext: () => setIdx(Math.min(items.length - 1, safeIdx + 1)),
        }
      : null;

  useRegisterShell({ ribbon, sidebar, pager }, [
    items.length,
    safeIdx,
    item?.id,
    item?.image_url,
    item?.stale,
    starting,
    isRunning,
    blocked,
    staleItems.length,
    hasAnyImage,
    inpaintActive,
    viewingHistory,
    canRefresh,
    Boolean(onContinue),
    Boolean(onSkip),
    projectActions,
    projectExtraCommands,
    genGroupLabel,
    allowRefine,
  ]);

  function buildSidebar() {
    if (!items.length || !hasAnyImage) return null;
    const order = [];
    const byGroup = new Map();
    items.forEach((it, i) => {
      const g = it.group || "Éléments";
      if (!byGroup.has(g)) {
        byGroup.set(g, []);
        order.push(g);
      }
      byGroup.get(g).push({
        id: String(i),
        label: it.shortLabel || it.label,
        badge: it.stale && it.image_url ? "•" : undefined,
        tone: "peach",
        title: it.stale ? "Le texte a changé depuis cette image" : it.label,
      });
    });
    return {
      sections: order.map((g) => ({ id: g, label: g, items: byGroup.get(g) })),
      activeItem: String(safeIdx),
      onSelect: (id) => setIdx(Number(id)),
    };
  }

  function buildRibbon() {
    const genCommands = [];
    if (!hasAnyImage) {
      genCommands.push({
        id: "generate",
        label: "Lancer",
        icon: <FaImages />,
        tone: "primary",
        onClick: () => start(),
        disabled: starting || blocked || isRunning,
        title: "Lancer la génération avec la qualité définie en préparation.",
      });
    } else {
      genCommands.push({
        id: "resume",
        label: "Reprendre",
        icon: <FaImages />,
        onClick: () => start(),
        disabled: starting || blocked || isRunning,
        title: "Reprendre / compléter la génération.",
      });
      genCommands.push({
        id: "regen-all",
        label: "Tout régénérer",
        icon: <FaArrowRotateRight />,
        onClick: () => setConfirmingRegenAll(true),
        disabled: starting || blocked || isRunning,
        title: "Régénère toutes les images de cette étape.",
      });
      if (staleItems.length > 0) {
        genCommands.push({
          id: "refresh-stale",
          label: `Obsolètes (${staleItems.length})`,
          icon: <FaArrowRotateRight />,
          tone: "primary",
          onClick: () => start({ force_ids: staleItems.map((it) => it.id) }),
          disabled: starting || blocked || isRunning,
          title: `${staleItems.length} image(s) ne correspondent plus au texte modifié.`,
        });
      }
    }
    if (allowSkip && !hasAnyImage) {
      genCommands.push({
        id: "skip",
        label: "Passer",
        icon: <FaForward />,
        onClick: onSkip,
        disabled: starting || blocked || isRunning,
      });
    }

    const groups = [{ id: "gen", label: genGroupLabel, commands: genCommands }];

    // Retouche group — only meaningful once an image exists.
    if (hasAnyImage && allowRefine) {
      const editCommands = [];
      if (canRefresh) {
        editCommands.push({
          id: "regen-one",
          label: "Régénérer",
          icon: <FaArrowRotateRight />,
          onClick: () => setConfirmingRegen(true),
          disabled: itemBusy || isRunning,
          title: "Régénère cette image (qualité actuelle conservée).",
        });
      }
      editCommands.push({
        id: "inpaint",
        label: "Retouche ciblée",
        icon: <FaPaintbrush />,
        ref: inpaintBtnRef,
        active: inpaintActive,
        onClick: () => (inpaintActive ? closeInpaint() : setInpaintActive(true)),
        disabled: !item?.image_url || itemBusy || isRunning || viewingHistory,
        title: viewingHistory
          ? "Restaurez d'abord cette version pour la retoucher."
          : "Peindre une zone et décrire la retouche.",
      });
      editCommands.push({
        id: "refine",
        label: "Retoucher",
        icon: <FaWandMagicSparkles />,
        onClick: () => setRefining(item),
        disabled: !item?.image_url || itemBusy || isRunning || viewingHistory,
        title: "Décrire une retouche en langage naturel.",
      });
      groups.push({ id: "edit", label: "Retouche", commands: editCommands });
    }

    // Album / continue group.
    const albumCommands = [];
    if (onContinue) {
      albumCommands.push({
        id: "continue",
        label: continueLabel.replace(/\s*→\s*$/, ""),
        icon: <FaCheck />,
        tone: "primary",
        onClick: onContinue,
        title: continueLabel,
      });
    }
    if (albumCommands.length) {
      groups.push({ id: "album", label: "Album", commands: albumCommands });
    }

    const projectGroup = projectRibbonGroup(projectActions, projectExtraCommands || []);
    if (projectGroup) groups.push(projectGroup);

    return { groups };
  }

  // ── Render ────────────────────────────────────────────────────────────
  if (isRunning) {
    return (
      <div className="space-y-6">
        <ProgressPanel
          title={`${title} — génération en cours…`}
          job={stream.job}
          events={stream.events}
          onInterrupt={stream.interrupt}
          hint={
            allowRefine
              ? "Vous pouvez feuilleter les images déjà générées. Pour donner un retour, interrompez d'abord la génération."
              : "Vous pouvez feuilleter les images déjà générées pendant l'upscale local."
          }
        />
        {hasAnyImage && item && renderReader()}
      </div>
    );
  }

  if (!hasAnyImage) {
    return (
      <div className="space-y-6">
        {blocked && <RunningBanner job={stream.job} />}
        {stream.terminal && stream.terminal.status !== "completed" && (
          <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
        )}
        <div className="card p-8 text-center">
          <h2 className="text-lg font-semibold mb-2">{title}</h2>
          <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-6">{intro}</p>
          {error && <p className="text-[var(--color-rose-500)] text-sm mb-3">{error}</p>}
          <div className="flex items-center justify-center gap-3">
            <button
              className="btn btn-primary"
              onClick={() => start()}
              disabled={starting || blocked || isRunning}
            >
              {starting ? "Démarrage…" : startLabel}
            </button>
            {allowSkip && onSkip && (
              <button className="btn btn-secondary" onClick={onSkip} disabled={starting || blocked || isRunning}>
                Passer cette étape
              </button>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {blocked && <RunningBanner job={stream.job} />}
      {stream.terminal && stream.terminal.status !== "completed" && (
        <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
      )}
      {error && <p className="text-[var(--color-rose-500)] text-sm">{error}</p>}
      {item && renderReader()}

      {inpaintActive && inpaintPos && createPortal(renderInpaintPopover(), document.body)}

      {allowRefine && refining && (
        <RefineDialog
          title={`Retoucher « ${refining.label} »`}
          hint="Décrivez ce qui doit changer. La génération sera relancée pour cet élément uniquement (les autres restent intacts)."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.imageFeedback(name, feedbackStep, refining.id, text);
            await start({ force_ids: [refining.id] });
          }}
        />
      )}

      {confirmingRegenAll && (
        <ConfirmDialog
          title="Tout régénérer ?"
          body={`Les ${items.length} images de cette étape seront régénérées. Les images existantes seront remplacées. Cette action consomme des crédits API.`}
          confirmLabel="Tout régénérer"
          onConfirm={async () => {
            await start({ force_ids: items.map((it) => it.id) });
          }}
          onClose={() => setConfirmingRegenAll(false)}
        />
      )}

      {confirmingRegen && item && (
        <ConfirmDialog
          title={`Régénérer « ${item.label} » ?`}
          body="L'image actuelle sera remplacée par une nouvelle génération. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await start({ force_ids: [item.id] });
          }}
          onClose={() => setConfirmingRegen(false)}
        />
      )}
    </div>
  );

  // Non-modal retouche panel, portalled to <body> and anchored under the
  // ribbon icon via `inpaintPos`. The mask is still painted on the image in
  // renderReader; this panel only carries the brush, prompt and actions.
  function renderInpaintPopover() {
    return (
      <div
        className="card"
        style={{
          position: "fixed",
          top: inpaintPos.top,
          left: inpaintPos.left,
          width: inpaintPos.width,
          zIndex: 60,
          boxShadow: "0 12px 32px rgb(0 0 0 / 0.18)",
        }}
        role="dialog"
        aria-label="Retouche ciblée"
      >
        <div
          className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-[var(--color-line)] select-none"
          style={{ cursor: "move" }}
          onMouseDown={startInpaintDrag}
          title="Glissez pour déplacer le panneau"
        >
          <span className="text-sm font-semibold truncate">⠿ Retouche ciblée — {item.label}</span>
          <button
            className="btn btn-ghost text-sm px-2 py-0.5"
            onClick={closeInpaint}
            onMouseDown={(e) => e.stopPropagation()}
            disabled={submitting}
            aria-label="Fermer"
            style={{ cursor: "pointer" }}
          >
            ✕
          </button>
        </div>
        <div className="p-4 space-y-3">
          <p className="text-xs text-[var(--color-ink-soft)]">
            Peignez la zone sur l'image, puis décrivez le changement.
          </p>
          <div className="flex items-center gap-2 flex-wrap text-sm">
            <span className="text-[var(--color-ink-soft)]">Pinceau</span>
            <button
              className="status-pager-btn"
              onClick={() => setBrushSize((s) => Math.max(MIN_BRUSH, s - 8))}
              aria-label="Réduire le pinceau"
            >
              −
            </button>
            <input
              type="range"
              min={MIN_BRUSH}
              max={MAX_BRUSH}
              value={brushSize}
              onChange={(e) => setBrushSize(Number(e.target.value))}
              className="w-24"
            />
            <button
              className="status-pager-btn"
              onClick={() => setBrushSize((s) => Math.min(MAX_BRUSH, s + 8))}
              aria-label="Agrandir le pinceau"
            >
              +
            </button>
            <span className="text-[var(--color-mute)] text-xs">{brushSize}px</span>
            <button className="btn btn-ghost text-xs ml-auto" onClick={clearMask} disabled={!hasMask}>
              Effacer le masque
            </button>
          </div>
          <textarea
            className="input textarea"
            rows={3}
            placeholder="Ex. : remplacer le fond par un ciel étoilé, changer la couleur du manteau en rouge…"
            value={inpaintPrompt}
            onChange={(e) => setInpaintPrompt(e.target.value)}
            disabled={itemBusy}
          />
          {inpaintError && <p className="text-xs text-[var(--color-rose-500)]">{inpaintError}</p>}
          <div className="flex justify-end gap-2">
            <button className="btn btn-ghost text-sm" onClick={closeInpaint} disabled={itemBusy}>
              Annuler
            </button>
            <button
              className="btn btn-primary text-sm"
              onClick={submitInpaint}
              disabled={itemBusy || !hasMask || !inpaintPrompt.trim()}
            >
              {submitting ? "Retouche en cours…" : "Lancer la retouche"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  // renderReader is a plain render function (not a nested component) so the
  // image/canvas DOM is inlined into ImageStep's tree and never remounts —
  // the inpaint mask survives re-renders. The reading zone holds only the
  // image + overlay + optional inpaint canvas + description.
  function renderReader() {
    return (
      <div className="card p-4 sm:p-6">
        <div className="flex items-center justify-center gap-2 mb-3 flex-wrap text-sm">
          <span className="font-medium truncate max-w-[18rem]">{item.label}</span>
          {name && filePath && (
            <VersionPicker
              projectName={name}
              filePath={filePath}
              selectedVersionId={selectedVersion.id}
              onSelectVersion={(id, version) => setSelectedVersion({ id, version })}
              onRestored={onChanged}
              disabled={inpaintActive || submitting}
            />
          )}
          {isStale && (
            <span className="chip chip-peach" title="Le texte a été modifié après cette image.">
              Texte modifié
            </span>
          )}
          {viewingHistory && (
            <span
              className="chip"
              style={{ background: "var(--color-paper-soft)", color: "var(--color-primary-700)" }}
              title="Version archivée — actions destructives désactivées."
            >
              version archivée
            </span>
          )}
        </div>

        <div
          className={
            "relative rounded-lg bg-[var(--color-paper-soft)] flex items-center justify-center overflow-hidden " +
            (LAYOUT_CLASS[layout] || LAYOUT_CLASS.portrait)
          }
          aria-busy={itemBusy}
        >
          <div
            className={
              "flex h-full w-full items-center justify-center transition duration-150 " +
              (itemBusy ? "opacity-40 grayscale select-none" : "")
            }
          >
            {item.image_url ? (
              inpaintActive ? (
                <div
                  style={{
                    display: "inline-block",
                    lineHeight: 0,
                    userSelect: "none",
                    touchAction: "none",
                    position: "relative",
                  }}
                >
                  <img
                    ref={imgRef}
                    src={displayedUrl}
                    alt={item.label}
                    className="block max-h-full max-w-full"
                    draggable={false}
                  />
                  <canvas
                    ref={canvasRef}
                    className="absolute inset-0 w-full h-full"
                    style={{ cursor: "crosshair" }}
                    onMouseDown={onPointerDown}
                    onMouseMove={onPointerMove}
                    onMouseUp={onPointerUp}
                    onMouseLeave={onPointerUp}
                    onTouchStart={onPointerDown}
                    onTouchMove={onPointerMove}
                    onTouchEnd={onPointerUp}
                  />
                </div>
              ) : (
                <img src={displayedUrl} alt={item.label} className="max-h-full max-w-full object-contain" />
              )
            ) : (
              <div className="text-sm text-[var(--color-mute)]">{emptyLabel || "Pas encore généré."}</div>
            )}
          </div>
          {itemBusy && (
            <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/60 backdrop-blur-[1px]">
              <div className="flex flex-col items-center gap-3 rounded-lg border border-[var(--color-line)] bg-white px-5 py-4 shadow-sm">
                <span className="inline-block h-8 w-8 rounded-full border-4 border-[var(--color-primary-100)] border-t-[var(--color-primary-500)] animate-spin" />
                <span className="text-sm font-medium text-[var(--color-ink-soft)]">{readerBusyLabel}</span>
              </div>
            </div>
          )}
        </div>

        {!inpaintActive && item.description && (
          <p className="text-sm text-[var(--color-ink-soft)] mt-3 whitespace-pre-wrap">{item.description}</p>
        )}
      </div>
    );
  }
}

function TerminalBanner({ terminal, onClear }) {
  const tone = terminal.status === "interrupted" ? "chip-peach" : "chip-rose";
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
