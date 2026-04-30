import { NavLink } from "react-router-dom";

export default function StepNav({ steps, active, baseUrl }) {
  const activeIdx = steps.findIndex((s) => s.id === active);
  return (
    <nav className="card p-4">
      <ol className="flex items-center justify-between gap-2 overflow-x-auto">
        {steps.map((s, i) => {
          const done = i < activeIdx;
          const current = s.id === active;
          return (
            <li key={s.id} className="flex items-center flex-1 min-w-0">
              <NavLink
                to={`${baseUrl}/${s.id}`}
                className={({ isActive }) =>
                  "flex items-center gap-2 px-2 py-1 rounded-md min-w-0 " +
                  (isActive
                    ? "text-[var(--color-primary-700)]"
                    : "text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]")
                }
              >
                <span
                  className={
                    "flex items-center justify-center w-7 h-7 rounded-full text-xs font-semibold flex-shrink-0 " +
                    (current
                      ? "bg-[var(--color-primary-500)] text-white"
                      : done
                      ? "bg-[var(--color-mint-200)] text-[var(--color-mint-700)]"
                      : "bg-[var(--color-paper-soft)] text-[var(--color-mute)] border border-[var(--color-line)]")
                  }
                >
                  {done ? "✓" : i + 1}
                </span>
                <span className="text-sm truncate">
                  {s.label}
                  {s.optional && (
                    <span className="text-[var(--color-mute)] text-xs"> (optionnel)</span>
                  )}
                </span>
              </NavLink>
              {i < steps.length - 1 && (
                <span className="flex-1 border-t border-[var(--color-line)] mx-1" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
