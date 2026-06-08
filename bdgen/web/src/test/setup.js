import "@testing-library/jest-dom/vitest";
import { afterEach, beforeAll } from "vitest";
import { cleanup } from "@testing-library/react";
import i18n from "../i18n/index.js";
import en from "../i18n/locales/en.json";
import fr from "../i18n/locales/fr.json";
import { initReactI18next } from "react-i18next";

// `globals` is disabled in vitest.config, so Testing Library's automatic
// afterEach cleanup never registers itself. Wire it up explicitly so each test
// starts from an empty DOM instead of leaking mounted components into the next.
afterEach(cleanup);

// i18n is initialized lazily on the first `loadInitialLanguage()` call. The
// Vitest environment has no `navigator.language`, so it would fall back to
// the default ("en") — which is exactly what we want for tests. We still
// need to make sure the resources are loaded AND `initReactI18next` is bound
// so that `useTranslation` resolves keys (otherwise it returns the raw key
// string and tests like shell.test.jsx end up looking for "Preparation"
// while the DOM contains "steps.preparation").
beforeAll(async () => {
  if (!i18n.isInitialized) {
    await i18n.use(initReactI18next).init({
      resources: {
        en: { translation: en },
        fr: { translation: fr },
      },
      lng: "en",
      fallbackLng: "en",
      supportedLngs: ["en", "fr"],
      debug: false,
      interpolation: { escapeValue: false },
      returnNull: false,
      react: { useSuspense: false },
    });
  }
});
