import { SHOW_UPSCALE } from "./featureFlags.js";

export const STEPS = [
  { id: "preparation", label: "Préparation" },
  { id: "script", label: "Écriture" },
  { id: "references", label: "Références" },
  { id: "compose", label: "Planches" },
  ...(SHOW_UPSCALE ? [{ id: "upscale", label: "Upscale", optional: true }] : []),
];

export const STEP_LABEL_MAP = Object.fromEntries(STEPS.map((s) => [s.id, s.label]));
