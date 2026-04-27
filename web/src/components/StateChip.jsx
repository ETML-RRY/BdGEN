const TONE = {
  preparation: "chip",
  script: "chip chip-sky",
  references: "chip chip-primary",
  wireframes: "chip chip-peach",
  compose: "chip chip-rose",
  done: "chip chip-mint",
};

export default function StateChip({ state, label }) {
  return <span className={TONE[state] || "chip"}>{label || state}</span>;
}
