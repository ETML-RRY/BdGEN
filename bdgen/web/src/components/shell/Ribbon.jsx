import { NavLink, Link, useLocation } from "react-router-dom";
import { FiHome } from "react-icons/fi";
import { useAppContext } from "../../context/AppContext.jsx";
import { STEPS } from "../../steps.js";

/**
 * Office-style ribbon. Its tab strip is the project's phase navigation
 * (Préparation ▸ Écriture ▸ Références ▸ Planches). The BD title now lives in
 * the application title bar (AppBar). The body below renders the command groups
 * published by the active phase through the `ribbon` slot:
 *   { groups: [{ id, label, commands: [command] }] }
 *   command = { id, label, icon, onClick, disabled, active, tone, title, size, ref }
 * `ref` (optional) is forwarded to the command's button so a phase can anchor a
 * popover under it (e.g. the targeted-retouch panel).
 *
 * The ribbon belongs to a project — outside one (Home / Réglages) there are no
 * phases, so it renders nothing.
 */
export default function Ribbon() {
  const { ribbon, projectMeta } = useAppContext();
  const location = useLocation();

  if (!projectMeta) return null;

  const baseUrl = `/projects/${encodeURIComponent(projectMeta.name)}`;
  const activeStep = location.pathname.split("/").pop();
  const activeIdx = STEPS.findIndex((s) => s.id === activeStep);
  const groups = ribbon?.groups ?? [];

  return (
    <div className="ribbon">
      <div className="ribbon-tabs">
        <Link to="/" className="ribbon-home" title="Retour à l'accueil" aria-label="Retour à l'accueil">
          <FiHome aria-hidden />
        </Link>
        <div className="ribbon-tablist" role="tablist" aria-label="Phases du projet">
          {STEPS.map((step, i) => {
            const done = activeIdx >= 0 && i < activeIdx;
            return (
              <NavLink
                key={step.id}
                to={`${baseUrl}/${step.id}`}
                role="tab"
                className={({ isActive }) => "ribbon-tab" + (isActive ? " active" : done ? " done" : "")}
              >
                <span className="ribbon-tab-marker" aria-hidden="true">
                  {done ? "✓" : i + 1}
                </span>
                <span>{step.label}</span>
                {step.optional && <span className="phase-tab-opt">(opt.)</span>}
              </NavLink>
            );
          })}
        </div>
      </div>
      {groups.length > 0 && (
        <div className="ribbon-groups">
          {groups.map((group) => (
            <RibbonGroup key={group.id} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}

function RibbonGroup({ group }) {
  return (
    <div className="ribbon-group">
      <div className="ribbon-group-commands">
        {group.commands.map((cmd) => (
          <RibbonCommand key={cmd.id} command={cmd} />
        ))}
      </div>
      {group.label && <div className="ribbon-group-label">{group.label}</div>}
    </div>
  );
}

function RibbonCommand({ command }) {
  const { label, icon, onClick, disabled, active, tone, title, size = "lg", ref } = command;
  const cls = [
    "ribbon-cmd",
    size === "sm" ? "ribbon-cmd-sm" : "ribbon-cmd-lg",
    active ? "active" : "",
    tone ? "ribbon-cmd-" + tone : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <button ref={ref} type="button" className={cls} onClick={onClick} disabled={disabled} title={title || label}>
      {icon && <span className="ribbon-cmd-icon" aria-hidden="true">{icon}</span>}
      <span className="ribbon-cmd-label">{label}</span>
    </button>
  );
}
