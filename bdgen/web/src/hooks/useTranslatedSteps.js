// Hooks for translating the project step labels.
//
// The structural definition (id, optional flag, ordering) lives in
// `bdgen/web/src/steps.js`. This module returns translated copies of
// that data so that consumers (Ribbon, StatusBar, Wizard, …) can render
// labels in the current UI language.

import { useTranslation } from "react-i18next";
import { STEPS } from "../steps.js";

export function useTranslatedSteps() {
  const { t } = useTranslation();
  return STEPS.map((s) => ({ ...s, label: t(`steps.${s.id}`) }));
}

export function useStepLabelMap() {
  const steps = useTranslatedSteps();
  return Object.fromEntries(steps.map((s) => [s.id, s.label]));
}
