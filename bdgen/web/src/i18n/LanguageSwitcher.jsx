import { useTranslation } from "react-i18next";
import { saveLanguage } from "./index.js";

const LANGS = [
  { code: "en", label: "English", flag: "EN" },
  { code: "fr", label: "Français", flag: "FR" },
  { code: "de", label: "Deutsch", flag: "DE" },
];

export default function LanguageSwitcher({ className = "" }) {
  const { i18n } = useTranslation();
  const current = LANGS.find((l) => l.code === (i18n.language || "").split("-")[0]) || LANGS[0];

  return (
    <div className={`flex items-center ${className}`}>
      <label className="sr-only" htmlFor="bdgen-lang">
        Language
      </label>
      <select
        id="bdgen-lang"
        className="bg-transparent border border-[var(--color-line)] rounded px-1.5 py-0.5 text-xs text-[var(--color-ink)] hover:border-[var(--color-primary-500)] focus:outline-none focus:ring-1 focus:ring-[var(--color-primary-500)] cursor-pointer"
        value={current.code}
        onChange={(e) => saveLanguage(e.target.value)}
        title="Language / Langue"
      >
        {LANGS.map((l) => (
          <option key={l.code} value={l.code}>
            {l.flag} — {l.label}
          </option>
        ))}
      </select>
    </div>
  );
}
