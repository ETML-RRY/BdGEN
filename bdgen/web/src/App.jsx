import { Routes, Route, Link, NavLink } from "react-router-dom";
import { useEffect, useState } from "react";
import { FiMinus, FiSquare, FiX } from "react-icons/fi";
import { api } from "./api.js";
import Home from "./pages/Home.jsx";
import Wizard from "./pages/Wizard.jsx";
import NewProject from "./pages/NewProject.jsx";
import ProjectStats from "./pages/ProjectStats.jsx";
import SecretsPage from "./pages/SecretsPage.jsx";
import OnboardingWizard, {
  APP_ONBOARDING_KEY,
  INITIAL_ONBOARDING_KEY,
  dismissOnboarding,
  hasDismissedOnboarding,
} from "./components/OnboardingWizard.jsx";

export default function App() {
  const [secretsStatus, setSecretsStatus] = useState(null);
  const [showInitialOnboarding, setShowInitialOnboarding] = useState(
    () => !hasDismissedOnboarding(INITIAL_ONBOARDING_KEY),
  );
  const [showAppOnboarding, setShowAppOnboarding] = useState(() => !hasDismissedOnboarding(APP_ONBOARDING_KEY));
  const isDesktop = Boolean(window.bdgenDesktop);

  useEffect(() => {
    api
      .secretsStatus()
      .then(setSecretsStatus)
      .catch(() => setSecretsStatus({ error: true }));
  }, []);

  const providers = secretsStatus?.providers || {};
  const hasConfiguredProvider = Object.values(providers).some((p) => p.configured);
  const needsInitialSetup = secretsStatus && !secretsStatus.vault_exists && !hasConfiguredProvider;
  const shouldGate =
    secretsStatus &&
    !secretsStatus.error &&
    ((secretsStatus.vault_exists && !secretsStatus.unlocked) || needsInitialSetup);

  function dismissInitialOnboarding(remember = false) {
    if (remember) {
      dismissOnboarding(INITIAL_ONBOARDING_KEY);
    }
    setShowInitialOnboarding(false);
  }

  function dismissAppOnboarding(remember = false) {
    if (remember) {
      dismissOnboarding(APP_ONBOARDING_KEY);
    }
    setShowAppOnboarding(false);
  }

  if (!secretsStatus) {
    return (
      <div className="min-h-full flex items-center justify-center text-sm text-[var(--color-mute)]">Chargement...</div>
    );
  }

  if (shouldGate) {
    return (
      <div className="h-full flex flex-col overflow-hidden">
        {isDesktop && <DesktopTitleBar hideNav />}
        <main className="flex-1 min-h-0">
          {needsInitialSetup && showInitialOnboarding ? (
            <div className="h-full min-h-0 flex items-center justify-center overflow-auto p-6">
              <OnboardingWizard
                kind="initial"
                embedded
                onDone={dismissInitialOnboarding}
                onSkip={dismissInitialOnboarding}
              />
            </div>
          ) : (
            <SecretsPage mode="gate" onReady={setSecretsStatus} />
          )}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-full flex flex-col">
      {isDesktop ? <DesktopTitleBar /> : <WebHeader />}

      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/new" element={<NewProject />} />
          <Route path="/settings/secrets" element={<SecretsPage onReady={setSecretsStatus} />} />
          <Route path="/projects/:name/stats" element={<ProjectStats />} />
          <Route path="/projects/:name/*" element={<Wizard />} />
        </Routes>
      </main>

      {showAppOnboarding && <OnboardingWizard kind="app" onDone={dismissAppOnboarding} onSkip={dismissAppOnboarding} />}

      <footer className="border-t border-[var(--color-line)] py-4 text-center text-xs text-[var(--color-mute)]">
        BdGEN · usage local
      </footer>
    </div>
  );
}

function WebHeader() {
  return (
    <header className="border-b border-[var(--color-line)] bg-white/80 backdrop-blur sticky top-0 z-10">
      <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between">
        <BrandLink />
        <AppNav />
      </div>
    </header>
  );
}

function DesktopTitleBar({ hideNav = false }) {
  const [maximized, setMaximized] = useState(false);
  const isMac = window.bdgenDesktop?.platform === "darwin";

  useEffect(() => {
    window.bdgenDesktop.isMaximized().then(setMaximized);
    return window.bdgenDesktop.onMaximizedChange(setMaximized);
  }, []);

  return (
    <header className="desktop-titlebar sticky top-0 z-20 border-b border-[var(--color-line)] bg-white/90 backdrop-blur">
      <div className={`desktop-drag-region desktop-titlebar-content ${isMac ? "desktop-titlebar-content-mac" : ""}`}>
        <BrandLink compact />
        <div className="desktop-no-drag flex h-full items-center gap-4">
          {!hideNav && <AppNav compact />}
          {!isMac && (
            <div className="flex h-full">
              <button
                type="button"
                className="window-control"
                title="Minimiser"
                onClick={() => window.bdgenDesktop.minimize()}
              >
                <FiMinus aria-hidden="true" />
              </button>
              <button
                type="button"
                className="window-control"
                title={maximized ? "Restaurer" : "Agrandir"}
                onClick={() => window.bdgenDesktop.toggleMaximize().then(setMaximized)}
              >
                <FiSquare aria-hidden="true" />
              </button>
              <button
                type="button"
                className="window-control window-control-close"
                title="Fermer"
                onClick={() => window.bdgenDesktop.close()}
              >
                <FiX aria-hidden="true" />
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

function BrandLink({ compact = false }) {
  return (
    <Link to="/" className="desktop-no-drag flex items-center gap-2 font-semibold text-lg">
      <img
        src="/bd_gen_logo.svg"
        alt="Logo BdGEN"
        className={compact ? "w-8 h-8 object-contain" : "w-10 h-10 object-contain"}
      />
      <span>BdGEN</span>
      {!compact && <span className="text-sm font-normal text-[var(--color-mute)]">générateur de bandes dessinées</span>}
    </Link>
  );
}

function AppNav({ compact = false }) {
  const linkClass = compact
    ? "px-2.5 py-1.5 rounded-md hover:bg-[var(--color-paper-soft)] hover:text-[var(--color-ink)]"
    : "px-3 py-1.5 hover:text-[var(--color-ink)]";

  return (
    <nav className="text-sm text-[var(--color-ink-soft)]">
      <NavLink to="/" end className={linkClass}>
        Accueil
      </NavLink>
      <NavLink to="/settings/secrets" className={linkClass}>
        Cles API
      </NavLink>
    </nav>
  );
}
