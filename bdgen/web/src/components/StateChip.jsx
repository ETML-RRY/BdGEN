import { useTranslation } from "react-i18next";

const TONE = {
  preparation: "chip",
  script: "chip chip-sky",
  references: "chip chip-primary",
  compose: "chip chip-rose",
  done: "chip chip-mint",
};

// Renders a small state pill for a project (Preparation / Writing / …). When
// `label` is provided it is used verbatim (e.g. as a label on a row that
// already has access to the translated list); otherwise the chip is built
// from the state id through `home.state<State>`.
export default function StateChip({ state, label }) {
  const { t } = useTranslation();
  if (label) return <span className={TONE[state] || "chip"}>{label}</span>;
  const key = `home.state${state[0]?.toUpperCase()}${state.slice(1)}`;
  return <span className={TONE[state] || "chip"}>{t(key, { defaultValue: state })}</span>;
}
