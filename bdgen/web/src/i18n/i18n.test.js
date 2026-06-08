import { describe, it, expect } from "vitest";
import en from "./locales/en.json";
import fr from "./locales/fr.json";
import de from "./locales/de.json";

// Walk a nested object and yield dot-separated paths so we can assert that
// locales have the same key set. Arrays are treated as leaves (we only
// care about the key shape, not about array items).
function collectKeys(obj, prefix = "") {
  const out = [];
  for (const [k, v] of Object.entries(obj)) {
    const path = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out.push(...collectKeys(v, path));
    } else {
      out.push(path);
    }
  }
  return out;
}

describe("i18n locale parity", () => {
  it("en, fr and de expose the same set of leaf keys", () => {
    const enKeys = new Set(collectKeys(en));
    const frKeys = new Set(collectKeys(fr));
    const deKeys = new Set(collectKeys(de));
    const missingInFr = [...enKeys].filter((k) => !frKeys.has(k));
    const missingInEn = [...frKeys].filter((k) => !enKeys.has(k));
    const missingInDe = [...enKeys].filter((k) => !deKeys.has(k));
    const missingInEnFromDe = [...deKeys].filter((k) => !enKeys.has(k));
    expect(missingInFr).toEqual([]);
    expect(missingInEn).toEqual([]);
    expect(missingInDe).toEqual([]);
    expect(missingInEnFromDe).toEqual([]);
  });

  it("all preset arrays in formPresets have the same length across all languages", () => {
    const presets = en.formPresets;
    for (const [key, list] of Object.entries(presets)) {
      if (!Array.isArray(list)) continue;
      const frList = fr.formPresets[key];
      const deList = de.formPresets[key];
      expect(Array.isArray(frList), `fr.formPresets.${key} is not an array`).toBe(true);
      expect(Array.isArray(deList), `de.formPresets.${key} is not an array`).toBe(true);
      expect(
        frList.length,
        `formPresets.${key} length mismatch (en=${list.length}, fr=${frList.length})`,
      ).toBe(list.length);
      expect(
        deList.length,
        `formPresets.${key} length mismatch (en=${list.length}, de=${deList.length})`,
      ).toBe(list.length);
    }
  });

  it("English is the default language and en/fr/de are supported", async () => {
    const mod = await import("./index.js");
    expect(mod.DEFAULT_LNG).toBe("en");
    expect(mod.SUPPORTED).toContain("en");
    expect(mod.SUPPORTED).toContain("fr");
    expect(mod.SUPPORTED).toContain("de");
  });
});
