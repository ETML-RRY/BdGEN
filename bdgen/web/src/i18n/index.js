// i18n singleton + language persistence.
//
// Persistence mirrors `bdgen/web/src/components/OnboardingWizard.jsx`
// (hasDismissedOnboarding / dismissOnboarding):
//   1. window.localStorage[STORAGE_KEY]
//   2. window.bdgenDesktop.getPreference(PREF_KEY)  (Electron IPC bridge)
//   3. navigator.language (en if base lang not in SUPPORTED)
//   4. DEFAULT_LNG

import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./locales/en.json";
import fr from "./locales/fr.json";
import de from "./locales/de.json";

export const STORAGE_KEY = "bdgen.language";
export const PREF_KEY = "bdgen.language";
export const SUPPORTED = ["en", "fr", "de"];
export const DEFAULT_LNG = "en";

function pickFromNavigator() {
  const nav = (typeof navigator !== "undefined" && navigator.language) || "";
  const base = (nav || "").toLowerCase().split("-")[0];
  return SUPPORTED.includes(base) ? base : DEFAULT_LNG;
}

async function readPersistedLanguage() {
  if (typeof window === "undefined") return DEFAULT_LNG;
  try {
    const fromLs = window.localStorage.getItem(STORAGE_KEY);
    if (fromLs && SUPPORTED.includes(fromLs)) return fromLs;
    if (window.bdgenDesktop?.getPreference) {
      const fromPref = await window.bdgenDesktop.getPreference(PREF_KEY);
      if (typeof fromPref === "string" && SUPPORTED.includes(fromPref)) return fromPref;
    }
  } catch {
    // ignore — fall through to navigator / default
  }
  return pickFromNavigator();
}

export async function loadInitialLanguage() {
  const lng = await readPersistedLanguage();
  if (!i18n.isInitialized) {
    await i18n.use(initReactI18next).init({
      resources: { en: { translation: en }, fr: { translation: fr }, de: { translation: de } },
      lng,
      fallbackLng: DEFAULT_LNG,
      supportedLngs: SUPPORTED,
      debug: false,
      interpolation: { escapeValue: false },
      returnNull: false,
      react: { useSuspense: false },
    });
  } else if (i18n.language !== lng) {
    await i18n.changeLanguage(lng);
  }
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("lang", lng);
  }
  return lng;
}

export async function saveLanguage(lng) {
  if (!SUPPORTED.includes(lng)) return;
  try {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(STORAGE_KEY, lng);
    }
    if (typeof window !== "undefined" && window.bdgenDesktop?.setPreference) {
      await window.bdgenDesktop.setPreference(PREF_KEY, lng).catch(() => {});
    }
    await i18n.changeLanguage(lng);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("lang", lng);
    }
  } catch {
    // best effort — language change in-memory may still have worked
  }
}

export default i18n;
