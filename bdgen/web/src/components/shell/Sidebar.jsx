import { useTranslation } from "react-i18next";
import { useAppContext } from "../../context/AppContext.jsx";

/**
 * Left sub-navigation for the active phase, rendered from the `sidebar` slot:
 *   { sections: [{ id, label, items: [{ id, label, badge, tone, disabled }] }],
 *     activeItem, onSelect }
 * Renders nothing when no model is registered (the layout collapses the column).
 */
export default function Sidebar() {
  const { sidebar } = useAppContext();
  const { t } = useTranslation();
  if (!sidebar || !sidebar.sections?.length) return null;

  const { sections, activeItem, onSelect } = sidebar;

  return (
    <aside className="app-sidebar" aria-label={t("sidebar.subsectionsAria")}>
      {sections.map((section) => (
        <div key={section.id} className="sidebar-section">
          {section.label && <div className="sidebar-section-label">{section.label}</div>}
          {section.items.map((item) => (
            <button
              key={item.id}
              type="button"
              className={"sidebar-item" + (item.id === activeItem ? " active" : "")}
              onClick={() => onSelect?.(item.id)}
              disabled={item.disabled}
              title={item.title || item.label}
            >
              <span className="sidebar-item-label">{item.label}</span>
              {item.badge != null && (
                <span className={"sidebar-badge" + (item.tone ? " " + item.tone : "")}>{item.badge}</span>
              )}
            </button>
          ))}
        </div>
      ))}
    </aside>
  );
}
