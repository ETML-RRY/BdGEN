import { useState, useEffect, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { FaPlus, FaTrash, FaPalette, FaChevronDown } from "react-icons/fa6";
import { api } from "../api.js";
import useRegisterShell from "../hooks/useRegisterShell.js";
import StyleFromImageDialog from "./StyleFromImageDialog.jsx";
import ReferencesBundlePanel from "./ReferencesBundlePanel.jsx";
import { SHOW_UPSCALE } from "../featureFlags.js";
import { presetsFor, isAllowedPresetValue } from "./projectFormPresets.js";
import { formatError } from "../i18n/formatError.js";
import i18n, { DEFAULT_LNG, SUPPORTED } from "../i18n/index.js";

// Default `metadata.language` for a blank project. The new-comic wizard used to
// hardcode "fr" here, which made every freshly created project French — even
// when the UI was running in English or German. We now mirror the same logic
// as the i18n bootstrap (base 2-letter ISO, fall back to the app default when
// the active language is not in SUPPORTED).
function defaultMetadataLanguage() {
  const base = (i18n.language || "").toLowerCase().split(/[-_]/)[0];
  return SUPPORTED.includes(base) ? base : DEFAULT_LNG;
}

// Fill `metadata.language` with the current UI language if the config is
// missing one. The DEFAULT_CONFIG placeholder is "" so that "no language
// chosen" is distinguishable from an explicit choice and can be back-filled.
function withDefaultLanguage(cfg) {
  if (cfg.metadata.language) return cfg;
  return { ...cfg, metadata: { ...cfg.metadata, language: defaultMetadataLanguage() } };
}

// Left sub-navigation: one entry per top-level <Section> of the form. The `id`
// is mirrored onto the section's DOM node so the sidebar can scroll to it and a
// scroll-spy can highlight the section currently in view. Labels are looked up
// at render time so a language switcher re-renders them.
function useFormSections() {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: "sec-identite", label: t("form.sections.identity") },
      { id: "sec-histoire", label: t("form.sections.story") },
      { id: "sec-style", label: t("form.sections.visualStyle") },
      { id: "sec-casting", label: t("form.sections.casting") },
      { id: "sec-structure", label: t("form.sections.structure") },
      { id: "sec-modeles", label: t("form.sections.models") },
    ],
    [t],
  );
}

export const DEFAULT_CONFIG = {
  project: "",
  display_name: "",
  output_root: "./output",
  // language is left empty so withDefaultLanguage() can fill it with the
  // current UI language (see top of file). Previously hardcoded to "fr".
  metadata: { title: "", author: "", language: "" },
  story: {
    synopsis: "",
    genre: "",
    tone: "",
    setting: "",
    target_audience: "",
  },
  style: {
    art_style: "",
    color_palette: "",
    line_work: "",
    mood: "",
    panel_borders: "",
    speech_bubbles: "",
    character_rendering: "",
  },
  characters: [],
  locations: [],
  objects: [],
  structure: {
    page_count: 6,
    panels_per_page_avg: 4,
    panels_per_page_range: [2, 6],
    include_cover: true,
    include_back_cover: true,
    narrative_pacing: "",
    page_format: "portrait",
    allow_extra_characters: true,
    allow_extra_locations: true,
    allow_extra_objects: true,
  },
  allow_style_copy: false,
  generation_options: {
    script_model: {
      provider: "anthropic",
      model: "claude-sonnet-4-6",
      temperature: 0.8,
      effort: "medium",
    },
    image_model: {
      provider: "openai",
      model: "gpt-image-2",
      size: "1024x1536",
      quality: "high",
    },
    references: {
      generate: true,
      image_model: null,
      character_views: ["face_closeup", "full_body_front", "expressions_sheet"],
      location_view: "establishing_shot",
      use_as_input_for_panels: true,
    },
    upscale: {
      enabled: false,
      mode: "target",
      target_megapixels: 4,
      scale_factor: 2,
      output_format: "png",
      output_quality: 90,
    },
    render_dialogs_separately: true,
    output_format: "pdf",
  },
};

// Derive a filesystem-safe project slug from a human label (display name or
// title). Mirrors the backend's slugify so the same idea yields the same id.
// Falls back to "projet" when the source has no usable characters.
export function slugifyProjectName(source) {
  return (
    (source || "projet")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 60) || "projet"
  );
}

const SCRIPT_MODEL_OPTIONS = {
  anthropic: [
    { value: "claude-opus-4-8", label: "Claude Opus 4.8" },
    { value: "claude-opus-4-7", label: "Claude Opus 4.7" },
    { value: "claude-opus-4-6", label: "Claude Opus 4.6" },
    { value: "claude-sonnet-4-6", label: "Claude Sonnet 4.6" },
    { value: "claude-opus-4-5", label: "Claude Opus 4.5" },
    { value: "claude-sonnet-4-5", label: "Claude Sonnet 4.5" },
    { value: "claude-haiku-4-5", label: "Claude Haiku 4.5" },
    { value: "claude-opus-4-1", label: "Claude Opus 4.1" },
  ],
  openai: [
    { value: "gpt-5.4", label: "GPT-5.4" },
    { value: "gpt-5.4-mini", label: "GPT-5.4 mini" },
    { value: "gpt-5.4-nano", label: "GPT-5.4 nano" },
    { value: "gpt-5.3-chat-latest", label: "GPT-5.3 (chat latest)" },
    { value: "gpt-5.2", label: "GPT-5.2" },
    { value: "gpt-5.2-pro", label: "GPT-5.2 pro" },
    { value: "gpt-5.1", label: "GPT-5.1" },
    { value: "gpt-5.1-codex-max", label: "GPT-5.1 Codex Max" },
    { value: "gpt-5-mini", label: "GPT-5 mini" },
    { value: "gpt-5-nano", label: "GPT-5 nano" },
    { value: "gpt-4.1", label: "GPT-4.1" },
  ],
  xai: [
    { value: "grok-4.3", label: "Grok 4.3" },
    { value: "grok-4.20-reasoning", label: "Grok 4.20 reasoning" },
    { value: "grok-4-fast-reasoning", label: "Grok 4 Fast reasoning" },
    { value: "grok-4-fast-non-reasoning", label: "Grok 4 Fast non-reasoning" },
    { value: "grok-3", label: "Grok 3" },
    { value: "grok-3-mini", label: "Grok 3 mini" },
  ],
};

const IMAGE_MODEL_OPTIONS = {
  openai: [
    { value: "gpt-image-2", label: "GPT Image 2" },
    { value: "gpt-image-1", label: "GPT Image 1" },
    { value: "gpt-image-1-mini", label: "GPT Image 1 mini" },
    { value: "chatgpt-image-latest", label: "ChatGPT image latest" },
  ],
  xai: [
    { value: "grok-imagine-image-quality", label: "Grok Imagine quality" },
    { value: "grok-imagine-image", label: "Grok Imagine" },
  ],
};

// Tarifs indicatifs en USD par million de tokens (mode standard, le moins
// cher). DOIT rester synchronisé avec bdgen/bdgen/stats.py::_rates.
function modelRates(provider, model) {
  const p = (provider || "").toLowerCase();
  const m = (model || "").toLowerCase();
  if (p === "openai") {
    if (m.includes("gpt-image-2")) return { input: 5, image_output: 30 };
    if (m.includes("gpt-image-1")) return { input: 5, output: 0 };
    if (m.includes("gpt-5.5")) return { input: 5, output: 30 };
    if (m.includes("gpt-5.4-mini")) return { input: 0.75, output: 4.5 };
    if (m.includes("gpt-5.4")) return { input: 2.5, output: 15 };
    if (m.includes("gpt-5")) return { input: 1.25, output: 10 };
    if (m.includes("gpt-4o-mini")) return { input: 0.15, output: 0.6 };
    if (m.includes("gpt-4o")) return { input: 2.5, output: 10 };
    return null;
  }
  if (p === "anthropic") {
    if (m.includes("opus")) {
      if (["opus-4-5", "opus-4-6", "opus-4-7", "opus-4-8", "opus-4-9"].some((v) => m.includes(v)))
        return { input: 5, output: 25 };
      return { input: 15, output: 75 };
    }
    if (m.includes("sonnet")) return { input: 3, output: 15 };
    if (m.includes("haiku-3-5") || m.includes("haiku-3.5")) return { input: 0.8, output: 4 };
    if (m.includes("haiku")) return { input: 0.25, output: 1.25 };
    return null;
  }
  return null;
}

function formatModelPrice(provider, model, t) {
  const r = modelRates(provider, model);
  if (!r) return null;
  const out = r.image_output ?? r.output;
  const outLabel = r.image_output ? t("form.priceSuffix.imageOutput") : t("form.priceSuffix.output");
  return t("form.priceLine", { input: r.input, output: out, outputLabel: outLabel });
}

// True for Opus variants that offer a premium "fast" tier at double the rate.
function hasFastTier(provider, model) {
  const m = (model || "").toLowerCase();
  return (
    (provider || "").toLowerCase() === "anthropic" &&
    ["opus-4-5", "opus-4-6", "opus-4-7", "opus-4-8", "opus-4-9"].some((v) => m.includes(v))
  );
}

const QUALITY_VALUES = ["low", "medium", "high"];
const SCRIPT_EFFORT_VALUES = ["low", "medium", "high", "max"];

function useQualityOptions() {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { value: "low", label: t("form.quality.economy") },
      { value: "medium", label: t("form.quality.standard") },
      { value: "high", label: t("form.quality.high") },
    ],
    [t],
  );
}

function useScriptEffortOptions() {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { value: "low", label: t("form.effort.fast") },
      { value: "medium", label: t("form.effort.balanced") },
      { value: "high", label: t("form.effort.thorough") },
      { value: "max", label: t("form.effort.maximum") },
    ],
    [t],
  );
}

function supportsScriptEffort(provider, model) {
  return (
    provider === "anthropic" &&
    (model.startsWith("claude-mythos-preview") ||
      model.startsWith("claude-opus-4-6") ||
      model.startsWith("claude-opus-4-7") ||
      model.startsWith("claude-opus-4-8") ||
      model.startsWith("claude-sonnet-4-6"))
  );
}

function normaliseScriptEffort(modelConfig) {
  if (supportsScriptEffort(modelConfig.provider, modelConfig.model)) {
    if (!SCRIPT_EFFORT_VALUES.includes(modelConfig.effort)) {
      modelConfig.effort = DEFAULT_CONFIG.generation_options.script_model.effort;
    }
    return;
  }
  delete modelConfig.effort;
}

function blankCharacter(i) {
  return {
    id: `perso_${i}`,
    name: "",
    role: "",
    physical_description: "",
    outfit: "",
    personality: "",
  };
}

function blankLocation(i) {
  return {
    id: `decor_${i}`,
    name: "",
    description: "",
  };
}

function blankObject(i) {
  return {
    id: `objet_${i}`,
    name: "",
    description: "",
  };
}

function dedupeId(base, used) {
  let id = base;
  let suffix = 2;
  while (used.has(id)) id = `${base}_${suffix++}`;
  used.add(id);
  return id;
}

function normalize(cfg) {
  // Tolerate configs saved before locations / objects / allow_extra_* /
  // display_name existed.
  const out = structuredClone(cfg);
  if (!out.generation_options) {
    out.generation_options = structuredClone(DEFAULT_CONFIG.generation_options);
  }
  if (!out.generation_options.script_model) {
    out.generation_options.script_model = structuredClone(DEFAULT_CONFIG.generation_options.script_model);
  }
  normaliseScriptEffort(out.generation_options.script_model);
  if (!out.generation_options.image_model) {
    out.generation_options.image_model = structuredClone(DEFAULT_CONFIG.generation_options.image_model);
  }
  if (out.generation_options.image_model.provider !== "openai") {
    out.generation_options.image_model.provider = "openai";
    out.generation_options.image_model.model = DEFAULT_CONFIG.generation_options.image_model.model;
  }
  if (!out.generation_options.references) {
    out.generation_options.references = structuredClone(DEFAULT_CONFIG.generation_options.references);
  }
  if (
    out.generation_options.references.image_model &&
    !["openai", "xai"].includes(out.generation_options.references.image_model.provider)
  ) {
    out.generation_options.references.image_model = structuredClone(DEFAULT_CONFIG.generation_options.image_model);
  }
  if (!out.generation_options.upscale) {
    out.generation_options.upscale = structuredClone(DEFAULT_CONFIG.generation_options.upscale);
  }
  if (!Array.isArray(out.locations)) out.locations = [];
  if (!Array.isArray(out.objects)) out.objects = [];
  if (!out.structure) out.structure = {};
  if (!["portrait", "landscape", "square", "strip"].includes(out.structure.page_format)) {
    out.structure.page_format = "portrait";
  }
  if (typeof out.structure.allow_extra_characters !== "boolean") {
    out.structure.allow_extra_characters = true;
  }
  if (typeof out.structure.allow_extra_locations !== "boolean") {
    out.structure.allow_extra_locations = true;
  }
  if (typeof out.structure.allow_extra_objects !== "boolean") {
    out.structure.allow_extra_objects = true;
  }
  if (typeof out.display_name !== "string") out.display_name = "";
  if (typeof out.allow_style_copy !== "boolean") out.allow_style_copy = false;
  if (typeof out.generation_options.upscale.enabled !== "boolean") {
    out.generation_options.upscale.enabled = false;
  }
  if (!["target", "factor"].includes(out.generation_options.upscale.mode)) {
    out.generation_options.upscale.mode = "target";
  }
  if (typeof out.generation_options.upscale.target_megapixels !== "number") {
    out.generation_options.upscale.target_megapixels = 4;
  }
  if (typeof out.generation_options.upscale.scale_factor !== "number") {
    out.generation_options.upscale.scale_factor = 2;
  }
  if (!["png", "jpg", "webp"].includes(out.generation_options.upscale.output_format)) {
    out.generation_options.upscale.output_format = "png";
  }
  if (typeof out.generation_options.upscale.output_quality !== "number") {
    out.generation_options.upscale.output_quality = 90;
  }
  return out;
}

export default function ProjectForm({
  initial,
  isNew = false,
  projectName = null,
  initialCharacterPhotos = null,
  initialLocationPhotos = null,
  initialObjectPhotos = null,
  initialReferenceImages = null,
  onSubmit,
  onCancel,
  onReferencesImported = null,
  submitLabel,
  onApplyStyleOnly = null,
  applyStyleOnlyLabel,
}) {
  const { t, i18n } = useTranslation();
  const FORM_SECTIONS = useFormSections();
  const QUALITY_OPTIONS = useQualityOptions();
  const SCRIPT_EFFORT_OPTIONS = useScriptEffortOptions();
  const [config, setConfig] = useState(() => withDefaultLanguage(normalize(initial || DEFAULT_CONFIG)));
  const [submitting, setSubmitting] = useState(false);
  const [applyingStyleOnly, setApplyingStyleOnly] = useState(false);
  const [error, setError] = useState(null);
  const [styleFromImageOpen, setStyleFromImageOpen] = useState(false);
  const [styleRefFile, setStyleRefFile] = useState(null);
  const [styleRefUrl, setStyleRefUrl] = useState(null);
  const [styleRefLocalPreview, setStyleRefLocalPreview] = useState(null);
  // Per-entity photo state, keyed by entity id.
  // Each entry is an array: [{ slot, url, file, uploading, error }, ...]
  // slot: server-assigned slot number (null for locally-picked photos not yet uploaded)
  const [characterPhotos, setCharacterPhotos] = useState(() => {
    const out = {};
    for (const [id, photoList] of Object.entries(initialCharacterPhotos || {})) {
      if (Array.isArray(photoList) && photoList.length > 0) {
        out[id] = photoList.map(({ slot, url }) => ({ slot, url, file: null, uploading: false, error: null }));
      }
    }
    return out;
  });
  const [locationPhotos, setLocationPhotos] = useState(() => {
    const out = {};
    for (const [id, photoList] of Object.entries(initialLocationPhotos || {})) {
      if (Array.isArray(photoList) && photoList.length > 0) {
        out[id] = photoList.map(({ slot, url }) => ({ slot, url, file: null, uploading: false, error: null }));
      }
    }
    return out;
  });
  const [objectPhotos, setObjectPhotos] = useState(() => {
    const out = {};
    for (const [id, photoList] of Object.entries(initialObjectPhotos || {})) {
      if (Array.isArray(photoList) && photoList.length > 0) {
        out[id] = photoList.map(({ slot, url }) => ({ slot, url, file: null, uploading: false, error: null }));
      }
    }
    return out;
  });

  useEffect(() => {
    if (initial) setConfig(withDefaultLanguage(normalize(initial)));
  }, [initial]);

  // ── Left sub-navigation (Préparation only) ────────────────────────────
  // Jump-to-section list published into the desktop shell sidebar, with a
  // scroll-spy that highlights whichever section is currently in view. Scoped
  // to the in-project form (`!isNew`); the standalone "New project" page keeps
  // its own layout.
  const [activeSection, setActiveSection] = useState(FORM_SECTIONS[0].id);

  useEffect(() => {
    if (isNew) return;
    const els = FORM_SECTIONS.map((s) => document.getElementById(s.id)).filter(Boolean);
    if (!els.length) return;
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting);
        if (!visible.length) return;
        visible.sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        setActiveSection(visible[0].target.id);
      },
      { rootMargin: "-15% 0px -75% 0px", threshold: 0 },
    );
    els.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [isNew]);

  function scrollToSection(id) {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    setActiveSection(id);
  }

  useRegisterShell(
    {
      sidebar: isNew
        ? null
        : {
            sections: [{ id: "form", label: t("form.sections.preparation"), items: FORM_SECTIONS }],
            activeItem: activeSection,
            onSelect: scrollToSection,
          },
    },
    [isNew, activeSection],
  );

  useEffect(() => {
    if (!projectName) return;
    api
      .getStyleReferenceInfo(projectName)
      .then((info) => {
        if (info?.url) setStyleRefUrl(info.url);
      })
      .catch(() => {});
  }, [projectName]);

  useEffect(() => {
    if (!initialCharacterPhotos) return;
    setCharacterPhotos((prev) => {
      const next = { ...prev };
      for (const [id, photoList] of Object.entries(initialCharacterPhotos)) {
        if (!Array.isArray(photoList) || photoList.length === 0) continue;
        const hasPending = (next[id] || []).some((e) => e.file);
        if (!hasPending) {
          next[id] = photoList.map(({ slot, url }) => ({ slot, url, file: null, uploading: false, error: null }));
        }
      }
      return next;
    });
  }, [initialCharacterPhotos]);

  useEffect(() => {
    if (!initialObjectPhotos) return;
    setObjectPhotos((prev) => {
      const next = { ...prev };
      for (const [id, photoList] of Object.entries(initialObjectPhotos)) {
        if (!Array.isArray(photoList) || photoList.length === 0) continue;
        const hasPending = (next[id] || []).some((e) => e.file);
        if (!hasPending) {
          next[id] = photoList.map(({ slot, url }) => ({ slot, url, file: null, uploading: false, error: null }));
        }
      }
      return next;
    });
  }, [initialObjectPhotos]);

  useEffect(() => {
    if (!initialLocationPhotos) return;
    setLocationPhotos((prev) => {
      const next = { ...prev };
      for (const [id, photoList] of Object.entries(initialLocationPhotos)) {
        if (!Array.isArray(photoList) || photoList.length === 0) continue;
        const hasPending = (next[id] || []).some((e) => e.file);
        if (!hasPending) {
          next[id] = photoList.map(({ slot, url }) => ({ slot, url, file: null, uploading: false, error: null }));
        }
      }
      return next;
    });
  }, [initialLocationPhotos]);

  function set(path, value) {
    setConfig((c) => {
      const next = structuredClone(c);
      const keys = path.split(".");
      let cur = next;
      for (let i = 0; i < keys.length - 1; i++) cur = cur[keys[i]];
      cur[keys[keys.length - 1]] = value;
      return next;
    });
  }

  function setModelProvider(kind, provider, optionsByProvider) {
    setConfig((c) => {
      const next = structuredClone(c);
      const modelConfig = next.generation_options[kind];
      modelConfig.provider = provider;
      modelConfig.model = optionsByProvider[provider]?.[0]?.value || "";
      if (kind === "script_model") normaliseScriptEffort(modelConfig);
      return next;
    });
  }

  function setScriptModel(model) {
    setConfig((c) => {
      const next = structuredClone(c);
      const modelConfig = next.generation_options.script_model;
      modelConfig.model = model;
      normaliseScriptEffort(modelConfig);
      return next;
    });
  }

  function setReferenceModelProvider(provider) {
    setConfig((c) => {
      const next = structuredClone(c);
      const modelConfig = next.generation_options.references.image_model;
      modelConfig.provider = provider;
      modelConfig.model = IMAGE_MODEL_OPTIONS[provider]?.[0]?.value || "";
      return next;
    });
  }

  function setReferenceImageModelEnabled(enabled) {
    setConfig((c) => {
      const next = structuredClone(c);
      next.generation_options.references.image_model = enabled
        ? structuredClone(next.generation_options.references.image_model || next.generation_options.image_model)
        : null;
      return next;
    });
  }

  function addCharacter() {
    setConfig((c) => ({
      ...c,
      characters: [...c.characters, blankCharacter(c.characters.length + 1)],
    }));
  }
  function updateCharacter(i, field, value) {
    setConfig((c) => {
      const next = structuredClone(c);
      const oldId = next.characters[i].id;
      next.characters[i][field] = value;
      if (field === "id" && oldId !== value && oldId) {
        setCharacterPhotos((prev) => {
          if (!prev[oldId]) return prev;
          const out = { ...prev };
          out[value] = prev[oldId];
          delete out[oldId];
          return out;
        });
        // Note: server-side slot paths still reference oldId until the next save
      }
      return next;
    });
  }
  function removeCharacter(i) {
    setConfig((c) => {
      const next = structuredClone(c);
      const removed = next.characters.splice(i, 1)[0];
      if (removed?.id) {
        setCharacterPhotos((prev) => {
          if (!prev[removed.id]) return prev;
          const out = { ...prev };
          delete out[removed.id];
          return out;
        });
        if (projectName) {
          api.deleteCharacterPhoto(projectName, removed.id).catch(() => {});
        }
      }
      return next;
    });
  }

  async function onAddCharacterPhoto(i, file) {
    if (!file) return;
    const charId = config.characters[i]?.id;
    if (!charId) return;
    const localUrl = URL.createObjectURL(file);

    setCharacterPhotos((prev) => ({
      ...prev,
      [charId]: [...(prev[charId] || []), { slot: null, url: localUrl, file, uploading: false, error: null }],
    }));

    // Extract character info — only fills fields that are still empty
    try {
      const extracted = await api.characterFromPhoto(file, config.metadata.language || defaultMetadataLanguage());
      setConfig((c) => {
        const next = structuredClone(c);
        const row = next.characters[i];
        if (!row) return c;
        if (!row.name && extracted.name) row.name = extracted.name;
        if (!row.physical_description && extracted.physical_description)
          row.physical_description = extracted.physical_description;
        if (!row.outfit && extracted.outfit) row.outfit = extracted.outfit;
        if (!row.personality && extracted.personality) row.personality = extracted.personality;
        return next;
      });
    } catch {
      // extraction failure is non-fatal
    }

    if (projectName) {
      setCharacterPhotos((prev) => ({
        ...prev,
        [charId]: (prev[charId] || []).map((e) => (e.file === file ? { ...e, uploading: true } : e)),
      }));
      try {
        const { slot, url } = await api.addCharacterPhoto(projectName, charId, file);
        setCharacterPhotos((prev) => ({
          ...prev,
          [charId]: (prev[charId] || []).map((e) =>
            e.file === file ? { slot, url: url || localUrl, file: null, uploading: false, error: null } : e,
          ),
        }));
      } catch (uploadErr) {
        setCharacterPhotos((prev) => ({
          ...prev,
          [charId]: (prev[charId] || []).map((e) =>
            e.file === file ? { ...e, uploading: false, error: uploadErr.message || t("form.uploadingFailed") } : e,
          ),
        }));
      }
    }
  }

  async function onRemoveCharacterPhotoAt(i, entryIndex) {
    const charId = config.characters[i]?.id;
    if (!charId) return;
    const list = characterPhotos[charId] || [];
    const entry = list[entryIndex];
    if (!entry) return;
    setCharacterPhotos((prev) => ({
      ...prev,
      [charId]: (prev[charId] || []).filter((_, idx) => idx !== entryIndex),
    }));
    if (projectName && entry.slot != null) {
      api.deleteCharacterPhotoSlot(projectName, charId, entry.slot).catch(() => {});
    }
  }

  function addLocation() {
    setConfig((c) => ({
      ...c,
      locations: [...c.locations, blankLocation(c.locations.length + 1)],
    }));
  }
  function updateLocation(i, field, value) {
    setConfig((c) => {
      const next = structuredClone(c);
      const oldId = next.locations[i].id;
      next.locations[i][field] = value;
      if (field === "id" && oldId !== value && oldId) {
        setLocationPhotos((prev) => {
          if (!prev[oldId]) return prev;
          const out = { ...prev };
          out[value] = prev[oldId];
          delete out[oldId];
          return out;
        });
      }
      return next;
    });
  }
  function removeLocation(i) {
    setConfig((c) => {
      const next = structuredClone(c);
      const removed = next.locations.splice(i, 1)[0];
      if (removed?.id) {
        setLocationPhotos((prev) => {
          if (!prev[removed.id]) return prev;
          const out = { ...prev };
          delete out[removed.id];
          return out;
        });
        if (projectName) {
          api.deleteLocationPhoto(projectName, removed.id).catch(() => {});
        }
      }
      return next;
    });
  }

  async function onAddLocationPhoto(i, file) {
    if (!file) return;
    const locId = config.locations[i]?.id;
    if (!locId) return;
    const localUrl = URL.createObjectURL(file);

    setLocationPhotos((prev) => ({
      ...prev,
      [locId]: [...(prev[locId] || []), { slot: null, url: localUrl, file, uploading: false, error: null }],
    }));

    // Extract location info — only fills fields that are still empty
    try {
      const extracted = await api.locationFromPhoto(file, config.metadata.language || defaultMetadataLanguage());
      setConfig((c) => {
        const next = structuredClone(c);
        const row = next.locations[i];
        if (!row) return c;
        if (!row.name && extracted.name) row.name = extracted.name;
        if (!row.description && extracted.description) row.description = extracted.description;
        return next;
      });
    } catch {
      // extraction failure is non-fatal
    }

    if (projectName) {
      setLocationPhotos((prev) => ({
        ...prev,
        [locId]: (prev[locId] || []).map((e) => (e.file === file ? { ...e, uploading: true } : e)),
      }));
      try {
        const { slot, url } = await api.addLocationPhoto(projectName, locId, file);
        setLocationPhotos((prev) => ({
          ...prev,
          [locId]: (prev[locId] || []).map((e) =>
            e.file === file ? { slot, url: url || localUrl, file: null, uploading: false, error: null } : e,
          ),
        }));
      } catch (uploadErr) {
        setLocationPhotos((prev) => ({
          ...prev,
          [locId]: (prev[locId] || []).map((e) =>
            e.file === file ? { ...e, uploading: false, error: uploadErr.message || t("form.uploadingFailed") } : e,
          ),
        }));
      }
    }
  }

  async function onRemoveLocationPhotoAt(i, entryIndex) {
    const locId = config.locations[i]?.id;
    if (!locId) return;
    const entry = (locationPhotos[locId] || [])[entryIndex];
    if (!entry) return;
    setLocationPhotos((prev) => ({
      ...prev,
      [locId]: (prev[locId] || []).filter((_, idx) => idx !== entryIndex),
    }));
    if (projectName && entry.slot != null) {
      api.deleteLocationPhotoSlot(projectName, locId, entry.slot).catch(() => {});
    }
  }

  function addObject() {
    setConfig((c) => ({
      ...c,
      objects: [...c.objects, blankObject(c.objects.length + 1)],
    }));
  }
  function updateObject(i, field, value) {
    setConfig((c) => {
      const next = structuredClone(c);
      const oldId = next.objects[i].id;
      next.objects[i][field] = value;
      if (field === "id" && oldId !== value && oldId) {
        setObjectPhotos((prev) => {
          if (!prev[oldId]) return prev;
          const out = { ...prev };
          out[value] = prev[oldId];
          delete out[oldId];
          return out;
        });
      }
      return next;
    });
  }
  function removeObject(i) {
    setConfig((c) => {
      const next = structuredClone(c);
      const removed = next.objects.splice(i, 1)[0];
      if (removed?.id) {
        setObjectPhotos((prev) => {
          if (!prev[removed.id]) return prev;
          const out = { ...prev };
          delete out[removed.id];
          return out;
        });
        if (projectName) {
          api.deleteObjectPhoto(projectName, removed.id).catch(() => {});
        }
      }
      return next;
    });
  }

  async function onAddObjectPhoto(i, file) {
    if (!file) return;
    const objId = config.objects[i]?.id;
    if (!objId) return;
    const localUrl = URL.createObjectURL(file);

    setObjectPhotos((prev) => ({
      ...prev,
      [objId]: [...(prev[objId] || []), { slot: null, url: localUrl, file, uploading: false, error: null }],
    }));

    // Extract object info — only fills fields that are still empty
    try {
      const extracted = await api.objectFromPhoto(file, config.metadata.language || defaultMetadataLanguage());
      setConfig((c) => {
        const next = structuredClone(c);
        const row = next.objects[i];
        if (!row) return c;
        if (!row.name && extracted.name) row.name = extracted.name;
        if (!row.description && extracted.description) row.description = extracted.description;
        return next;
      });
    } catch {
      // extraction failure is non-fatal
    }

    if (projectName) {
      setObjectPhotos((prev) => ({
        ...prev,
        [objId]: (prev[objId] || []).map((e) => (e.file === file ? { ...e, uploading: true } : e)),
      }));
      try {
        const { slot, url } = await api.addObjectPhoto(projectName, objId, file);
        setObjectPhotos((prev) => ({
          ...prev,
          [objId]: (prev[objId] || []).map((e) =>
            e.file === file ? { slot, url: url || localUrl, file: null, uploading: false, error: null } : e,
          ),
        }));
      } catch (uploadErr) {
        setObjectPhotos((prev) => ({
          ...prev,
          [objId]: (prev[objId] || []).map((e) =>
            e.file === file ? { ...e, uploading: false, error: uploadErr.message || t("form.uploadingFailed") } : e,
          ),
        }));
      }
    }
  }

  async function onRemoveObjectPhotoAt(i, entryIndex) {
    const objId = config.objects[i]?.id;
    if (!objId) return;
    const entry = (objectPhotos[objId] || [])[entryIndex];
    if (!entry) return;
    setObjectPhotos((prev) => ({
      ...prev,
      [objId]: (prev[objId] || []).filter((_, idx) => idx !== entryIndex),
    }));
    if (projectName && entry.slot != null) {
      api.deleteObjectPhotoSlot(projectName, objId, entry.slot).catch(() => {});
    }
  }

  function prepareConfig() {
    const out = structuredClone(config);
    if (isNew && !out.project) {
      out.project = slugifyProjectName(out.display_name || out.metadata.title);
    }
    out.display_name = out.display_name?.trim() || null;
    out.structure.page_count = Number(out.structure.page_count);
    out.structure.panels_per_page_avg = Number(out.structure.panels_per_page_avg);
    out.structure.panels_per_page_range = [
      Number(out.structure.panels_per_page_range[0]),
      Number(out.structure.panels_per_page_range[1]),
    ];
    out.generation_options.script_model.temperature = Number(out.generation_options.script_model.temperature);
    normaliseScriptEffort(out.generation_options.script_model);
    out.generation_options.upscale.target_megapixels = Number(out.generation_options.upscale.target_megapixels);
    out.generation_options.upscale.scale_factor = Number(out.generation_options.upscale.scale_factor);
    out.generation_options.upscale.output_quality = Number(out.generation_options.upscale.output_quality);
    return out;
  }

  async function maybeUploadStyleRef(out) {
    if (!styleRefFile) return;
    const projName = projectName || out.project;
    if (!projName) return;
    try {
      await api.setStyleReference(projName, styleRefFile);
    } catch {
      /* non-fatal */
    }
  }

  async function maybeUploadPendingCharacterPhotos(out) {
    const projName = projectName || out.project;
    if (!projName) return;
    for (const c of out.characters || []) {
      const photoList = characterPhotos[c.id] || [];
      for (const entry of photoList.filter((e) => e.file)) {
        try {
          const { slot, url } = await api.addCharacterPhoto(projName, c.id, entry.file);
          setCharacterPhotos((prev) => ({
            ...prev,
            [c.id]: (prev[c.id] || []).map((e) =>
              e.file === entry.file ? { slot, url: url || entry.url, file: null, uploading: false, error: null } : e,
            ),
          }));
        } catch {
          // non-fatal
        }
      }
    }
  }

  async function maybeUploadPendingLocationPhotos(out) {
    const projName = projectName || out.project;
    if (!projName) return;
    for (const l of out.locations || []) {
      const photoList = locationPhotos[l.id] || [];
      for (const entry of photoList.filter((e) => e.file)) {
        try {
          const { slot, url } = await api.addLocationPhoto(projName, l.id, entry.file);
          setLocationPhotos((prev) => ({
            ...prev,
            [l.id]: (prev[l.id] || []).map((e) =>
              e.file === entry.file ? { slot, url: url || entry.url, file: null, uploading: false, error: null } : e,
            ),
          }));
        } catch {
          // non-fatal
        }
      }
    }
  }

  async function maybeUploadPendingObjectPhotos(out) {
    const projName = projectName || out.project;
    if (!projName) return;
    for (const o of out.objects || []) {
      const photoList = objectPhotos[o.id] || [];
      for (const entry of photoList.filter((e) => e.file)) {
        try {
          const { slot, url } = await api.addObjectPhoto(projName, o.id, entry.file);
          setObjectPhotos((prev) => ({
            ...prev,
            [o.id]: (prev[o.id] || []).map((e) =>
              e.file === entry.file ? { slot, url: url || entry.url, file: null, uploading: false, error: null } : e,
            ),
          }));
        } catch {
          // non-fatal
        }
      }
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const out = prepareConfig();
      await onSubmit(out);
      await maybeUploadStyleRef(out);
      await maybeUploadPendingCharacterPhotos(out);
      await maybeUploadPendingLocationPhotos(out);
      await maybeUploadPendingObjectPhotos(out);
    } catch (e) {
      setError(formatError(e, t));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApplyStyleOnly() {
    if (!onApplyStyleOnly) return;
    if (
      !window.confirm(t("form.styleConfirm"))
    )
      return;
    setError(null);
    setApplyingStyleOnly(true);
    try {
      const out = prepareConfig();
      await maybeUploadStyleRef(out);
      await onApplyStyleOnly(out);
    } catch (e) {
      setError(formatError(e, t));
    } finally {
      setApplyingStyleOnly(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Section id="sec-identite" title={t("form.identity.title")}>
        <Field
          label={t("form.identity.nameLabel")}
          hint={t("form.identity.nameHint")}
        >
          <input
            className="input"
            value={config.display_name || ""}
            onChange={(e) => set("display_name", e.target.value)}
            placeholder={t("form.identity.namePlaceholder")}
          />
        </Field>
        {isNew && (
          <Field
            label={t("form.identity.slugLabel")}
            hint={t("form.identity.slugHint")}
          >
            <input
              className="input"
              value={config.project}
              onChange={(e) => set("project", e.target.value.replace(/\s+/g, "_"))}
              placeholder={t("form.identity.slugPlaceholder")}
            />
          </Field>
        )}
        <Grid cols={2}>
          <Field label={t("form.identity.comicTitleLabel")} hint={t("form.identity.comicTitleHint")}>
            <input
              className="input"
              value={config.metadata.title}
              onChange={(e) => set("metadata.title", e.target.value)}
              required
            />
          </Field>
          <Field label={t("form.identity.authorLabel")}>
            <input
              className="input"
              value={config.metadata.author}
              onChange={(e) => set("metadata.author", e.target.value)}
              required
            />
          </Field>
          <Field label={t("form.identity.languageLabel")}>
            <input
              className="input"
              value={config.metadata.language}
              onChange={(e) => set("metadata.language", e.target.value)}
            />
          </Field>
        </Grid>
      </Section>

      <Section id="sec-histoire" title={t("form.story.title")}>
        <Field label={t("form.story.synopsisLabel")} hint={t("form.story.synopsisHint")}>
          <textarea
            className="textarea min-h-[7rem]"
            value={config.story.synopsis}
            onChange={(e) => set("story.synopsis", e.target.value)}
            required
          />
        </Field>
        <Grid cols={2}>
          <Field label={t("form.story.genreLabel")}>
            <ComboBox
              value={config.story.genre || ""}
              options={presetsFor("storyGenre", i18n.language)}
              onChange={(v) => set("story.genre", v)}
              placeholder={t("form.story.genrePlaceholder")}
            />
          </Field>
          <Field label={t("form.story.toneLabel")}>
            <ComboBox
              value={config.story.tone || ""}
              options={presetsFor("storyTone", i18n.language)}
              onChange={(v) => set("story.tone", v)}
              placeholder={t("form.story.tonePlaceholder")}
            />
          </Field>
          <Field label={t("form.story.settingLabel")}>
            <ComboBox
              value={config.story.setting || ""}
              options={presetsFor("storySetting", i18n.language)}
              onChange={(v) => set("story.setting", v)}
              placeholder={t("form.story.settingPlaceholder")}
            />
          </Field>
          <Field label={t("form.story.audienceLabel")}>
            <ComboBox
              value={config.story.target_audience || ""}
              options={presetsFor("storyAudience", i18n.language)}
              onChange={(v) => set("story.target_audience", v)}
              placeholder={t("form.story.audiencePlaceholder")}
            />
          </Field>
        </Grid>
      </Section>

      <Section
        id="sec-style"
        title={t("form.sections.visualStyle")}
        action={
          <button
            type="button"
            className="btn btn-secondary text-sm inline-flex items-center gap-2"
            onClick={() => setStyleFromImageOpen(true)}
          >
            <FaPalette aria-hidden /> {t("form.actions.styleFromImage")}
          </button>
        }
      >
        <StyleReferenceCard
          url={styleRefLocalPreview || styleRefUrl}
          onPickImage={() => setStyleFromImageOpen(true)}
          config={config}
          set={set}
        />
      </Section>

      <Section
        id="sec-casting"
        title={t("form.casting.title")}
        intro={t("form.casting.intro")}
        action={
          projectName ? <ReferencesBundlePanel projectName={projectName} onImported={onReferencesImported} /> : null
        }
      >
        <Subsection
          title={t("form.casting.charactersTitle")}
          action={
            <button
              type="button"
              className="btn btn-secondary text-sm inline-flex items-center gap-2"
              onClick={addCharacter}
            >
              <FaPlus aria-hidden /> {t("form.casting.addButton")}
            </button>
          }
        >
          <Toggle
            label={t("form.casting.aiAllowCharacters")}
            value={config.structure.allow_extra_characters}
            onChange={(v) => set("structure.allow_extra_characters", v)}
          />
          {config.characters.length === 0 && (
            <p className="text-sm text-[var(--color-mute)]">
              {t("form.casting.noCharacters")}
              {config.structure.allow_extra_characters ? t("form.casting.aiSuggestsCharacters") : ""}
            </p>
          )}
          <div className="space-y-4">
            {config.characters.map((c, i) => (
              <div key={i} className="card p-4 bg-[var(--color-paper-soft)]/40">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[var(--color-mute)] uppercase tracking-wide">{t("form.casting.cardHeading", { n: i + 1 })}</span>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
                    onClick={() => removeCharacter(i)}
                    title={t("form.casting.removeAria")}
                  >
                    <FaTrash aria-hidden /> {t("common.delete")}
                  </button>
                </div>
                <MultiPhotosField
                  entityIndex={i}
                  kind="character"
                  photos={characterPhotos[c.id] || []}
                  maxPhotos={config.generation_options?.references?.image_model?.provider === "xai" ? 2 : 4}
                  onAdd={(file) => onAddCharacterPhoto(i, file)}
                  onRemove={(idx) => onRemoveCharacterPhotoAt(i, idx)}
                />
                <ReferenceImagePreview
                  url={initialReferenceImages?.characters?.[c.id]}
                  label={t("form.casting.refPreview", { name: c.name || c.id })}
                />
                <Grid cols={2}>
                  <Field label={t("form.casting.idLabel")} hint={t("form.casting.idHint")}>
                    <input
                      className="input"
                      value={c.id}
                      onChange={(e) => updateCharacter(i, "id", e.target.value.replace(/\s+/g, "_"))}
                    />
                  </Field>
                  <Field label={t("form.casting.nameLabel")}>
                    <input
                      className="input"
                      value={c.name}
                      onChange={(e) => updateCharacter(i, "name", e.target.value)}
                      required
                    />
                  </Field>
                  <Field label={t("form.casting.roleLabel")}>
                    <input
                      className="input"
                      value={c.role || ""}
                      onChange={(e) => updateCharacter(i, "role", e.target.value)}
                      placeholder={t("form.casting.rolePlaceholder")}
                    />
                  </Field>
                  <Field label={t("form.casting.personalityLabel")}>
                    <input
                      className="input"
                      value={c.personality || ""}
                      onChange={(e) => updateCharacter(i, "personality", e.target.value)}
                    />
                  </Field>
                </Grid>
                <Field label={t("form.casting.physicalLabel")}>
                  <textarea
                    className="textarea"
                    value={c.physical_description}
                    onChange={(e) => updateCharacter(i, "physical_description", e.target.value)}
                    required
                  />
                </Field>
                <Field label={t("form.casting.outfitLabel")}>
                  <textarea
                    className="textarea"
                    value={c.outfit || ""}
                    onChange={(e) => updateCharacter(i, "outfit", e.target.value)}
                  />
                </Field>
              </div>
            ))}
          </div>
        </Subsection>

        <Subsection
          title={t("form.casting.locationsTitle")}
          action={
            <button
              type="button"
              className="btn btn-secondary text-sm inline-flex items-center gap-2"
              onClick={addLocation}
            >
              <FaPlus aria-hidden /> {t("form.casting.addButton")}
            </button>
          }
        >
          <Toggle
            label={t("form.casting.aiAllowLocations")}
            value={config.structure.allow_extra_locations}
            onChange={(v) => set("structure.allow_extra_locations", v)}
          />
          {config.locations.length === 0 && (
            <p className="text-sm text-[var(--color-mute)]">
              {t("form.casting.noLocations")}
              {config.structure.allow_extra_locations
                ? t("form.casting.aiSuggestsLocations")
                : t("form.casting.noLocationsWarning")}
            </p>
          )}
          <div className="space-y-4">
            {config.locations.map((l, i) => (
              <div key={i} className="card p-4 bg-[var(--color-paper-soft)]/40">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[var(--color-mute)] uppercase tracking-wide">{t("form.casting.locationCardHeading", { n: i + 1 })}</span>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
                    onClick={() => removeLocation(i)}
                    title={t("form.casting.removeLocationAria")}
                  >
                    <FaTrash aria-hidden /> {t("common.delete")}
                  </button>
                </div>
                <MultiPhotosField
                  entityIndex={i}
                  kind="location"
                  photos={locationPhotos[l.id] || []}
                  maxPhotos={config.generation_options?.references?.image_model?.provider === "xai" ? 2 : 4}
                  onAdd={(file) => onAddLocationPhoto(i, file)}
                  onRemove={(idx) => onRemoveLocationPhotoAt(i, idx)}
                />
                <ReferenceImagePreview
                  url={initialReferenceImages?.locations?.[l.id]}
                  label={t("form.casting.refPreview", { name: l.name || l.id })}
                />
                <Grid cols={2}>
                  <Field label={t("form.casting.idLabel")} hint={t("form.casting.idHint")}>
                    <input
                      className="input"
                      value={l.id}
                      onChange={(e) => updateLocation(i, "id", e.target.value.replace(/\s+/g, "_"))}
                    />
                  </Field>
                  <Field label={t("form.casting.nameLabel")}>
                    <input
                      className="input"
                      value={l.name}
                      onChange={(e) => updateLocation(i, "name", e.target.value)}
                      required
                    />
                  </Field>
                </Grid>
                <Field label={t("form.casting.descriptionLabel")} hint={t("form.casting.descriptionHint")}>
                  <textarea
                    className="textarea"
                    value={l.description}
                    onChange={(e) => updateLocation(i, "description", e.target.value)}
                    required
                  />
                </Field>
              </div>
            ))}
          </div>
        </Subsection>

        <Subsection
          title={t("form.casting.objectsTitle")}
          action={
            <button
              type="button"
              className="btn btn-secondary text-sm inline-flex items-center gap-2"
              onClick={addObject}
            >
              <FaPlus aria-hidden /> {t("form.casting.addButton")}
            </button>
          }
        >
          <p className="text-sm text-[var(--color-mute)]">
            {t("form.casting.objectsIntro")}
          </p>
          <Toggle
            label={t("form.casting.aiAllowObjects")}
            value={config.structure.allow_extra_objects}
            onChange={(v) => set("structure.allow_extra_objects", v)}
          />
          {config.objects.length === 0 && (
            <p className="text-sm text-[var(--color-mute)]">
              {t("form.casting.noObjects")}
              {config.structure.allow_extra_objects ? t("form.casting.aiMarginObjects") : ""}
            </p>
          )}
          <div className="space-y-4">
            {config.objects.map((o, i) => (
              <div key={i} className="card p-4 bg-[var(--color-paper-soft)]/40">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[var(--color-mute)] uppercase tracking-wide">{t("form.casting.objectCardHeading", { n: i + 1 })}</span>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
                    onClick={() => removeObject(i)}
                    title={t("form.casting.removeObjectAria")}
                  >
                    <FaTrash aria-hidden /> {t("common.delete")}
                  </button>
                </div>
                <MultiPhotosField
                  entityIndex={i}
                  kind="object"
                  photos={objectPhotos[o.id] || []}
                  maxPhotos={config.generation_options?.references?.image_model?.provider === "xai" ? 2 : 4}
                  onAdd={(file) => onAddObjectPhoto(i, file)}
                  onRemove={(idx) => onRemoveObjectPhotoAt(i, idx)}
                />
                <ReferenceImagePreview
                  url={initialReferenceImages?.objects?.[o.id]}
                  label={t("form.casting.refPreview", { name: o.name || o.id })}
                />
                <Grid cols={2}>
                  <Field label={t("form.casting.idLabel")} hint={t("form.casting.idHint")}>
                    <input
                      className="input"
                      value={o.id}
                      onChange={(e) => updateObject(i, "id", e.target.value.replace(/\s+/g, "_"))}
                    />
                  </Field>
                  <Field label={t("form.casting.nameLabel")}>
                    <input
                      className="input"
                      value={o.name}
                      onChange={(e) => updateObject(i, "name", e.target.value)}
                      required
                    />
                  </Field>
                </Grid>
                <Field label={t("form.casting.descriptionLabel")} hint={t("form.casting.objectDescriptionHint")}>
                  <textarea
                    className="textarea"
                    value={o.description}
                    onChange={(e) => updateObject(i, "description", e.target.value)}
                    required
                  />
                </Field>
              </div>
            ))}
          </div>
        </Subsection>
      </Section>

      <Section id="sec-structure" title={t("form.structure.title")}>
        <Grid cols={3}>
          <Field label={t("form.structure.pageCountLabel")}>
            <input
              type="number"
              min={1}
              max={99}
              className="input"
              value={config.structure.page_count}
              onChange={(e) => set("structure.page_count", e.target.value)}
            />
          </Field>
          <Field label={t("form.structure.avgPanelsLabel")}>
            <input
              type="number"
              min={1}
              max={12}
              className="input"
              value={config.structure.panels_per_page_avg}
              onChange={(e) => set("structure.panels_per_page_avg", e.target.value)}
            />
          </Field>
          <Field label={t("form.structure.panelsRangeLabel")}>
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                max={99}
                className="input"
                value={config.structure.panels_per_page_range[0]}
                onChange={(e) =>
                  set("structure.panels_per_page_range", [e.target.value, config.structure.panels_per_page_range[1]])
                }
              />
              <input
                type="number"
                min={1}
                max={99}
                className="input"
                value={config.structure.panels_per_page_range[1]}
                onChange={(e) =>
                  set("structure.panels_per_page_range", [config.structure.panels_per_page_range[0], e.target.value])
                }
              />
            </div>
          </Field>
        </Grid>
        <Grid cols={2}>
          <Toggle
            label={t("form.structure.includeCoverLabel")}
            value={config.structure.include_cover}
            onChange={(v) => set("structure.include_cover", v)}
          />
          <Toggle
            label={t("form.structure.includeBackCoverLabel")}
            value={config.structure.include_back_cover}
            onChange={(v) => set("structure.include_back_cover", v)}
          />
        </Grid>
        <Field label={t("form.structure.pageFormatLabel")} hint={t("form.structure.pageFormatHint")}>
          <select
            className="select"
            value={config.structure.page_format}
            onChange={(e) => set("structure.page_format", e.target.value)}
          >
            <option value="portrait">{t("form.structure.pageFormatPortrait")}</option>
            <option value="landscape">{t("form.structure.pageFormatLandscape")}</option>
            <option value="square">{t("form.structure.pageFormatSquare")}</option>
            <option value="strip">{t("form.structure.pageFormatStrip")}</option>
          </select>
        </Field>
        <Field label={t("form.structure.narrativePaceLabel")}>
          <input
            className="input"
            value={config.structure.narrative_pacing || ""}
            onChange={(e) => set("structure.narrative_pacing", e.target.value)}
            placeholder={t("form.structure.narrativePacePlaceholder")}
          />
        </Field>
      </Section>

      <Section id="sec-modeles" title={t("form.models.title")}>
        <Subsection title={t("form.models.scriptTitle")}>
          <Grid cols={2}>
            <Field label={t("form.models.scriptProviderLabel")}>
              <select
                className="select"
                value={config.generation_options.script_model.provider}
                onChange={(e) => setModelProvider("script_model", e.target.value, SCRIPT_MODEL_OPTIONS)}
              >
                <option value="anthropic">Anthropic</option>
                <option value="openai">OpenAI</option>
                <option value="xai">xAI</option>
              </select>
            </Field>
            <Field label={t("form.models.scriptModelLabel")}>
              <ModelSelector
                provider={config.generation_options.script_model.provider}
                model={config.generation_options.script_model.model}
                optionsByProvider={SCRIPT_MODEL_OPTIONS}
                onChange={setScriptModel}
              />
            </Field>
            {supportsScriptEffort(
              config.generation_options.script_model.provider,
              config.generation_options.script_model.model,
            ) && (
              <Field
                label={t("form.models.scriptEffortLabel")}
                hint={t("form.models.scriptEffortHint")}
              >
                <OptionSelect
                  value={
                    config.generation_options.script_model.effort ||
                    DEFAULT_CONFIG.generation_options.script_model.effort
                  }
                  options={SCRIPT_EFFORT_OPTIONS}
                  onChange={(value) => set("generation_options.script_model.effort", value)}
                />
              </Field>
            )}
          </Grid>
        </Subsection>

        <Subsection title={t("form.models.imagesTitle")}>
          <Grid cols={2}>
            <Field label={t("form.models.imagesProviderLabel")}>
              <select
                className="select"
                value={config.generation_options.image_model.provider}
                onChange={(e) => setModelProvider("image_model", e.target.value, IMAGE_MODEL_OPTIONS)}
              >
                <option value="openai">OpenAI</option>
              </select>
            </Field>
            <Field label={t("form.models.imagesModelLabel")}>
              <ModelSelector
                provider={config.generation_options.image_model.provider}
                model={config.generation_options.image_model.model}
                optionsByProvider={IMAGE_MODEL_OPTIONS}
                onChange={(value) => set("generation_options.image_model.model", value)}
              />
            </Field>
            <Field label={t("form.models.imagesQualityLabel")}>
              <OptionSelect
                value={config.generation_options.image_model.quality}
                options={QUALITY_OPTIONS}
                onChange={(value) => set("generation_options.image_model.quality", value)}
              />
            </Field>
          </Grid>
        </Subsection>

        <Subsection title={t("form.models.referencesTitle")}>
          <Toggle
            label={t("form.models.referencesUseDedicatedLabel")}
            value={!!config.generation_options.references.image_model}
            onChange={setReferenceImageModelEnabled}
          />
          {config.generation_options.references.image_model && (
            <Grid cols={2}>
              <Field label={t("form.models.referencesProviderLabel")}>
                <select
                  className="select"
                  value={config.generation_options.references.image_model.provider}
                  onChange={(e) => setReferenceModelProvider(e.target.value)}
                >
                  <option value="openai">OpenAI</option>
                  <option value="xai">xAI / Grok</option>
                </select>
              </Field>
              <Field label={t("form.models.referencesModelLabel")}>
                <ModelSelector
                  provider={config.generation_options.references.image_model.provider}
                  model={config.generation_options.references.image_model.model}
                  optionsByProvider={IMAGE_MODEL_OPTIONS}
                  onChange={(value) => set("generation_options.references.image_model.model", value)}
                />
              </Field>
              <Field label={t("form.models.referencesQualityLabel")}>
                <OptionSelect
                  value={config.generation_options.references.image_model.quality}
                  options={QUALITY_OPTIONS}
                  onChange={(value) => set("generation_options.references.image_model.quality", value)}
                />
              </Field>
            </Grid>
          )}
        </Subsection>

        <Subsection title={t("form.models.outputTitle")}>
          <Grid cols={2}>
            <Field label={t("form.models.outputFormatLabel")}>
              <select
                className="select"
                value={config.generation_options.output_format}
                onChange={(e) => set("generation_options.output_format", e.target.value)}
              >
                <option value="pdf">PDF</option>
                <option value="images">Images</option>
              </select>
            </Field>
          </Grid>
        </Subsection>

        {SHOW_UPSCALE && (
          <Subsection title={t("form.models.upscaleTitle")}>
            <Grid cols={2}>
              <Toggle
                label={t("form.models.upscaleEnableLabel")}
                value={config.generation_options.upscale.enabled}
                onChange={(v) => set("generation_options.upscale.enabled", v)}
              />
              <Field
                label={t("form.models.upscaleModeLabel")}
                hint={t("form.models.upscaleModeHint")}
              >
                <select
                  className="select"
                  value={config.generation_options.upscale.mode}
                  onChange={(e) => set("generation_options.upscale.mode", e.target.value)}
                >
                  <option value="target">{t("form.models.upscaleModeTarget")}</option>
                  <option value="factor">{t("form.models.upscaleModeFactor")}</option>
                </select>
              </Field>
            </Grid>

            <Grid cols={2}>
              <Field label={t("form.models.upscaleTargetLabel")} hint={t("form.models.upscaleTargetHint")}>
                <input
                  type="number"
                  min={1}
                  max={8}
                  step={1}
                  className="input"
                  value={config.generation_options.upscale.target_megapixels}
                  onChange={(e) => set("generation_options.upscale.target_megapixels", e.target.value)}
                  disabled={config.generation_options.upscale.mode !== "target"}
                />
              </Field>
              <Field
                label={t("form.models.upscaleFactorLabel")}
                hint={t("form.models.upscaleFactorHint")}
              >
                <input
                  type="number"
                  min={1}
                  max={8}
                  step={0.1}
                  className="input"
                  value={config.generation_options.upscale.scale_factor}
                  onChange={(e) => set("generation_options.upscale.scale_factor", e.target.value)}
                  disabled={config.generation_options.upscale.mode !== "factor"}
                />
              </Field>
              <Field label={t("form.models.upscaleFormatLabel")}>
                <select
                  className="select"
                  value={config.generation_options.upscale.output_format}
                  onChange={(e) => set("generation_options.upscale.output_format", e.target.value)}
                >
                  <option value="png">PNG</option>
                  <option value="jpg">JPEG</option>
                  <option value="webp">WebP</option>
                </select>
              </Field>
              <Field label={t("form.models.upscaleQualityLabel")} hint={t("form.models.upscaleQualityHint")}>
                <input
                  type="number"
                  min={1}
                  max={100}
                  step={1}
                  className="input"
                  value={config.generation_options.upscale.output_quality}
                  onChange={(e) => set("generation_options.upscale.output_quality", e.target.value)}
                  disabled={config.generation_options.upscale.output_format === "png"}
                />
              </Field>
            </Grid>

            <p className="text-xs text-[var(--color-mute)]">
              <span dangerouslySetInnerHTML={{ __html: t("form.models.upscaleFootnote", { interpolation: { skipOnVariables: false } })
                .replace("REPLICATE_API_TOKEN", "<code>REPLICATE_API_TOKEN</code>")
                .replace(".env", "<code>.env</code>") }} />
            </p>
          </Subsection>
        )}
      </Section>

      {error && (
        <div className="card p-4 bg-[var(--color-rose-100)] border-[var(--color-rose-300)] text-[var(--color-rose-500)] text-sm">
          {error}
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-3">
        {onCancel && (
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            {t("common.cancel")}
          </button>
        )}
        {onApplyStyleOnly && (
          <button
            type="button"
            className="btn btn-secondary inline-flex items-center gap-2"
            onClick={handleApplyStyleOnly}
            disabled={submitting || applyingStyleOnly}
            title={t("form.applyStyleTitle")}
          >
            <FaPalette aria-hidden />
            {applyingStyleOnly ? t("form.applyingStyle") : (applyStyleOnlyLabel || t("form.actions.applyStyleOnly"))}
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={submitting || applyingStyleOnly}>
          {submitting ? t("form.savingForm") : (submitLabel || t("form.actions.save"))}
        </button>
      </div>

      {styleFromImageOpen && (
        <StyleFromImageDialog
          language={config.metadata.language || defaultMetadataLanguage()}
          onClose={() => setStyleFromImageOpen(false)}
          onApply={({ style, characters, locations, file }) => {
            setStyleRefFile(file || null);
            if (file) {
              setStyleRefLocalPreview(URL.createObjectURL(file));
              if (projectName) {
                api
                  .setStyleReference(projectName, file)
                  .then(({ url }) => {
                    if (url) setStyleRefUrl(url);
                  })
                  .catch(() => {});
              }
            }
            setConfig((c) => {
              const next = {
                ...c,
                style: {
                  ...c.style,
                  art_style: style.art_style ?? c.style.art_style,
                  color_palette: style.color_palette ?? c.style.color_palette,
                  line_work: style.line_work ?? c.style.line_work,
                  mood: style.mood ?? c.style.mood,
                  panel_borders: style.panel_borders ?? c.style.panel_borders,
                  speech_bubbles: style.speech_bubbles ?? c.style.speech_bubbles,
                  character_rendering: style.character_rendering ?? c.style.character_rendering,
                },
              };
              if (Array.isArray(characters) && characters.length > 0) {
                const used = new Set(c.characters.map((x) => x.id));
                next.characters = [
                  ...c.characters,
                  ...characters.map((nc) => ({
                    ...nc,
                    id: dedupeId(nc.id, used),
                  })),
                ];
              }
              if (Array.isArray(locations) && locations.length > 0) {
                const used = new Set(c.locations.map((x) => x.id));
                next.locations = [
                  ...c.locations,
                  ...locations.map((nl) => ({
                    ...nl,
                    id: dedupeId(nl.id, used),
                  })),
                ];
              }
              return next;
            });
          }}
        />
      )}
    </form>
  );
}

function Section({ id, title, intro, action, children }) {
  return (
    <div id={id} className="card p-6 scroll-mt-4">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="flex-1 min-w-[12rem]">
          <h3 className="text-base font-semibold">{title}</h3>
          {intro && <p className="text-sm text-[var(--color-mute)] mt-1">{intro}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Subsection({ title, action, children }) {
  return (
    <div className="border-t border-[var(--color-line)] pt-5 first:border-t-0 first:pt-0">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-ink-soft)]">{title}</h4>
        {action}
      </div>
      <div className="space-y-4">{children}</div>
    </div>
  );
}

function Field({ label, hint, children }) {
  return (
    <div>
      <label className="label">{label}</label>
      {children}
      {hint && <p className="text-xs text-[var(--color-mute)] mt-1">{hint}</p>}
    </div>
  );
}

function ComboBox({ value, options, onChange, placeholder, required = false, disabled = false }) {
  const { t } = useTranslation();
  // A non-preset value forces manual mode; otherwise the user can opt in
  // by picking "Saisir manuellement…", which we remember locally so the
  // input stays visible even while the value is empty.
  const valueForcesCustom = !!value && !options.includes(value);
  const [userPickedCustom, setUserPickedCustom] = useState(false);
  const customMode = valueForcesCustom || userPickedCustom;
  const selectValue = customMode ? "__custom__" : value || "";
  return (
    <div className="space-y-2">
      <select
        className="select"
        value={selectValue}
        onChange={(e) => {
          if (e.target.value === "__custom__") {
            setUserPickedCustom(true);
            return;
          }
          setUserPickedCustom(false);
          onChange(e.target.value);
        }}
        required={required && !customMode && !disabled}
        disabled={disabled}
      >
        <option value="">{t("form.chooseOne")}</option>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
        <option value="__custom__">{t("form.manualEntry")}</option>
      </select>
      {customMode && (
        <input
          className="input"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          required={required && !disabled}
          disabled={disabled}
          autoFocus
        />
      )}
    </div>
  );
}

function OptionSelect({ value, options, onChange }) {
  return (
    <select className="select" value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

function ModelSelector({ provider, model, optionsByProvider, onChange }) {
  const { t } = useTranslation();
  const options = optionsByProvider[provider] || [];
  const known = options.some((option) => option.value === model);
  const selectValue = known ? model : "__custom__";
  const priceText = formatModelPrice(provider, model, t);

  return (
    <div className="space-y-2">
      <select
        className="select"
        value={selectValue}
        onChange={(e) => {
          if (e.target.value === "__custom__") {
            onChange("");
            return;
          }
          onChange(e.target.value);
        }}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
        <option value="__custom__">{t("form.customModel")}</option>
      </select>
      {selectValue === "__custom__" && (
        <input
          className="input"
          value={model}
          onChange={(e) => onChange(e.target.value)}
          placeholder={t("form.customModelPlaceholder")}
        />
      )}
      {priceText ? (
        <p className="text-xs text-[var(--color-mute)]">
          {priceText}
          {hasFastTier(provider, model) ? t("form.priceFastSuffix") : ""}
        </p>
      ) : (
        model && <p className="text-xs text-[var(--color-mute)]">{t("form.priceUnknown")}</p>
      )}
    </div>
  );
}

function Grid({ cols = 2, children }) {
  return <div className={`grid grid-cols-1 md:grid-cols-${cols} gap-4`}>{children}</div>;
}

function ReferenceImagePreview({ url, label }) {
  const { t } = useTranslation();
  if (!url) return null;
  return (
    <div className="mb-4 flex items-start gap-4">
      <div className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center shrink-0">
        <img src={url} alt={label || t("form.styleRefAlt")} className="w-full h-full object-cover" />
      </div>
      <div className="flex-1 min-w-0">
        <label className="label">{t("imageStep.referenceImageLabel")}</label>
        <p className="text-xs text-[var(--color-mute)]">
          {t("imageStep.referenceImageBody")}
        </p>
      </div>
    </div>
  );
}

const _PHOTO_HINTS = {
  character: "form.characterPhotoHint",
  location: "form.locationPhotoHint",
  object: "form.objectPhotoHint",
};

function MultiPhotosField({ entityIndex, kind, photos, maxPhotos, onAdd, onRemove }) {
  const { t } = useTranslation();
  const inputId = `photos-${kind}-${entityIndex}`;
  const canAdd = photos.length < maxPhotos;
  const hintKey = _PHOTO_HINTS[kind] || "form.characterPhotoHint";
  return (
    <div className="mb-4">
      <label className="label">{t("form.referencePhotosLabel")}</label>
      <p className="text-xs text-[var(--color-mute)] mb-2">{t(hintKey)}</p>
      <div className="flex flex-wrap gap-2 items-start">
        {photos.map((entry, idx) => (
          <div key={idx} className="relative shrink-0">
            <div className="w-20 h-20 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center text-xs text-[var(--color-mute)]">
              {entry.url ? (
                <img src={entry.url} alt="" className="w-full h-full object-cover" />
              ) : (
                <span>{entry.uploading ? "…" : "?"}</span>
              )}
            </div>
            {entry.uploading && (
              <div className="absolute inset-0 rounded-lg bg-black/30 flex items-center justify-center">
                <span className="text-white text-xs">↑</span>
              </div>
            )}
            <button
              type="button"
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-[var(--color-rose-500)] text-white text-xs flex items-center justify-center hover:bg-[var(--color-rose-600)] leading-none"
              onClick={() => onRemove(idx)}
              title={t("form.removePhotoAria")}
              aria-label={t("form.removePhotoAria")}
            >
              ×
            </button>
            {entry.error && (
              <p className="text-xs text-[var(--color-rose-500)] mt-0.5 max-w-[5rem] break-words">{entry.error}</p>
            )}
          </div>
        ))}
        {canAdd && (
          <label
            htmlFor={inputId}
            className="w-20 h-20 shrink-0 rounded-lg border-2 border-dashed border-[var(--color-line)] flex flex-col items-center justify-center gap-0.5 cursor-pointer hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] text-[var(--color-mute)] transition-colors"
            title={t("form.addPhotoTitle")}
            aria-label={t("form.addPhotoAria")}
          >
            <FaPlus className="w-4 h-4" aria-hidden />
            <span className="text-xs leading-tight">{t("form.addPhotoAria")}</span>
          </label>
        )}
        <input
          id={inputId}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            e.target.value = "";
            if (f) onAdd(f);
          }}
        />
      </div>
      {photos.length >= maxPhotos && (
        <p className="text-xs text-amber-600 mt-1">{t("form.maxPhotosWarning", { max: maxPhotos })}</p>
      )}
    </div>
  );
}

function StyleReferenceCard({ url, onPickImage, config, set }) {
  const { t, i18n } = useTranslation();
  const [expanded, setExpanded] = useState(false);
  const allowStyleCopy = !!config.allow_style_copy;
  // When a style reference image is uploaded it carries the overall art-style
  // and atmosphere on its own — the matching text fields become redundant
  // (and risk conflicting with the image). Disable them; keep the precise,
  // descriptive fields (palette, line work, borders, bubbles, character
  // rendering) enabled because those refine constraints the image alone
  // cannot pin down (e.g. forcing B&W when the reference is in color).
  const hasStyleRef = !!url;
  // Required `art_style` must remain non-empty for backend validation. Auto-
  // fill with a sentinel when the user uploads a style reference image but
  // left this field blank — it never overrides existing user input.
  useEffect(() => {
    if (hasStyleRef && !(config.style.art_style || "").trim()) {
      set("style.art_style", t("form.artStyleFromImage"));
    }
    // We intentionally fire only on hasStyleRef transitions: re-running on
    // every art_style change would clobber the user's own edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasStyleRef, t]);
  return (
    <div className="space-y-4">
      <div className="flex items-start gap-4">
        <div
          className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center text-xs text-[var(--color-mute)] shrink-0 cursor-pointer"
          onClick={onPickImage}
          title={url ? t("form.styleRefChange") : t("form.styleRefChoose")}
        >
          {url ? (
            <img src={url} alt={t("form.styleRefAlt")} className="w-full h-full object-cover" />
          ) : (
            <span className="text-center px-1">{t("form.styleEmpty")}</span>
          )}
        </div>
        <div className="flex-1 min-w-0 space-y-3">
          <div>
            <label className="label">{t("form.artStyleLabel")}</label>
            <ComboBox
              value={config.style.art_style}
              options={presetsFor("styleArtStyle", i18n.language)}
              onChange={(v) => set("style.art_style", v)}
              placeholder={t("form.artStylePlaceholder")}
              required
              disabled={hasStyleRef}
            />
            <p className="text-xs text-[var(--color-mute)] mt-1">
              {hasStyleRef ? t("form.artStyleDisabledHint") : t("form.noArtistNamesHint")}
            </p>
          </div>
          <button
            type="button"
            className="text-xs text-[var(--color-mute)] hover:text-[var(--color-ink)] inline-flex items-center gap-1 transition-colors"
            onClick={() => setExpanded((v) => !v)}
          >
            <FaChevronDown aria-hidden className={"transition-transform " + (expanded ? "rotate-180" : "")} />
            {expanded ? t("form.expandHide") : t("form.expandShow")}
          </button>
          {expanded && (
            <div className="space-y-3">
              {hasStyleRef && (
                <p className="text-xs text-[var(--color-mute)]">{t("form.expandHint")}</p>
              )}
              <Grid cols={3}>
                <Field label={t("form.colorPaletteLabel")}>
                  <ComboBox
                    value={config.style.color_palette || ""}
                    options={presetsFor("styleColorPalette", i18n.language)}
                    onChange={(v) => set("style.color_palette", v)}
                  />
                </Field>
                <Field label={t("form.lineWorkLabel")}>
                  <ComboBox
                    value={config.style.line_work || ""}
                    options={presetsFor("styleLineWork", i18n.language)}
                    onChange={(v) => set("style.line_work", v)}
                  />
                </Field>
                <Field label={t("form.moodLabel")}>
                  <ComboBox
                    value={config.style.mood || ""}
                    options={presetsFor("styleMood", i18n.language)}
                    onChange={(v) => set("style.mood", v)}
                    disabled={hasStyleRef}
                  />
                  {hasStyleRef && <p className="text-xs text-[var(--color-mute)] mt-1">{t("form.artStyleDisabledHint")}</p>}
                </Field>
              </Grid>
              <Grid cols={3}>
                <Field label={t("form.panelBordersLabel")}>
                  <ComboBox
                    value={config.style.panel_borders || ""}
                    options={presetsFor("stylePanelBorders", i18n.language)}
                    onChange={(v) => set("style.panel_borders", v)}
                    placeholder={t("form.panelBordersPlaceholder")}
                  />
                </Field>
                <Field label={t("form.speechBubblesLabel")}>
                  <ComboBox
                    value={config.style.speech_bubbles || ""}
                    options={presetsFor("styleSpeechBubbles", i18n.language)}
                    onChange={(v) => set("style.speech_bubbles", v)}
                    placeholder={t("form.speechBubblesPlaceholder")}
                  />
                </Field>
                <Field label={t("form.characterRenderingLabel")}>
                  <ComboBox
                    value={config.style.character_rendering || ""}
                    options={presetsFor("styleCharacterRendering", i18n.language)}
                    onChange={(v) => set("style.character_rendering", v)}
                    placeholder={t("form.characterRenderingPlaceholder")}
                  />
                </Field>
              </Grid>
            </div>
          )}
        </div>
      </div>
      <div
        className={
          "rounded-lg border p-3 " +
          (allowStyleCopy
            ? "border-[var(--color-rose-500)] bg-[var(--color-rose-50)]/40"
            : "border-[var(--color-line)] bg-[var(--color-paper-soft)]/40")
        }
      >
        <Toggle
          label={t("form.antiPlagiarismLabel")}
          value={allowStyleCopy}
          onChange={(v) => set("allow_style_copy", v)}
        />
        <p className="text-xs text-[var(--color-mute)] mt-2">
          {t("form.antiPlagiarismDesc")}
        </p>
        {allowStyleCopy && (
          <div
            role="alert"
            className="mt-3 rounded-md border border-[var(--color-rose-500)] bg-[var(--color-rose-50)] p-3 text-sm text-[var(--color-rose-700)]"
          >
            <p className="font-semibold">{t("form.legalTitle")}</p>
            <p className="mt-1">{t("form.legalBody")}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Toggle({ label, value, onChange }) {
  return (
    <label className="flex items-center gap-3 cursor-pointer">
      <span
        className={
          "relative inline-block w-10 h-6 rounded-full transition " +
          (value ? "bg-[var(--color-primary-500)]" : "bg-[var(--color-line)]")
        }
      >
        <input type="checkbox" className="sr-only" checked={value} onChange={(e) => onChange(e.target.checked)} />
        <span
          className={
            "absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition " + (value ? "left-[18px]" : "left-0.5")
          }
        />
      </span>
      <span className="text-sm">{label}</span>
    </label>
  );
}
