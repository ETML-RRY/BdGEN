import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api.js";
import useJobStream from "./useJobStream.js";
import ProgressPanel from "./ProgressPanel.jsx";
import RefineDialog from "./RefineDialog.jsx";

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

/**
 * Reusable shell for the image-generation steps (references, compose). Each
 * step provides:
 *   - stepId: "references" | "compose"
 *   - title / intro / etc.
 *   - items: [{ id, label, image_url, description?, quality? }]
 *   - supportsQuality: true to enable draft/final mode + per-item upgrade
 */
export default function ImageStep({
  project,
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

  const isRunning = stream.matchesThisStep && stream.job?.status === "running";
  const otherStepRunning = stream.job?.status === "running" && !stream.matchesThisStep;
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
  }, [stream.events.length, onChanged]);

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

  if (otherStepRunning) {
    return (
      <div className="card p-6 text-sm">
        Une autre génération est en cours&nbsp;: étape «&nbsp;{stream.job.step}&nbsp;»
        sur le projet «&nbsp;{stream.job.project}&nbsp;». Patientez avant de
        lancer cette étape.
      </div>
    );
  }

  const flipper =
    items.length > 0 ? (
      <ImageFlipper
        items={items}
        idx={idx}
        setIdx={setIdx}
        layout={layout}
        onRefine={isRunning || !allowRefine ? null : (item) => setRefining(item)}
        onUpgrade={
          isRunning || !supportsQuality
            ? null
            : (item) => start({ force_ids: [item.id], quality_override: "high" })
        }
        onRefresh={
          isRunning
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
                disabled={starting}
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
              disabled={starting}
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
                disabled={starting}
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
      {stream.terminal && stream.terminal.status !== "completed" && (
        <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
      )}
      <div className="card p-6">
        <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="flex gap-2 flex-wrap">
            {staleItems.length > 0 && (
              <button
                className="btn btn-primary text-sm"
                onClick={() =>
                  start({
                    force_ids: staleItems.map((it) => it.id),
                  })
                }
                disabled={starting}
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
                  disabled={starting}
                  title="Génère ce qui manque encore en brouillon. Les éléments déjà en final sont conservés."
                >
                  Compléter en brouillon
                </button>
                <button
                  className="btn btn-secondary text-sm"
                  onClick={() =>
                    start({
                      // Upgrade any existing draft to final AND fill in
                      // missing items at final quality, in one pass.
                      force_ids: draftItems.length > 0
                        ? draftItems.map((it) => it.id)
                        : undefined,
                      quality_override: "high",
                    })
                  }
                  disabled={starting}
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
                disabled={starting}
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
            // Force-regenerate this single asset, preserving its current
            // quality level (a draft retouche stays in draft).
            await start({
              force_ids: [refining.id],
              quality_override: refining.quality || undefined,
            });
          }}
        />
      )}
    </div>
  );
}

function ImageFlipper({ items, idx, setIdx, layout, onRefine, onUpgrade, onRefresh, emptyLabel }) {
  const safeIdx = Math.max(0, Math.min(idx, items.length - 1));
  const item = items[safeIdx];
  const canUpgrade = onUpgrade && item.image_url && item.quality && item.quality !== "high";
  const isStale = !!item.stale && !!item.image_url;
  const canRefresh = onRefresh && isStale;

  return (
    <div>
      <div className="flex items-center justify-between mb-3 gap-2">
        <button
          className="btn btn-ghost text-sm"
          disabled={safeIdx === 0}
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
          disabled={safeIdx === items.length - 1}
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
          <img
            src={item.image_url}
            alt={item.label}
            className={
              "max-h-full max-w-full object-contain " +
              (isStale ? "opacity-60 ring-2 ring-[var(--color-peach-300)]" : "")
            }
          />
        ) : (
          <div className="text-sm text-[var(--color-mute)]">
            {emptyLabel || "Pas encore généré."}
          </div>
        )}
      </div>
      {item.description && (
        <p className="text-sm text-[var(--color-ink-soft)] mt-3 whitespace-pre-wrap">
          {item.description}
        </p>
      )}
      {(onRefine || canUpgrade || canRefresh) && (
        <div className="flex justify-end gap-2 mt-3 flex-wrap">
          {canRefresh && (
            <button
              className="btn btn-primary text-sm"
              onClick={() => onRefresh(item)}
              title="Régénère cette image avec la dernière version du texte (qualité actuelle conservée)."
            >
              ↻ Régénérer l'image
            </button>
          )}
          {canUpgrade && (
            <button
              className={(canRefresh ? "btn btn-secondary" : "btn btn-primary") + " text-sm"}
              onClick={() => onUpgrade(item)}
              title="Régénère cet élément seul en haute qualité."
            >
              ✨ Améliorer la qualité
            </button>
          )}
          {onRefine && (
            <button
              className="btn btn-secondary text-sm"
              onClick={() => onRefine(item)}
              disabled={!item.image_url}
            >
              Retoucher cet élément
            </button>
          )}
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
