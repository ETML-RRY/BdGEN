// Project workflow steps.
//
// This file holds the *structural* definition: id, optional flag, and
// ordering. Labels are NOT hardcoded — consumers should translate them
// via `t("steps.<id>")` (see `useTranslatedSteps` / `useStepLabelMap`
// in `bdgen/web/src/hooks/useTranslatedSteps.js`).

import { SHOW_UPSCALE } from "./featureFlags.js";

export const STEPS = [
  { id: "preparation", optional: false },
  { id: "script", optional: false },
  { id: "references", optional: false },
  { id: "compose", optional: false },
  ...(SHOW_UPSCALE ? [{ id: "upscale", optional: true }] : []),
];
