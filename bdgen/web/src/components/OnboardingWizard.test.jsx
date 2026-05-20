import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { APP_ONBOARDING_KEY, dismissOnboarding, hasDismissedOnboardingPreference } from "./OnboardingWizard.jsx";

describe("onboarding dismissal preferences", () => {
  beforeEach(() => {
    window.localStorage.clear();
    delete window.bdgenDesktop;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    delete window.bdgenDesktop;
  });

  it("falls back to localStorage in the browser", async () => {
    window.localStorage.setItem(APP_ONBOARDING_KEY, "true");

    await expect(hasDismissedOnboardingPreference(APP_ONBOARDING_KEY)).resolves.toBe(true);
  });

  it("reads persisted Electron preferences when localStorage belongs to a fresh port", async () => {
    window.bdgenDesktop = {
      getPreference: vi.fn().mockResolvedValue(true),
    };

    await expect(hasDismissedOnboardingPreference(APP_ONBOARDING_KEY)).resolves.toBe(true);
    expect(window.bdgenDesktop.getPreference).toHaveBeenCalledWith(APP_ONBOARDING_KEY);
  });

  it("writes both localStorage and Electron preferences when remembered", async () => {
    window.bdgenDesktop = {
      setPreference: vi.fn().mockResolvedValue(true),
    };

    await dismissOnboarding(APP_ONBOARDING_KEY);

    expect(window.localStorage.getItem(APP_ONBOARDING_KEY)).toBe("true");
    expect(window.bdgenDesktop.setPreference).toHaveBeenCalledWith(APP_ONBOARDING_KEY, true);
  });
});
