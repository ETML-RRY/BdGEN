import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

const MIN_BRUSH = 8;
const MAX_BRUSH = 80;
const DEFAULT_BRUSH = 24;

export default function InpaintModal({ item, onClose, onSubmit }) {
  const { t } = useTranslation();
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH);
  const [isDrawing, setIsDrawing] = useState(false);
  const [hasMask, setHasMask] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const lastPos = useRef(null);

  // Sync canvas dimensions to the rendered image
  function syncCanvas() {
    const img = imageRef.current;
    const cvs = canvasRef.current;
    if (!img || !cvs) return;
    const rect = img.getBoundingClientRect();
    if (cvs.width !== rect.width || cvs.height !== rect.height) {
      // Preserve existing drawing while resizing
      const tmp = document.createElement("canvas");
      tmp.width = cvs.width;
      tmp.height = cvs.height;
      tmp.getContext("2d").drawImage(cvs, 0, 0);
      cvs.width = rect.width;
      cvs.height = rect.height;
      cvs.getContext("2d").drawImage(tmp, 0, 0, rect.width, rect.height);
    }
  }

  useEffect(() => {
    const img = imageRef.current;
    if (!img) return;
    if (img.complete) {
      syncCanvas();
    } else {
      img.addEventListener("load", syncCanvas);
      return () => img.removeEventListener("load", syncCanvas);
    }
  });

  function getPos(e) {
    const cvs = canvasRef.current;
    if (!cvs) return null;
    const rect = cvs.getBoundingClientRect();
    const client = e.touches ? e.touches[0] : e;
    return {
      x: client.clientX - rect.left,
      y: client.clientY - rect.top,
    };
  }

  function paint(pos) {
    const cvs = canvasRef.current;
    if (!cvs) return;
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
          // Painted → transparent (AI regenerates this area)
          maskData.data[i] = 0;
          maskData.data[i + 1] = 0;
          maskData.data[i + 2] = 0;
          maskData.data[i + 3] = 0;
        } else {
          // Not painted → white opaque (AI keeps this area)
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

  async function handleSubmit() {
    if (!hasMask) {
      setError(t("dialogs.inpaint.drawFirst"));
      return;
    }
    if (!prompt.trim()) {
      setError(t("dialogs.inpaint.describeFirst"));
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const maskBlob = await buildMaskBlob();
      await onSubmit(maskBlob, prompt.trim());
      onClose();
    } catch (e) {
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div
        className="relative bg-[var(--color-paper)] rounded-xl shadow-2xl flex flex-col"
        style={{ maxWidth: "min(92vw, 720px)", maxHeight: "92vh", width: "100%" }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-5 pt-5 pb-3 border-b border-[var(--color-border)]">
          <h2 className="text-base font-semibold">
            {t("dialogs.inpaint.title", { label: item.label })}
          </h2>
          <button
            className="btn btn-ghost text-sm"
            onClick={onClose}
            disabled={submitting}
          >
            ✕
          </button>
        </div>

        {/* Canvas area */}
        <div className="flex-1 overflow-auto px-5 pt-4">
          <p className="text-xs text-[var(--color-ink-soft)] mb-3">
            {t("dialogs.inpaint.instruction")}
          </p>
          <div
            className="relative inline-block rounded overflow-hidden"
            style={{ cursor: "crosshair", userSelect: "none", touchAction: "none" }}
          >
            <img
              ref={imageRef}
              src={item.image_url}
              alt={item.label}
              className="block max-w-full"
              style={{ maxHeight: "45vh", objectFit: "contain" }}
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

          {/* Brush controls */}
          <div className="flex items-center gap-3 mt-3 flex-wrap">
            <span className="text-xs text-[var(--color-ink-soft)]">{t("dialogs.inpaint.brushLabel")}</span>
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
              {t("dialogs.inpaint.clearMask")}
            </button>
          </div>
        </div>

        {/* Prompt + footer */}
        <div className="px-5 pt-3 pb-5 space-y-3 border-t border-[var(--color-border)] mt-3">
          <label className="block text-xs font-medium text-[var(--color-ink-soft)]">
            {t("dialogs.inpaint.promptLabel")}
          </label>
          <textarea
            className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-paper-soft)] px-3 py-2 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            rows={2}
            placeholder={t("dialogs.inpaint.promptPlaceholder")}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={submitting}
          />
          {error && (
            <p className="text-xs text-[var(--color-rose-500)]">{error}</p>
          )}
          <div className="flex justify-end gap-2">
            <button
              className="btn btn-ghost text-sm"
              onClick={onClose}
              disabled={submitting}
            >
              {t("common.cancel")}
            </button>
            <button
              className="btn btn-primary text-sm"
              onClick={handleSubmit}
              disabled={submitting || !hasMask || !prompt.trim()}
            >
              {submitting ? t("dialogs.inpaint.inProgress") : t("dialogs.inpaint.submit")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
