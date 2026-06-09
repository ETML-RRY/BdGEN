import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import LanguageSwitcher from "./LanguageSwitcher.jsx";
import { saveLanguage } from "./index.js";

// `saveLanguage` touches localStorage / Electron IPC; replace it with a stub
// we can assert against.
vi.mock("./index.js", async (importOriginal) => {
  const mod = await importOriginal();
  return { ...mod, saveLanguage: vi.fn() };
});

describe("LanguageSwitcher", () => {
  beforeEach(() => {
    saveLanguage.mockClear();
  });

  it("renders the three supported languages", () => {
    render(<LanguageSwitcher />);
    const select = screen.getByLabelText(/Language/i);
    expect(select.options).toHaveLength(3);
    expect(select.options[0].value).toBe("en");
    expect(select.options[1].value).toBe("fr");
    expect(select.options[2].value).toBe("de");
  });

  it("calls saveLanguage with the chosen code on change", () => {
    render(<LanguageSwitcher />);
    const select = screen.getByLabelText(/Language/i);
    fireEvent.change(select, { target: { value: "fr" } });
    expect(saveLanguage).toHaveBeenCalledWith("fr");
  });

  it("can switch to German", () => {
    render(<LanguageSwitcher />);
    const select = screen.getByLabelText(/Language/i);
    fireEvent.change(select, { target: { value: "de" } });
    expect(saveLanguage).toHaveBeenCalledWith("de");
  });
});
