import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import useJobStream from "./useJobStream.js";
import ProgressPanel from "./ProgressPanel.jsx";
import RunningBanner from "./RunningBanner.jsx";
import RefineDialog from "./RefineDialog.jsx";
import ConfirmDialog from "./ConfirmDialog.jsx";

const QUALITY_LABEL = {
  low: "Brouillon",
  medium: "Standard",
  high: "Final",
};
const QUALITY_CHIP = {
  low: "chip chip-peach",
  medium: "chip chip-sky",
  high: "chip chip-mint",
};

const MIN_BRUSH = 8;
const MAX_BRUSH = 80;
const DEFAULT_BRUSH = 24;

/**
 * Reusable shell for the image-generation steps (references, compose). Each
 * step provides:
 *   - stepId: "references" | "compose"
 *   - title / intro / etc.
 *   - items: [{ id, label, image_url, description?, quality? }]
 *   - supportsQuality: true to enable draft/final mode + per-item upgrade
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
  items,
  emptyLabel,
  layout = "portrait",
  supportsQuality = false,
}) {
  const { name } = useParams();
  const stream = useJobStream({ project: name, step: stepId });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const [refining, setRefining] = useState(null);
  const [idx, setIdx] = useState(0);
  const [confirmingRegenAll, setConfirmingRegenAll] = useState(false);

  const isRunning = stream.matchesThisStep && stream.job?.status === "running";
  const otherStepRunning = stream.job?.status === "running" && !stream.matchesThisStep;
  const blocked = otherStepRunning;
  const hasAnyImage = items.some((it) => it.image_url);

  // Items not yet at "high" quality — surfaced for the per-step "Tout améliorer".
  const draftItems = supportsQuality
    ? items.filter((it) => it.image_url && it.quality && it.quality !== "high")
    : [];
  // Items whose underlying script text was rewritten after the image was
  // generated — the on-disk PNG no longer matches the latest description.
  const staleItems = items.filter((it) => it.stale && it.image_url);

  useEffect(() => {
    if (stream.terminal) onChanged();
  }, [stream.terminal, onChanged]);

  useEffect(() => {
    if (!stream.events.length) return;
    const last = stream.events[stream.events.length - 1];
    if (last?.artifact) onChanged();
  }, [stream.events, onChanged]);

  async function start({ force_ids, quality_override } = {}) {
    if (starting || isRunning) return;
    setError(null);
    setStarting(true);
    try {
      const payload = {};
      if (force_ids) payload.force_ids = force_ids;
      if (quality_override) payload.quality_override = quality_override;
      await api.startStep(name, stepId, payload);
      await stream.refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setStarting(false);
    }
  }

  const flipper =
    items.length > 0 ? (
      <ImageFlipper
        items={items}
        idx={idx}
        setIdx={setIdx}
        layout={layout}
        busy={starting || isRunning}
        busyLabel={isRunning ? "Génération en cours..." : "Préparation..."}
        onRefine={isRunning || blocked || !allowRefine ? null : (item) => setRefining(item)}
        onInpaint={isRunning || blocked || !allowRefine ? null : async (item, maskBlob, prompt) => {
          await api.inpaintImage(name, feedbackStep, item.id, maskBlob, prompt);
          onChanged();
        }}
        onUpgrade={
          isRunning || blocked || !supportsQuality
            ? null
            : (item) => start({ force_ids: [item.id], quality_override: "high" })
        }
        onRefresh={
          isRunning || blocked
            ? null
            : (item) =>
                start({
                  force_ids: [item.id],
                  quality_override: item.quality || undefined,
                })
        }
        emptyLabel={emptyLabel}
      />
    ) : null;

  if (isRunning) {
    return (
      <div className="space-y-6">
        <ProgressPanel
          title={`${title} — génération en cours…`}
          job={stream.job}
          events={stream.events}
          onInterrupt={stream.interrupt}
          hint={allowRefine
            ? "Vous pouvez feuilleter les images déjà générées. Pour donner un retour, interrompez d'abord la génération."
            : "Vous pouvez feuilleter les images déjà générées pendant l'upscale local."}
        />
        {flipper}
      </div>
    );
  }

  // Idle (never started, or finished, or interrupted)
  if (!hasAnyImage) {
    return (
      <div className="space-y-6">
        {blocked && <RunningBanner job={stream.job} />}
        {stream.terminal && stream.terminal.status !== "completed" && (
          <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
        )}
        <div className="card p-8 text-center">
          <h2 className="text-lg font-semibold mb-2">{title}</h2>
          <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-6">
            {intro}
          </p>
          {error && (
            <p className="text-[var(--color-rose-500)] text-sm mb-3">{error}</p>
          )}
          <div className="flex justify-center flex-wrap gap-3">
            {supportsQuality && (
              <button
                className="btn btn-secondary"
                onClick={() => start({ quality_override: "low" })}
                disabled={starting || blocked}
                title="Génération basse qualité — beaucoup moins coûteuse, idéale pour valider l'ensemble avant de monter en qualité."
              >
                Brouillon (économique)
              </button>
            )}
            <button
              className="btn btn-primary"
              onClick={() =>
                start(supportsQuality ? { quality_override: "high" } : {})
              }
              disabled={starting || blocked}
            >
              {starting
                ? "Démarrage…"
                : supportsQuality
                ? "Qualité finale"
                : "Lancer la génération"}
            </button>
            {allowSkip && (
              <button
                className="btn btn-ghost"
                onClick={onSkip}
                disabled={starting || blocked}
              >
                Passer
              </button>
            )}
          </div>
          {supportsQuality && (
            <p className="text-xs text-[var(--color-mute)] mt-4 max-w-md mx-auto">
              Astuce&nbsp;: lancez d'abord en brouillon, puis améliorez
              élément par élément ce qui en vaut la peine.
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {blocked && <RunningBanner job={stream.job} />}
      {stream.terminal && stream.terminal.status !== "completed" && (
        <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
      )}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="flex gap-2 flex-wrap">
            <button
              className="btn btn-ghost text-sm"
              onClick={() => setConfirmingRegenAll(true)}
              disabled={starting || blocked}
              title="Régénère toutes les images de cette étape"
            >
              ↻ Tout régénérer
            </button>
            {staleItems.length > 0 && (
              <button
                className="btn btn-primary text-sm"
                onClick={() =>
                  start({
                    force_ids: staleItems.map((it) => it.id),
                  })
                }
                disabled={starting || blocked}
                title={`${staleItems.length} image(s) ne correspondent plus au texte modifié`}
              >
                ↻ Rafraîchir les obsolètes ({staleItems.length})
              </button>
            )}
            {supportsQuality ? (
              <>
                <button
                  className="btn btn-ghost text-sm"
                  onClick={() => start({ quality_override: "low" })}
                  disabled={starting || blocked}
                  title="Génère ce qui manque encore en brouillon. Les éléments déjà en final sont conservés."
                >
                  Compléter en brouillon
                </button>
                <button
                  className="btn btn-secondary text-sm"
                  onClick={() =>
                    start({
                      force_ids: draftItems.length > 0
                        ? draftItems.map((it) => it.id)
                        : undefined,
                      quality_override: "high",
                    })
                  }
                  disabled={starting || blocked}
                  title={
                    draftItems.length > 0
                      ? `Régénère ${draftItems.length} brouillon(s) en final et complète les éléments manquants en final.`
                      : "Génère ce qui manque encore en qualité finale."
                  }
                >
                  {draftItems.length > 0
                    ? `Tout finaliser (${draftItems.length} brouillon${draftItems.length > 1 ? "s" : ""})`
                    : "Compléter en final"}
                </button>
              </>
            ) : (
              <button
                className="btn btn-secondary text-sm"
                onClick={() => start()}
                disabled={starting || blocked}
              >
                {starting ? "Démarrage…" : "Reprendre / compléter"}
              </button>
            )}
            {onContinue && (
              <button className="btn btn-primary text-sm" onClick={onContinue}>
                {continueLabel}
              </button>
            )}
          </div>
        </div>
        {error && (
          <p className="text-[var(--color-rose-500)] text-sm mb-3">{error}</p>
        )}
        {flipper}
      </div>

      {allowRefine && refining && (
        <RefineDialog
          title={`Retoucher « ${refining.label} »`}
          hint="Décrivez ce qui doit changer. La génération sera relancée pour cet élément uniquement (les autres restent intacts)."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.imageFeedback(name, feedbackStep, refining.id, text);
            await start({
              force_ids: [refining.id],
              quality_override: refining.quality || undefined,
            });
          }}
        />
      )}

      {confirmingRegenAll && (
        <ConfirmDialog
          title="Tout régénérer ?"
          body={`Les ${items.length} images de cette étape seront régénérées. Les images existantes seront remplacées. Cette action consomme des crédits API.`}
          confirmLabel="Tout régénérer"
          onConfirm={async () => {
            await start({
              force_ids: items.map((it) => it.id),
            });
          }}
          onClose={() => setConfirmingRegenAll(false)}
        />
      )}
    </div>
  );
}

function ImageFlipper({
  items,
  idx,
  setIdx,
  layout,
  busy = false,
  busyLabel = "Génération en cours...",
  onRefine,
  onInpaint,
  onUpgrade,
  onRefresh,
  emptyLabel,
}) {
  const [confirmingRegen, setConfirmingRegen] = useState(false);
  const [inpaintActive, setInpaintActive] = useState(false);
  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasMask, setHasMask] = useState(false);
  const [inpaintPrompt, setInpaintPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [inpaintError, setInpaintError] = useState(null);
  const canvasRef = useRef(null);
  const imgRef = useRef(null);
  const lastPos = useRef(null);

  const safeIdx = Math.max(0, Math.min(idx, items.length - 1));
  const item = items[safeIdx];
  const canUpgrade = onUpgrade && item.image_url && item.quality && item.quality !== "high";
  const isStale = !!item.stale && !!item.image_url;
  const canRefresh = onRefresh && item.image_url;
  const readerBusy = busy || submitting;
  const readerBusyLabel = submitting ? "Retouche en cours..." : busyLabel;

  useEffect(() => {
    setInpaintActive(false);
    setHasMask(false);
    setInpaintPrompt("");
    setInpaintError(null);
    lastPos.current = null;
  }, [safeIdx]);

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
          maskData.data[i] = 0; maskData.data[i + 1] = 0;
          maskData.data[i + 2] = 0; maskData.data[i + 3] = 0;
        } else {
          maskData.data[i] = 255; maskData.data[i + 1] = 255;
          maskData.data[i + 2] = 255; maskData.data[i + 3] = 255;
        }
      }
      ctx.putImageData(maskData, 0, 0);
      offscreen.toBlob(resolve, "image/png");
    });
  }

  async function submitInpaint() {
    if (!hasMask) { setInpaintError("Dessinez d'abord la zone à retoucher."); return; }
    if (!inpaintPrompt.trim()) { setInpaintError("Décrivez ce que vous souhaitez changer."); return; }
    setInpaintError(null);
    setSubmitting(true);
    try {
      const maskBlob = await buildMaskBlob();
      await onInpaint(item, maskBlob, inpaintPrompt.trim());
      setInpaintActive(false);
      clearMask();
    } catch (e) {
      setInpaintError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="relative">
      <div
        className={
          "transition duration-150 " +
          (readerBusy ? "opacity-40 grayscale pointer-events-none select-none" : "")
        }
        aria-busy={readerBusy}
      >
      <div className="flex items-center justify-between mb-3 gap-2">
        <button
          className="btn btn-ghost text-sm"
          disabled={safeIdx === 0 || inpaintActive || readerBusy}
          onClick={() => setIdx(safeIdx - 1)}
        >
          ← Précédent
        </button>
        <div className="flex items-center gap-2 min-w-0 flex-1 justify-center flex-wrap">
          <span className="text-sm font-medium truncate text-center">
            {item.label}
            <span className="text-[var(--color-mute)] ml-2">
              ({safeIdx + 1}/{items.length})
            </span>
          </span>
          {item.image_url && item.quality && (
            <span
              className={QUALITY_CHIP[item.quality] || "chip"}
              title={`Qualité de génération : ${item.quality}`}
            >
              {QUALITY_LABEL[item.quality] || item.quality}
            </span>
          )}
          {isStale && (
            <span
              className="chip chip-peach"
              title="Le texte a été modifié après cette image. Régénérez pour aligner le visuel sur la nouvelle description."
            >
              Texte modifié
            </span>
          )}
        </div>
        <button
          className="btn btn-ghost text-sm"
          disabled={safeIdx === items.length - 1 || inpaintActive || readerBusy}
          onClick={() => setIdx(safeIdx + 1)}
        >
          Suivant →
        </button>
      </div>
      <div
        className={
          "rounded-lg bg-[var(--color-paper-soft)] flex items-center justify-center overflow-hidden " +
          (layout === "portrait" ? "aspect-[2/3]" : "aspect-square")
        }
      >
        {item.image_url ? (
          inpaintActive ? (
            <div
              style={{ display: "inline-block", lineHeight: 0, userSelect: "none", touchAction: "none", position: "relative" }}
            >
              <img
                ref={imgRef}
                src={item.image_url}
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
            <img
              src={item.image_url}
              alt={item.label}
              className={
                "max-h-full max-w-full object-contain " +
                (isStale ? "opacity-60 ring-2 ring-[var(--color-peach-300)]" : "")
              }
            />
          )
        ) : (
          <div className="text-sm text-[var(--color-mute)]">
            {emptyLabel || "Pas encore généré."}
          </div>
        )}
      </div>

      {inpaintActive && (
        <div className="mt-3 space-y-3">
          <p className="text-xs text-[var(--color-ink-soft)]">
            Peignez la zone à modifier, puis décrivez la retouche souhaitée.
          </p>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs text-[var(--color-ink-soft)]">Pinceau :</span>
            <button
              className="btn btn-ghost text-xs px-2 py-1"
              onClick={() => setBrushSize((s) => Math.max(MIN_BRUSH, s - 8))}
            >
              −
            </button>
            <input
              type="range"
              min={MIN_BRUSH}
              max={MAX_BRUSH}
              value={brushSize}
              onChange={(e) => setBrushSize(Number(e.target.value))}
              className="w-28"
            />
            <button
              className="btn btn-ghost text-xs px-2 py-1"
              onClick={() => setBrushSize((s) => Math.min(MAX_BRUSH, s + 8))}
            >
              +
            </button>
            <span className="text-xs text-[var(--color-mute)]">{brushSize}px</span>
            <button
              className="btn btn-ghost text-xs ml-auto"
              onClick={clearMask}
              disabled={!hasMask}
            >
              Effacer le masque
            </button>
          </div>
          <label className="block text-xs font-medium text-[var(--color-ink-soft)]">
            Que souhaitez-vous changer dans cette zone ?
          </label>
          <textarea
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-paper-soft)] px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            rows={2}
            placeholder="Ex. : remplacer le fond par un ciel étoilé, changer la couleur du manteau en rouge…"
            value={inpaintPrompt}
            onChange={(e) => setInpaintPrompt(e.target.value)}
            disabled={readerBusy}
          />
          {inpaintError && (
            <p className="text-xs text-[var(--color-rose-500)]">{inpaintError}</p>
          )}
          <div className="flex justify-end gap-2">
            <button
              className="btn btn-ghost text-sm"
              onClick={() => { setInpaintActive(false); clearMask(); }}
              disabled={readerBusy}
            >
              Annuler
            </button>
            <button
              className="btn btn-primary text-sm"
              onClick={submitInpaint}
              disabled={readerBusy || !hasMask || !inpaintPrompt.trim()}
            >
              {submitting ? "Retouche en cours…" : "Lancer la retouche"}
            </button>
          </div>
        </div>
      )}

      {!inpaintActive && item.description && (
        <p className="text-sm text-[var(--color-ink-soft)] mt-3 whitespace-pre-wrap">
          {item.description}
        </p>
      )}
      {!inpaintActive && (onRefine || onInpaint || canUpgrade || canRefresh) && (
        <div className="flex justify-end gap-2 mt-3 flex-wrap">
          {canRefresh && (
            <button
              className="btn btn-secondary text-sm"
              onClick={() => setConfirmingRegen(true)}
              disabled={readerBusy}
              title="Régénère cette image (la qualité actuelle est conservée)."
            >
              ↻ Régénérer
            </button>
          )}
          {canUpgrade && (
            <button
              className="btn btn-primary text-sm"
              onClick={() => onUpgrade(item)}
              disabled={readerBusy}
              title="Régénère cet élément seul en haute qualité."
            >
              ✨ Améliorer la qualité
            </button>
          )}
          {onInpaint && (
            <button
              className="btn btn-ghost text-sm"
              onClick={() => setInpaintActive(true)}
              disabled={!item.image_url || readerBusy}
              title="Peindre une zone et décrire la retouche souhaitée."
            >
              🖌 Retouche ciblée
            </button>
          )}
          {onRefine && (
            <button
              className="btn btn-ghost text-sm"
              onClick={() => onRefine(item)}
              disabled={!item.image_url || readerBusy}
            >
              Retoucher cet élément
            </button>
          )}
        </div>
      )}

      {confirmingRegen && (
        <ConfirmDialog
          title={`Régénérer « ${item.label} » ?`}
          body="L'image actuelle sera remplacée par une nouvelle génération. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => { await onRefresh(item); }}
          onClose={() => setConfirmingRegen(false)}
        />
      )}
      </div>

      {readerBusy && (
        <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/60 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-3 rounded-lg border border-[var(--color-line)] bg-white px-5 py-4 shadow-sm">
            <span className="inline-block h-8 w-8 rounded-full border-4 border-[var(--color-primary-100)] border-t-[var(--color-primary-500)] animate-spin" />
            <span className="text-sm font-medium text-[var(--color-ink-soft)]">
              {readerBusyLabel}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

function TerminalBanner({ terminal, onClear }) {
  const tone =
    terminal.status === "interrupted" ? "chip-peach" : "chip-rose";
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
