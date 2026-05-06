import { useMemo, useState } from "react";
import {
  FaArrowRight,
  FaCheck,
  FaCoins,
  FaKey,
  FaLock,
  FaWandMagicSparkles,
  FaXmark,
} from "react-icons/fa6";

export const INITIAL_ONBOARDING_KEY = "bdgen.initialOnboarding.dismissed";
export const APP_ONBOARDING_KEY = "bdgen.appOnboarding.dismissed";

const INITIAL_STEPS = [
  {
    icon: FaLock,
    title: "Protéger vos clés API",
    body:
      "Le mot de passe principal sert à chiffrer vos clés sur cet ordinateur. BdGEN ne le stocke pas : il faudra le retenir pour rouvrir le coffre.",
  },
  {
    icon: FaKey,
    title: "Récupérer les clés utiles",
    body:
      "OpenAI est requis pour démarrer. Anthropic, xAI et Replicate sont optionnels selon les modèles que vous souhaitez utiliser.",
  },
  {
    icon: FaCoins,
    title: "Comprendre le budget",
    body:
      "Une BD consomme des appels texte et image. Le coût varie selon les modèles, le nombre de pages, les essais et l’upscale ; prévoyez d’abord un petit projet de test et suivez les statistiques de coût dans BdGEN.",
  },
];

const APP_STEPS = [
  {
    icon: FaWandMagicSparkles,
    title: "1. Préparer le projet",
    body:
      "Décrivez l’histoire, le format, les personnages et le style. Plus la base est claire, plus les étapes suivantes seront cohérentes.",
  },
  {
    icon: FaCheck,
    title: "2. Écrire et relire",
    body:
      "L’étape Écriture transforme votre brief en script structuré. Vous pouvez corriger le résultat avant de lancer les images.",
  },
  {
    icon: FaKey,
    title: "3. Générer les références",
    body:
      "BdGEN crée les fiches visuelles des personnages, lieux et objets. Validez-les ou affinez-les avant les planches finales.",
  },
  {
    icon: FaCoins,
    title: "4. Composer la BD",
    body:
      "Les planches, la couverture et le PDF sont générés à partir du script et des références. L’upscale reste optionnel pour améliorer la définition.",
  },
];

export function hasDismissedOnboarding(key) {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(key) === "true";
}

export function dismissOnboarding(key) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(key, "true");
}

export default function OnboardingWizard({
  kind = "initial",
  onDone,
  onSkip,
  embedded = false,
}) {
  const steps = kind === "initial" ? INITIAL_STEPS : APP_STEPS;
  const [index, setIndex] = useState(0);
  const current = steps[index];
  const Icon = current.icon;
  const isLast = index === steps.length - 1;

  const copy = useMemo(
    () =>
      kind === "initial"
        ? {
            eyebrow: "Premier lancement",
            title: "Avant de créer votre première BD",
            intro:
              "BdGEN utilise vos propres clés API pour générer textes et images. Cette courte introduction pose les bases avant la configuration.",
            done: "Configurer le coffre",
          }
        : {
            eyebrow: "Guide de l’atelier",
            title: "Comment se déroule une création",
            intro:
              "L’outil avance par étapes. Vous pouvez revenir en arrière, relancer une partie et garder la main avant les générations coûteuses.",
            done: "Commencer",
          },
    [kind]
  );

  function finish() {
    onDone?.();
  }

  const panel = (
    <section className="card w-full max-w-3xl overflow-hidden">
      <div className="grid md:grid-cols-[0.9fr_1.1fr]">
        <div className="bg-[var(--color-paper-soft)] p-6 flex flex-col justify-between gap-6">
          <div>
            <p className="text-xs font-semibold uppercase text-[var(--color-primary-700)]">
              {copy.eyebrow}
            </p>
            <h1 className="mt-2 text-2xl font-semibold">{copy.title}</h1>
            <p className="mt-3 text-sm text-[var(--color-ink-soft)]">
              {copy.intro}
            </p>
          </div>
          <ol className="flex md:flex-col gap-2" aria-label="Progression du guide">
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
                  <span className="hidden md:block text-sm font-medium">
                    {step.title}
                  </span>
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
                title="Passer le guide"
                aria-label="Passer le guide"
                onClick={onSkip}
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
            <p className="mt-3 text-[var(--color-ink-soft)] leading-relaxed">
              {current.body}
            </p>
          </div>
          <div className="mt-6 flex justify-between gap-3">
            <button
              type="button"
              className="btn btn-secondary"
              disabled={index === 0}
              onClick={() => setIndex((prev) => Math.max(0, prev - 1))}
            >
              Retour
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => (isLast ? finish() : setIndex((prev) => prev + 1))}
            >
              {isLast ? copy.done : "Suivant"}
              {!isLast && <FaArrowRight aria-hidden />}
            </button>
          </div>
        </div>
      </div>
    </section>
  );

  if (embedded) {
    return panel;
  }

  return (
    <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/35 p-4">
      {panel}
    </div>
  );
}
