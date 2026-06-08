import { Link, NavLink, useLocation } from "react-router-dom";
import { FiMinus, FiSquare, FiX, FiFolder, FiKey } from "react-icons/fi";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppContext } from "../context/AppContext.jsx";
import LanguageSwitcher from "../i18n/LanguageSwitcher.jsx";

export default function AppBar({ hideNav = false }) {
  const { t } = useTranslation();
  const isDesktop = Boolean(window.bdgenDesktop);
  const isMac = window.bdgenDesktop?.platform === "darwin";
  const [maximized, setMaximized] = useState(false);
  const location = useLocation();
  const { projectMeta } = useAppContext();

  useEffect(() => {
    if (!isDesktop) return;
    window.bdgenDesktop.isMaximized().then(setMaximized);
    return window.bdgenDesktop.onMaximizedChange(setMaximized);
  }, [isDesktop]);

  const primaryNav = useMemo(
    () => [
      { id: "projects", label: t("nav.projects"), to: "/", icon: FiFolder, match: (p) => !p.startsWith("/settings") },
      { id: "keys", label: t("nav.apiKeys"), to: "/settings/secrets", icon: FiKey, match: (p) => p.startsWith("/settings") },
    ],
    [t],
  );

  const leftContent = (
    <div className={`flex items-center gap-3 min-w-0 ${isDesktop ? "desktop-no-drag" : ""}`}>
      <Link
        to="/"
        className="flex items-center gap-2 font-semibold text-sm hover:text-[var(--color-primary-700)] transition-colors flex-shrink-0"
      >
        <img src="/bd_gen_logo.svg" alt={t("appBar.logoAlt")} className="w-7 h-7 object-contain" />
        <span>BdGEN</span>
      </Link>
      {!hideNav && (
        <nav className="primary-nav" aria-label={t("nav.primaryAria")}>
          {primaryNav.map((item) => {
            const Icon = item.icon;
            const active = item.match(location.pathname);
            return (
              <NavLink
                key={item.id}
                to={item.to}
                className={"primary-nav-item" + (active ? " active" : "")}
              >
                <Icon aria-hidden />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      )}
    </div>
  );

  // Title of the currently-open BD — centered in the title bar. Absolutely
  // positioned so it stays centered on the window regardless of the left/right
  // content widths. `pointer-events-none` keeps the desktop drag region and the
  // window controls underneath fully usable.
  const centerTitle = projectMeta ? (
    <div className="app-title-center" title={projectMeta.displayName || projectMeta.name}>
      {projectMeta.displayName || projectMeta.name}
    </div>
  ) : null;

  const rightContent = (
    <div className={`flex h-full items-center gap-2 ${isDesktop ? "desktop-no-drag" : ""}`}>
      <LanguageSwitcher />
      {isDesktop && !isMac && (
        <div className="flex h-full ml-1">
          <button
            type="button"
            className="window-control"
            title={t("appBar.minimize")}
            onClick={() => window.bdgenDesktop.minimize()}
          >
            <FiMinus aria-hidden />
          </button>
          <button
            type="button"
            className="window-control"
            title={maximized ? t("appBar.restore") : t("appBar.maximize")}
            onClick={() => window.bdgenDesktop.toggleMaximize().then(setMaximized)}
          >
            <FiSquare aria-hidden />
          </button>
          <button
            type="button"
            className="window-control window-control-close"
            title={t("appBar.close")}
            onClick={() => window.bdgenDesktop.close()}
          >
            <FiX aria-hidden />
          </button>
        </div>
      )}
    </div>
  );

  if (isDesktop) {
    return (
      <header className="desktop-titlebar border-b border-[var(--color-line)] bg-white/90 backdrop-blur flex-shrink-0 z-20">
        <div className={`relative desktop-drag-region desktop-titlebar-content ${isMac ? "desktop-titlebar-content-mac" : ""}`}>
          {leftContent}
          {centerTitle}
          {rightContent}
        </div>
      </header>
    );
  }

  return (
    <header className="h-12 border-b border-[var(--color-line)] bg-white/80 backdrop-blur flex-shrink-0 z-10">
      <div className="relative h-full px-4 flex items-center justify-between">
        {leftContent}
        {centerTitle}
        {rightContent}
      </div>
    </header>
  );
}
