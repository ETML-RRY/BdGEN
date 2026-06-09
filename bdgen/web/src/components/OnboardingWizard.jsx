import { useMemo, useState } from "react";
import { FaArrowRight, FaCheck, FaCoins, FaKey, FaLock, FaWandMagicSparkles, FaXmark } from "react-icons/fa6";
import { useTranslation } from "react-i18next";
import { SHOW_UPSCALE } from "../featureFlags.js";

export const INITIAL_ONBOARDING_KEY = "bdgen.initialOnboarding.dismissed";
export const APP_ONBOARDING_KEY = "bdgen.appOnboarding.dismissed";

export function hasDismissedOnboarding(key) {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(key) === "true";
}

export async function hasDismissedOnboardingPreference(key) {
  if (typeof window === "undefined") return true;
  if (hasDismissedOnboarding(key)) return true;
  if (!window.bdgenDesktop?.getPreference) return false;
  return (await window.bdgenDesktop.getPreference(key)) === true;
}

export function dismissOnboarding(key) {
  if (typeof window === "undefined") return Promise.resolve();
  window.localStorage.setItem(key, "true");
  return (window.bdgenDesktop?.setPreference?.(key, true) ?? Promise.resolve()).catch(() => {});
}

// Step definitions are translated at render time (the `kind` namespace +
// index) and rely on `useTranslation` so the user can flip languages without
// restarting the wizard.
function useOnboardingSteps(kind) {
  const { t } = useTranslation();
  return useMemo(() => {
    if (kind === "initial") {
      return [
        {
          icon: FaLock,
          title: t("onboarding.initial.step1Title"),
          body: t("onboarding.initial.step1Body"),
        },
        {
          icon: FaKey,
          title: t("onboarding.initial.step2Title"),
          body: t("onboarding.initial.step2Body"),
        },
        {
          icon: FaCoins,
          title: t("onboarding.initial.step3Title"),
          body: t(
            SHOW_UPSCALE
              ? "onboarding.initial.step3BodyWithUpscale"
              : "onboarding.initial.step3Body"
          ),
        },
      ];
    }
    return [
      {
        icon: FaWandMagicSparkles,
        title: t("onboarding.app.step1Title"),
        body: t("onboarding.app.step1Body"),
      },
      {
        icon: FaCheck,
        title: t("onboarding.app.step2Title"),
        body: t("onboarding.app.step2Body"),
      },
      {
        icon: FaKey,
        title: t("onboarding.app.step3Title"),
        body: t("onboarding.app.step3Body"),
      },
      {
        icon: FaCoins,
        title: t("onboarding.app.step4Title"),
        body: t(SHOW_UPSCALE ? "onboarding.app.step4Body" : "onboarding.app.step4BodyNoUpscale"),
      },
    ];
  }, [kind, t]);
}

export default function OnboardingWizard({ kind = "initial", onDone, onSkip, embedded = false }) {
  const { t } = useTranslation();
  const steps = useOnboardingSteps(kind);
  const [index, setIndex] = useState(0);
  const [dontShowAgain, setDontShowAgain] = useState(false);
  const current = steps[index];
  const Icon = current.icon;
  const isLast = index === steps.length - 1;

  const copy = useMemo(
    () =>
      kind === "initial"
        ? {
            eyebrow: t("onboarding.initial.eyebrow"),
            title: t("onboarding.initial.title"),
            intro: t("onboarding.initial.intro"),
            done: t("onboarding.initial.done"),
          }
        : {
            eyebrow: t("onboarding.app.eyebrow"),
            title: t("onboarding.app.title"),
            intro: t("onboarding.app.intro"),
            done: t("onboarding.app.done"),
          },
    [kind, t],
  );

  function finish() {
    onDone?.(dontShowAgain);
  }

  function skip() {
    onSkip?.(dontShowAgain);
  }

  const panel = (
    <section className="card w-full max-w-3xl overflow-hidden">
      <div className="grid md:grid-cols-[0.9fr_1.1fr]">
        <div className="bg-[var(--color-paper-soft)] p-6 flex flex-col justify-between gap-6">
          <div>
            <p className="text-xs font-semibold uppercase text-[var(--color-primary-700)]">{copy.eyebrow}</p>
            <h1 className="mt-2 text-2xl font-semibold">{copy.title}</h1>
            <p className="mt-3 text-sm text-[var(--color-ink-soft)]">{copy.intro}</p>
          </div>
          <ol className="flex md:flex-col gap-2" aria-label={t("onboarding.initial.progressAria")}>
            {steps.map((step, stepIndex) => (
              <li key={step.title} className="flex-1">
                <button
                  type="button"
                  className={`w-full h-2 md:h-auto md:px-3 md:py-2 rounded-full md:rounded-md text-left transition ${
                    stepIndex === index
                      ? "bg-[var(--color-primary-500)] text-white"
                      : "bg-white/70 text-[var(--color-ink-soft)]"
                  }`}
                  aria-label={step.title}
                  onClick={() => setIndex(stepIndex)}
                >
                  <span className="hidden md:block text-sm font-medium">{step.title}</span>
                </button>
              </li>
            ))}
          </ol>
        </div>

        <div className="p-6">
          <div className="flex justify-end min-h-8">
            {onSkip && (
              <button
                type="button"
                className="p-2 rounded-md text-[var(--color-mute)] hover:bg-[var(--color-paper-soft)] hover:text-[var(--color-ink)]"
                title={t("onboarding.skip")}
                aria-label={t("onboarding.skip")}
                onClick={skip}
              >
                <FaXmark aria-hidden />
              </button>
            )}
          </div>
          <div className="min-h-52 flex flex-col justify-center">
            <div className="w-12 h-12 rounded-lg bg-[var(--color-primary-100)] text-[var(--color-primary-700)] flex items-center justify-center mb-5">
              <Icon aria-hidden className="text-xl" />
            </div>
            <h2 className="text-xl font-semibold">{current.title}</h2>
            <p className="mt-3 text-[var(--color-ink-soft)] leading-relaxed">{current.body}</p>
          </div>
          <div className="mt-6 flex justify-between gap-3">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={index === 0}
              onClick={() => setIndex((prev) => Math.max(0, prev - 1))}
            >
              {t("onboarding.back")}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => (isLast ? finish() : setIndex((prev) => prev + 1))}
            >
              {isLast ? copy.done : t("onboarding.next")}
              {!isLast && <FaArrowRight aria-hidden />}
            </button>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm text-[var(--color-ink-soft)]">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-[var(--color-line)] text-[var(--color-primary-600)] focus:ring-[var(--color-primary-200)]"
              checked={dontShowAgain}
              onChange={(event) => setDontShowAgain(event.target.checked)}
            />
            <span className="min-w-0">{t("onboarding.neverShowAgain")}</span>
          </label>
        </div>
      </div>
    </section>
  );

  if (embedded) {
    return panel;
  }

  return <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/35 p-4">{panel}</div>;
}
