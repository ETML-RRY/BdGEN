import { useEffect, useState } from "react";
import { Routes, Route } from "react-router-dom";
import { api } from "./api.js";
import { useAppContext } from "./context/AppContext.jsx";
import AppBar from "./components/AppBar.jsx";
import Ribbon from "./components/shell/Ribbon.jsx";
import Sidebar from "./components/shell/Sidebar.jsx";
import StatusBar from "./components/StatusBar.jsx";
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
  hasDismissedOnboardingPreference,
} from "./components/OnboardingWizard.jsx";

export default function App() {
  const { setRunningJob } = useAppContext();
  const [secretsStatus, setSecretsStatus] = useState(null);
  const [onboardingLoaded, setOnboardingLoaded] = useState(() => !window.bdgenDesktop?.getPreference);
  const [showInitialOnboarding, setShowInitialOnboarding] = useState(
    () => !hasDismissedOnboarding(INITIAL_ONBOARDING_KEY),
  );
  const [showAppOnboarding, setShowAppOnboarding] = useState(() => !hasDismissedOnboarding(APP_ONBOARDING_KEY));

  useEffect(() => {
    api
      .secretsStatus()
      .then(setSecretsStatus)
      .catch(() => setSecretsStatus({ error: true }));
  }, []);

  useEffect(() => {
    if (!window.bdgenDesktop?.getPreference) return;

    let active = true;
    Promise.all([
      hasDismissedOnboardingPreference(INITIAL_ONBOARDING_KEY),
      hasDismissedOnboardingPreference(APP_ONBOARDING_KEY),
    ])
      .then(([initialDismissed, appDismissed]) => {
        if (!active) return;
        if (initialDismissed) setShowInitialOnboarding(false);
        if (appDismissed) setShowAppOnboarding(false);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setOnboardingLoaded(true);
      });

    return () => {
      active = false;
    };
  }, []);

  // Global job polling — keeps StatusBar current across all pages
  useEffect(() => {
    let active = true;
    function poll() {
      api
        .currentJob()
        .then(({ job }) => {
          if (active) setRunningJob(job);
        })
        .catch(() => {});
    }
    poll();
    const t = setInterval(poll, 5000);
    return () => {
      active = false;
      clearInterval(t);
    };
  }, [setRunningJob]);

  const providers = secretsStatus?.providers || {};
  const hasConfiguredProvider = Object.values(providers).some((p) => p.configured);
  const needsInitialSetup = secretsStatus && !secretsStatus.vault_exists && !hasConfiguredProvider;
  const shouldGate =
    secretsStatus &&
    !secretsStatus.error &&
    ((secretsStatus.vault_exists && !secretsStatus.unlocked) || needsInitialSetup);

  function dismissInitialOnboarding(remember = false) {
    if (remember) void dismissOnboarding(INITIAL_ONBOARDING_KEY);
    setShowInitialOnboarding(false);
  }

  function dismissAppOnboarding(remember = false) {
    if (remember) void dismissOnboarding(APP_ONBOARDING_KEY);
    setShowAppOnboarding(false);
  }

  if (!secretsStatus || !onboardingLoaded) {
    return (
      <div className="min-h-full flex items-center justify-center text-sm text-[var(--color-mute)]">
        Chargement...
      </div>
    );
  }

  if (shouldGate) {
    return (
      <div className="h-screen flex flex-col overflow-hidden">
        <AppBar hideNav />
        <main className="flex-1 min-h-0 overflow-y-auto">
          {needsInitialSetup && showInitialOnboarding ? (
            <div className="h-full flex items-center justify-center p-6">
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
        <StatusBar />
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <AppBar />
      <Ribbon />
      <div className="flex-1 min-h-0 flex">
        <Sidebar />
        <main className="flex-1 min-h-0 overflow-y-auto">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/new" element={<NewProject />} />
            <Route path="/settings/secrets" element={<SecretsPage onReady={setSecretsStatus} />} />
            <Route path="/projects/:name/stats" element={<ProjectStats />} />
            <Route path="/projects/:name/*" element={<Wizard />} />
          </Routes>
        </main>
      </div>
      <StatusBar />
      {showAppOnboarding && (
        <OnboardingWizard kind="app" onDone={dismissAppOnboarding} onSkip={dismissAppOnboarding} />
      )}
    </div>
  );
}
