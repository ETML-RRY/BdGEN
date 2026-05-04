import { useState, useEffect } from "react";
import {
  FaPlus,
  FaTrash,
  FaUpload,
  FaPalette,
  FaChevronDown,
} from "react-icons/fa6";
import { api } from "../api.js";
import StyleFromImageDialog from "./StyleFromImageDialog.jsx";
import ReferencesBundlePanel from "./ReferencesBundlePanel.jsx";

export const DEFAULT_CONFIG = {
  project: "",
  display_name: "",
  output_root: "./output",
  metadata: { title: "", author: "", language: "fr" },
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
    allow_extra_characters: true,
    allow_extra_locations: true,
    allow_extra_objects: true,
  },
  generation_options: {
    script_model: {
      provider: "anthropic",
      model: "claude-sonnet-4-20250514",
      temperature: 0.8,
    },
    image_model: {
      provider: "openai",
      model: "gpt-image-2",
      size: "1024x1536",
      quality: "high",
    },
    references: {
      generate: true,
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

const SCRIPT_MODEL_OPTIONS = {
  anthropic: [
    { value: "claude-opus-4-1-20250805", label: "Claude Opus 4.1" },
    { value: "claude-opus-4-20250514", label: "Claude Opus 4" },
    { value: "claude-sonnet-4-20250514", label: "Claude Sonnet 4" },
    { value: "claude-3-7-sonnet-20250219", label: "Claude Sonnet 3.7" },
    { value: "claude-3-5-haiku-20241022", label: "Claude Haiku 3.5" },
  ],
  openai: [
    { value: "gpt-5.2", label: "GPT-5.2" },
    { value: "gpt-5.2-pro", label: "GPT-5.2 pro" },
    { value: "gpt-5.1", label: "GPT-5.1" },
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
};

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
  if (!out.generation_options.upscale) {
    out.generation_options.upscale = structuredClone(DEFAULT_CONFIG.generation_options.upscale);
  }
  if (!Array.isArray(out.locations)) out.locations = [];
  if (!Array.isArray(out.objects)) out.objects = [];
  if (!out.structure) out.structure = {};
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
  submitLabel = "Enregistrer",
  onApplyStyleOnly = null,
  applyStyleOnlyLabel = "Appliquer le style uniquement",
}) {
  const [config, setConfig] = useState(() => normalize(initial || DEFAULT_CONFIG));
  const [submitting, setSubmitting] = useState(false);
  const [applyingStyleOnly, setApplyingStyleOnly] = useState(false);
  const [error, setError] = useState(null);
  const [styleFromImageOpen, setStyleFromImageOpen] = useState(false);
  const [styleRefFile, setStyleRefFile] = useState(null);
  const [styleRefUrl, setStyleRefUrl] = useState(null);
  const [styleRefLocalPreview, setStyleRefLocalPreview] = useState(null);
  // Per-character photo state, keyed by character id.
  // Each entry: { url: server-side URL or null, file: pending File or null,
  //               extracting: bool, error: string | null }
  const [characterPhotos, setCharacterPhotos] = useState(() => {
    const out = {};
    for (const [id, url] of Object.entries(initialCharacterPhotos || {})) {
      if (url) out[id] = { url, file: null, extracting: false, error: null };
    }
    return out;
  });
  // Same shape as characterPhotos but keyed by location id.
  const [locationPhotos, setLocationPhotos] = useState(() => {
    const out = {};
    for (const [id, url] of Object.entries(initialLocationPhotos || {})) {
      if (url) out[id] = { url, file: null, extracting: false, error: null };
    }
    return out;
  });
  // Same shape as characterPhotos but keyed by object id.
  const [objectPhotos, setObjectPhotos] = useState(() => {
    const out = {};
    for (const [id, url] of Object.entries(initialObjectPhotos || {})) {
      if (url) out[id] = { url, file: null, extracting: false, error: null };
    }
    return out;
  });

  useEffect(() => {
    if (initial) setConfig(normalize(initial));
  }, [initial]);

  useEffect(() => {
    if (!projectName) return;
    api.getStyleReferenceInfo(projectName).then((info) => {
      if (info?.url) setStyleRefUrl(info.url);
    }).catch(() => {});
  }, [projectName]);

  useEffect(() => {
    if (!initialCharacterPhotos) return;
    setCharacterPhotos((prev) => {
      const next = { ...prev };
      for (const [id, url] of Object.entries(initialCharacterPhotos)) {
        if (!url) continue;
        if (!next[id] || (!next[id].file && next[id].url !== url)) {
          next[id] = { url, file: null, extracting: false, error: null };
        }
      }
      return next;
    });
  }, [initialCharacterPhotos]);

  useEffect(() => {
    if (!initialObjectPhotos) return;
    setObjectPhotos((prev) => {
      const next = { ...prev };
      for (const [id, url] of Object.entries(initialObjectPhotos)) {
        if (!url) continue;
        if (!next[id] || (!next[id].file && next[id].url !== url)) {
          next[id] = { url, file: null, extracting: false, error: null };
        }
      }
      return next;
    });
  }, [initialObjectPhotos]);

  useEffect(() => {
    if (!initialLocationPhotos) return;
    setLocationPhotos((prev) => {
      const next = { ...prev };
      for (const [id, url] of Object.entries(initialLocationPhotos)) {
        if (!url) continue;
        if (!next[id] || (!next[id].file && next[id].url !== url)) {
          next[id] = { url, file: null, extracting: false, error: null };
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

  async function onPickCharacterPhoto(i, file) {
    if (!file) return;
    const charId = config.characters[i]?.id;
    if (!charId) return;
    const localUrl = URL.createObjectURL(file);
    setCharacterPhotos((prev) => ({
      ...prev,
      [charId]: {
        url: localUrl,
        file,
        extracting: true,
        error: null,
      },
    }));
    try {
      const extracted = await api.characterFromPhoto(
        file,
        config.metadata.language || "fr"
      );
      setConfig((c) => {
        const next = structuredClone(c);
        const row = next.characters[i];
        if (!row) return c;
        // Pre-fill empty fields only — never clobber what the user typed.
        if (!row.name && extracted.name) row.name = extracted.name;
        if (!row.physical_description && extracted.physical_description) {
          row.physical_description = extracted.physical_description;
        }
        if (!row.outfit && extracted.outfit) row.outfit = extracted.outfit;
        if (!row.personality && extracted.personality) {
          row.personality = extracted.personality;
        }
        return next;
      });
      if (projectName) {
        try {
          const { url } = await api.setCharacterPhoto(
            projectName,
            charId,
            file
          );
          setCharacterPhotos((prev) => ({
            ...prev,
            [charId]: {
              url: url || localUrl,
              file: null,
              extracting: false,
              error: null,
            },
          }));
          return;
        } catch (uploadErr) {
          setCharacterPhotos((prev) => ({
            ...prev,
            [charId]: {
              ...prev[charId],
              extracting: false,
              error: uploadErr.message || "Échec de l'upload.",
            },
          }));
          return;
        }
      }
      setCharacterPhotos((prev) => ({
        ...prev,
        [charId]: {
          ...prev[charId],
          extracting: false,
          error: null,
        },
      }));
    } catch (e) {
      setCharacterPhotos((prev) => ({
        ...prev,
        [charId]: {
          ...prev[charId],
          extracting: false,
          error: e.message || "Échec de l'extraction.",
        },
      }));
    }
  }

  async function onClearCharacterPhoto(i) {
    const charId = config.characters[i]?.id;
    if (!charId) return;
    setCharacterPhotos((prev) => {
      const out = { ...prev };
      delete out[charId];
      return out;
    });
    if (projectName) {
      try {
        await api.deleteCharacterPhoto(projectName, charId);
      } catch {
        // non-fatal
      }
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

  async function onPickLocationPhoto(i, file) {
    if (!file) return;
    const locId = config.locations[i]?.id;
    if (!locId) return;
    const localUrl = URL.createObjectURL(file);
    setLocationPhotos((prev) => ({
      ...prev,
      [locId]: {
        url: localUrl,
        file,
        extracting: true,
        error: null,
      },
    }));
    try {
      const extracted = await api.locationFromPhoto(
        file,
        config.metadata.language || "fr"
      );
      setConfig((c) => {
        const next = structuredClone(c);
        const row = next.locations[i];
        if (!row) return c;
        if (!row.name && extracted.name) row.name = extracted.name;
        if (!row.description && extracted.description) {
          row.description = extracted.description;
        }
        return next;
      });
      if (projectName) {
        try {
          const { url } = await api.setLocationPhoto(projectName, locId, file);
          setLocationPhotos((prev) => ({
            ...prev,
            [locId]: {
              url: url || localUrl,
              file: null,
              extracting: false,
              error: null,
            },
          }));
          return;
        } catch (uploadErr) {
          setLocationPhotos((prev) => ({
            ...prev,
            [locId]: {
              ...prev[locId],
              extracting: false,
              error: uploadErr.message || "Échec de l'upload.",
            },
          }));
          return;
        }
      }
      setLocationPhotos((prev) => ({
        ...prev,
        [locId]: {
          ...prev[locId],
          extracting: false,
          error: null,
        },
      }));
    } catch (e) {
      setLocationPhotos((prev) => ({
        ...prev,
        [locId]: {
          ...prev[locId],
          extracting: false,
          error: e.message || "Échec de l'extraction.",
        },
      }));
    }
  }

  async function onClearLocationPhoto(i) {
    const locId = config.locations[i]?.id;
    if (!locId) return;
    setLocationPhotos((prev) => {
      const out = { ...prev };
      delete out[locId];
      return out;
    });
    if (projectName) {
      try {
        await api.deleteLocationPhoto(projectName, locId);
      } catch {
        // non-fatal
      }
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

  async function onPickObjectPhoto(i, file) {
    if (!file) return;
    const objId = config.objects[i]?.id;
    if (!objId) return;
    const localUrl = URL.createObjectURL(file);
    setObjectPhotos((prev) => ({
      ...prev,
      [objId]: {
        url: localUrl,
        file,
        extracting: true,
        error: null,
      },
    }));
    try {
      const extracted = await api.objectFromPhoto(
        file,
        config.metadata.language || "fr"
      );
      setConfig((c) => {
        const next = structuredClone(c);
        const row = next.objects[i];
        if (!row) return c;
        if (!row.name && extracted.name) row.name = extracted.name;
        if (!row.description && extracted.description) {
          row.description = extracted.description;
        }
        return next;
      });
      if (projectName) {
        try {
          const { url } = await api.setObjectPhoto(projectName, objId, file);
          setObjectPhotos((prev) => ({
            ...prev,
            [objId]: {
              url: url || localUrl,
              file: null,
              extracting: false,
              error: null,
            },
          }));
          return;
        } catch (uploadErr) {
          setObjectPhotos((prev) => ({
            ...prev,
            [objId]: {
              ...prev[objId],
              extracting: false,
              error: uploadErr.message || "Échec de l'upload.",
            },
          }));
          return;
        }
      }
      setObjectPhotos((prev) => ({
        ...prev,
        [objId]: {
          ...prev[objId],
          extracting: false,
          error: null,
        },
      }));
    } catch (e) {
      setObjectPhotos((prev) => ({
        ...prev,
        [objId]: {
          ...prev[objId],
          extracting: false,
          error: e.message || "Échec de l'extraction.",
        },
      }));
    }
  }

  async function onClearObjectPhoto(i) {
    const objId = config.objects[i]?.id;
    if (!objId) return;
    setObjectPhotos((prev) => {
      const out = { ...prev };
      delete out[objId];
      return out;
    });
    if (projectName) {
      try {
        await api.deleteObjectPhoto(projectName, objId);
      } catch {
        // non-fatal
      }
    }
  }

  function prepareConfig() {
    const out = structuredClone(config);
    const slugSource = out.display_name || out.metadata.title || "projet";
    if (isNew && !out.project) {
      out.project = slugSource
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 60) || "projet";
    }
    out.display_name = out.display_name?.trim() || null;
    out.structure.page_count = Number(out.structure.page_count);
    out.structure.panels_per_page_avg = Number(out.structure.panels_per_page_avg);
    out.structure.panels_per_page_range = [
      Number(out.structure.panels_per_page_range[0]),
      Number(out.structure.panels_per_page_range[1]),
    ];
    out.generation_options.script_model.temperature = Number(
      out.generation_options.script_model.temperature
    );
    out.generation_options.upscale.target_megapixels = Number(
      out.generation_options.upscale.target_megapixels
    );
    out.generation_options.upscale.scale_factor = Number(
      out.generation_options.upscale.scale_factor
    );
    out.generation_options.upscale.output_quality = Number(
      out.generation_options.upscale.output_quality
    );
    return out;
  }

  async function maybeUploadStyleRef(out) {
    if (!styleRefFile) return;
    const projName = projectName || out.project;
    if (!projName) return;
    try { await api.setStyleReference(projName, styleRefFile); } catch { /* non-fatal */ }
  }

  async function maybeUploadPendingCharacterPhotos(out) {
    const projName = projectName || out.project;
    if (!projName) return;
    const updates = [];
    for (const c of out.characters || []) {
      const slot = characterPhotos[c.id];
      if (slot?.file) {
        updates.push(
          api.setCharacterPhoto(projName, c.id, slot.file)
            .then(({ url }) => [c.id, url])
            .catch(() => [c.id, null])
        );
      }
    }
    if (!updates.length) return;
    const results = await Promise.all(updates);
    setCharacterPhotos((prev) => {
      const next = { ...prev };
      for (const [id, url] of results) {
        if (!next[id]) continue;
        if (url) {
          next[id] = { url, file: null, extracting: false, error: null };
        }
      }
      return next;
    });
  }

  async function maybeUploadPendingLocationPhotos(out) {
    const projName = projectName || out.project;
    if (!projName) return;
    const updates = [];
    for (const l of out.locations || []) {
      const slot = locationPhotos[l.id];
      if (slot?.file) {
        updates.push(
          api.setLocationPhoto(projName, l.id, slot.file)
            .then(({ url }) => [l.id, url])
            .catch(() => [l.id, null])
        );
      }
    }
    if (!updates.length) return;
    const results = await Promise.all(updates);
    setLocationPhotos((prev) => {
      const next = { ...prev };
      for (const [id, url] of results) {
        if (!next[id]) continue;
        if (url) {
          next[id] = { url, file: null, extracting: false, error: null };
        }
      }
      return next;
    });
  }

  async function maybeUploadPendingObjectPhotos(out) {
    const projName = projectName || out.project;
    if (!projName) return;
    const updates = [];
    for (const o of out.objects || []) {
      const slot = objectPhotos[o.id];
      if (slot?.file) {
        updates.push(
          api.setObjectPhoto(projName, o.id, slot.file)
            .then(({ url }) => [o.id, url])
            .catch(() => [o.id, null])
        );
      }
    }
    if (!updates.length) return;
    const results = await Promise.all(updates);
    setObjectPhotos((prev) => {
      const next = { ...prev };
      for (const [id, url] of results) {
        if (!next[id]) continue;
        if (url) {
          next[id] = { url, file: null, extracting: false, error: null };
        }
      }
      return next;
    });
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
      setError(e.message);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApplyStyleOnly() {
    if (!onApplyStyleOnly) return;
    if (!window.confirm(
      "Le style va remplacer celui du projet. Le scénario (textes, dialogues, " +
      "personnages, planches) reste intact, mais les images de référence et " +
      "planches composées seront supprimées pour pouvoir être régénérées avec " +
      "le nouveau style.\n\nContinuer ?"
    )) return;
    setError(null);
    setApplyingStyleOnly(true);
    try {
      const out = prepareConfig();
      await maybeUploadStyleRef(out);
      await onApplyStyleOnly(out);
    } catch (e) {
      setError(e.message);
    } finally {
      setApplyingStyleOnly(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <Section title="Identité du projet">
        <Field
          label="Nom du projet (interface)"
          hint="Optionnel — sert uniquement à retrouver le projet dans la liste. N'apparaît jamais dans la BD générée. Si vide, le titre de la BD est affiché."
        >
          <input
            className="input"
            value={config.display_name || ""}
            onChange={(e) => set("display_name", e.target.value)}
            placeholder="ex. Brouillon — version courte"
          />
        </Field>
        {isNew && (
          <Field label="Identifiant du projet (slug)" hint="Optionnel — déduit du nom du projet ou du titre si vide. Lettres, chiffres et underscores.">
            <input
              className="input"
              value={config.project}
              onChange={(e) => set("project", e.target.value.replace(/\s+/g, "_"))}
              placeholder="ex. mon_super_projet"
            />
          </Field>
        )}
        <Grid cols={2}>
          <Field label="Titre de la BD" hint="Apparaît sur la couverture et dans le contenu généré.">
            <input
              className="input"
              value={config.metadata.title}
              onChange={(e) => set("metadata.title", e.target.value)}
              required
            />
          </Field>
          <Field label="Auteur·rice">
            <input
              className="input"
              value={config.metadata.author}
              onChange={(e) => set("metadata.author", e.target.value)}
              required
            />
          </Field>
          <Field label="Langue (ISO)">
            <input
              className="input"
              value={config.metadata.language}
              onChange={(e) => set("metadata.language", e.target.value)}
            />
          </Field>
        </Grid>
      </Section>

      <Section title="Histoire">
        <Field label="Synopsis" hint="Présentez l'histoire en quelques phrases.">
          <textarea
            className="textarea min-h-[7rem]"
            value={config.story.synopsis}
            onChange={(e) => set("story.synopsis", e.target.value)}
            required
          />
        </Field>
        <Grid cols={2}>
          <Field label="Genre">
            <input
              className="input"
              value={config.story.genre || ""}
              onChange={(e) => set("story.genre", e.target.value)}
              placeholder="ex. mystère, drame familial"
            />
          </Field>
          <Field label="Ton">
            <input
              className="input"
              value={config.story.tone || ""}
              onChange={(e) => set("story.tone", e.target.value)}
              placeholder="ex. contemplatif, mélancolique"
            />
          </Field>
          <Field label="Cadre / époque">
            <input
              className="input"
              value={config.story.setting || ""}
              onChange={(e) => set("story.setting", e.target.value)}
              placeholder="ex. Bretagne, automne 1987"
            />
          </Field>
          <Field label="Public visé">
            <input
              className="input"
              value={config.story.target_audience || ""}
              onChange={(e) => set("story.target_audience", e.target.value)}
              placeholder="ex. ado-adulte"
            />
          </Field>
        </Grid>
      </Section>

      <Section
        title="Style visuel"
        action={
          <button
            type="button"
            className="btn btn-secondary text-sm inline-flex items-center gap-2"
            onClick={() => setStyleFromImageOpen(true)}
          >
            <FaPalette aria-hidden /> Style depuis une image
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
        title="Casting"
        intro="Personnages, décors et objets — descriptions, photos optionnelles et images de référence. Importez ou exportez un sous-ensemble en .bdrefs pour le réutiliser dans une autre BD (ex. Tome 2)."
        action={
          projectName ? (
            <ReferencesBundlePanel
              projectName={projectName}
              onImported={onReferencesImported}
            />
          ) : null
        }
      >
        <Subsection
          title="Personnages"
          action={
            <button
              type="button"
              className="btn btn-secondary text-sm inline-flex items-center gap-2"
              onClick={addCharacter}
            >
              <FaPlus aria-hidden /> Ajouter
            </button>
          }
        >
          <Toggle
            label="Autoriser l'IA à inventer des personnages supplémentaires si l'histoire en a besoin"
            value={config.structure.allow_extra_characters}
            onChange={(v) => set("structure.allow_extra_characters", v)}
          />
          {config.characters.length === 0 && (
            <p className="text-sm text-[var(--color-mute)]">
              Aucun personnage défini pour l'instant.
              {config.structure.allow_extra_characters
                ? " L'IA en proposera selon les besoins du scénario."
                : ""}
            </p>
          )}
          <div className="space-y-4">
            {config.characters.map((c, i) => (
              <div key={i} className="card p-4 bg-[var(--color-paper-soft)]/40">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[var(--color-mute)] uppercase tracking-wide">
                    Personnage {i + 1}
                  </span>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
                    onClick={() => removeCharacter(i)}
                    title="Supprimer ce personnage"
                  >
                    <FaTrash aria-hidden /> Supprimer
                  </button>
                </div>
                <CharacterPhotoField
                  slot={characterPhotos[c.id]}
                  onPick={(file) => onPickCharacterPhoto(i, file)}
                  onClear={() => onClearCharacterPhoto(i)}
                />
                <ReferenceImagePreview
                  url={initialReferenceImages?.characters?.[c.id]}
                  label={`Référence — ${c.name || c.id}`}
                />
                <Grid cols={2}>
                  <Field label="Identifiant" hint="Référence interne (lettres + underscore)">
                    <input
                      className="input"
                      value={c.id}
                      onChange={(e) => updateCharacter(i, "id", e.target.value.replace(/\s+/g, "_"))}
                    />
                  </Field>
                  <Field label="Nom">
                    <input
                      className="input"
                      value={c.name}
                      onChange={(e) => updateCharacter(i, "name", e.target.value)}
                      required
                    />
                  </Field>
                  <Field label="Rôle">
                    <input
                      className="input"
                      value={c.role || ""}
                      onChange={(e) => updateCharacter(i, "role", e.target.value)}
                      placeholder="ex. protagoniste"
                    />
                  </Field>
                  <Field label="Personnalité">
                    <input
                      className="input"
                      value={c.personality || ""}
                      onChange={(e) => updateCharacter(i, "personality", e.target.value)}
                    />
                  </Field>
                </Grid>
                <Field label="Description physique">
                  <textarea
                    className="textarea"
                    value={c.physical_description}
                    onChange={(e) => updateCharacter(i, "physical_description", e.target.value)}
                    required
                  />
                </Field>
                <Field label="Tenue / accessoires">
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
          title="Décors"
          action={
            <button
              type="button"
              className="btn btn-secondary text-sm inline-flex items-center gap-2"
              onClick={addLocation}
            >
              <FaPlus aria-hidden /> Ajouter
            </button>
          }
        >
          <Toggle
            label="Autoriser l'IA à inventer des décors supplémentaires si l'histoire en a besoin"
            value={config.structure.allow_extra_locations}
            onChange={(v) => set("structure.allow_extra_locations", v)}
          />
          {config.locations.length === 0 && (
            <p className="text-sm text-[var(--color-mute)]">
              Aucun décor défini pour l'instant.
              {config.structure.allow_extra_locations
                ? " L'IA en inventera selon les besoins du scénario."
                : " ⚠️ Aucun décor disponible — l'IA ne pourra pas situer les scènes."}
            </p>
          )}
          <div className="space-y-4">
            {config.locations.map((l, i) => (
              <div key={i} className="card p-4 bg-[var(--color-paper-soft)]/40">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[var(--color-mute)] uppercase tracking-wide">
                    Décor {i + 1}
                  </span>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
                    onClick={() => removeLocation(i)}
                    title="Supprimer ce décor"
                  >
                    <FaTrash aria-hidden /> Supprimer
                  </button>
                </div>
                <LocationPhotoField
                  slot={locationPhotos[l.id]}
                  onPick={(file) => onPickLocationPhoto(i, file)}
                  onClear={() => onClearLocationPhoto(i)}
                />
                <ReferenceImagePreview
                  url={initialReferenceImages?.locations?.[l.id]}
                  label={`Référence — ${l.name || l.id}`}
                />
                <Grid cols={2}>
                  <Field label="Identifiant" hint="Référence interne (lettres + underscore)">
                    <input
                      className="input"
                      value={l.id}
                      onChange={(e) => updateLocation(i, "id", e.target.value.replace(/\s+/g, "_"))}
                    />
                  </Field>
                  <Field label="Nom">
                    <input
                      className="input"
                      value={l.name}
                      onChange={(e) => updateLocation(i, "name", e.target.value)}
                      required
                    />
                  </Field>
                </Grid>
                <Field label="Description" hint="Décrivez le lieu : éléments visuels, ambiance, époque…">
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
          title="Objets / produits / références"
          action={
            <button
              type="button"
              className="btn btn-secondary text-sm inline-flex items-center gap-2"
              onClick={addObject}
            >
              <FaPlus aria-hidden /> Ajouter
            </button>
          }
        >
          <p className="text-sm text-[var(--color-mute)]">
            Optionnel. Ajoutez ici un livre, un produit, un objet symbolique qui doit
            revenir dans l'histoire. Une photo (optionnelle) servira de guide pour en
            dessiner une version caricaturée dans le style de la BD.
          </p>
          <Toggle
            label="Autoriser l'IA à inventer des objets supplémentaires si l'histoire en a besoin"
            value={config.structure.allow_extra_objects}
            onChange={(v) => set("structure.allow_extra_objects", v)}
          />
          {config.objects.length === 0 && (
            <p className="text-sm text-[var(--color-mute)]">
              Aucun objet défini pour l'instant.
              {config.structure.allow_extra_objects
                ? " L'IA n'en inventera qu'à la marge."
                : ""}
            </p>
          )}
          <div className="space-y-4">
            {config.objects.map((o, i) => (
              <div key={i} className="card p-4 bg-[var(--color-paper-soft)]/40">
                <div className="flex items-center justify-between mb-3">
                  <span className="text-xs text-[var(--color-mute)] uppercase tracking-wide">
                    Objet {i + 1}
                  </span>
                  <button
                    type="button"
                    className="btn btn-ghost text-xs inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
                    onClick={() => removeObject(i)}
                    title="Supprimer cet objet"
                  >
                    <FaTrash aria-hidden /> Supprimer
                  </button>
                </div>
                <ObjectPhotoField
                  slot={objectPhotos[o.id]}
                  onPick={(file) => onPickObjectPhoto(i, file)}
                  onClear={() => onClearObjectPhoto(i)}
                />
                <ReferenceImagePreview
                  url={initialReferenceImages?.objects?.[o.id]}
                  label={`Référence — ${o.name || o.id}`}
                />
                <Grid cols={2}>
                  <Field label="Identifiant" hint="Référence interne (lettres + underscore)">
                    <input
                      className="input"
                      value={o.id}
                      onChange={(e) => updateObject(i, "id", e.target.value.replace(/\s+/g, "_"))}
                    />
                  </Field>
                  <Field label="Nom">
                    <input
                      className="input"
                      value={o.name}
                      onChange={(e) => updateObject(i, "name", e.target.value)}
                      required
                    />
                  </Field>
                </Grid>
                <Field label="Description" hint="Décrivez l'objet et son rôle dans l'histoire.">
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

      <Section title="Structure">
        <Grid cols={3}>
          <Field label="Nombre de planches">
            <input
              type="number"
              min={1}
              className="input"
              value={config.structure.page_count}
              onChange={(e) => set("structure.page_count", e.target.value)}
            />
          </Field>
          <Field label="Cases par planche (moyenne)">
            <input
              type="number"
              min={1}
              max={12}
              className="input"
              value={config.structure.panels_per_page_avg}
              onChange={(e) => set("structure.panels_per_page_avg", e.target.value)}
            />
          </Field>
          <Field label="Cases / planche (min – max)">
            <div className="flex gap-2">
              <input
                type="number"
                min={1}
                className="input"
                value={config.structure.panels_per_page_range[0]}
                onChange={(e) =>
                  set("structure.panels_per_page_range", [
                    e.target.value,
                    config.structure.panels_per_page_range[1],
                  ])
                }
              />
              <input
                type="number"
                min={1}
                className="input"
                value={config.structure.panels_per_page_range[1]}
                onChange={(e) =>
                  set("structure.panels_per_page_range", [
                    config.structure.panels_per_page_range[0],
                    e.target.value,
                  ])
                }
              />
            </div>
          </Field>
        </Grid>
        <Grid cols={2}>
          <Toggle
            label="Inclure une couverture"
            value={config.structure.include_cover}
            onChange={(v) => set("structure.include_cover", v)}
          />
          <Toggle
            label="Inclure une 4ᵉ de couverture"
            value={config.structure.include_back_cover}
            onChange={(v) => set("structure.include_back_cover", v)}
          />
        </Grid>
        <Field label="Rythme narratif">
          <input
            className="input"
            value={config.structure.narrative_pacing || ""}
            onChange={(e) => set("structure.narrative_pacing", e.target.value)}
            placeholder="ex. lent au début, accélération vers la révélation finale"
          />
        </Field>
      </Section>

      <Section title="Modèles de génération">
        <Grid cols={2}>
          <Field label="LLM scénario — fournisseur">
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
          <Field label="LLM scénario — modèle">
            <ModelSelector
              provider={config.generation_options.script_model.provider}
              model={config.generation_options.script_model.model}
              optionsByProvider={SCRIPT_MODEL_OPTIONS}
              onChange={(value) => set("generation_options.script_model.model", value)}
            />
          </Field>
          <Field label="Image — fournisseur">
            <select
              className="select"
              value={config.generation_options.image_model.provider}
              onChange={(e) => setModelProvider("image_model", e.target.value, IMAGE_MODEL_OPTIONS)}
            >
              <option value="openai">OpenAI</option>
            </select>
          </Field>
          <Field label="Image — modèle">
            <ModelSelector
              provider={config.generation_options.image_model.provider}
              model={config.generation_options.image_model.model}
              optionsByProvider={IMAGE_MODEL_OPTIONS}
              onChange={(value) => set("generation_options.image_model.model", value)}
            />
          </Field>
          <Field label="Qualité image">
            <select
              className="select"
              value={config.generation_options.image_model.quality}
              onChange={(e) => set("generation_options.image_model.quality", e.target.value)}
            >
              <option value="low">low</option>
              <option value="medium">medium</option>
              <option value="high">high</option>
            </select>
          </Field>
          <Field label="Format de sortie">
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

        <Subsection title="Upscale (Pruna via Replicate)">
          <Grid cols={2}>
            <Toggle
              label="Activer l'étape d'upscale"
              value={config.generation_options.upscale.enabled}
              onChange={(v) => set("generation_options.upscale.enabled", v)}
            />
            <Field
              label="Mode d'agrandissement"
              hint="Choisissez une cible en mégapixels ou un facteur multiplicatif."
            >
              <select
                className="select"
                value={config.generation_options.upscale.mode}
                onChange={(e) => set("generation_options.upscale.mode", e.target.value)}
              >
                <option value="target">Taille cible (MP)</option>
                <option value="factor">Facteur ×N</option>
              </select>
            </Field>
          </Grid>

          <Grid cols={2}>
            <Field
              label="Mégapixels cibles"
              hint="Utilisé en mode “taille cible”. Exemple : 4 MP."
            >
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
              label="Facteur d'agrandissement"
              hint="Utilisé en mode “facteur”. Exemple : 2 = largeur et hauteur ×2."
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
            <Field label="Format de sortie upscalé">
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
            <Field
              label="Qualité fichier"
              hint="Appliquée aux formats JPEG et WebP. Ignorée pour PNG."
            >
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
            Utilise le modèle Pruna P-Image-Upscale via l'API Replicate.
            Coût : ~$0.005/image (1-4 MP) ou ~$0.01/image (5-8 MP).
            Nécessite <code>REPLICATE_API_TOKEN</code> dans le <code>.env</code> du serveur.
          </p>
        </Subsection>
      </Section>

      {error && (
        <div className="card p-4 bg-[var(--color-rose-100)] border-[var(--color-rose-300)] text-[var(--color-rose-500)] text-sm">
          {error}
        </div>
      )}

      <div className="flex flex-wrap justify-end gap-3">
        {onCancel && (
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Annuler
          </button>
        )}
        {onApplyStyleOnly && (
          <button
            type="button"
            className="btn btn-secondary inline-flex items-center gap-2"
            onClick={handleApplyStyleOnly}
            disabled={submitting || applyingStyleOnly}
            title="Mettre à jour le style et réinitialiser les images sans toucher au scénario."
          >
            <FaPalette aria-hidden />
            {applyingStyleOnly ? "Application…" : applyStyleOnlyLabel}
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={submitting || applyingStyleOnly}>
          {submitting ? "Enregistrement…" : submitLabel}
        </button>
      </div>

      {styleFromImageOpen && (
        <StyleFromImageDialog
          language={config.metadata.language || "fr"}
          onClose={() => setStyleFromImageOpen(false)}
          onApply={({ style, characters, locations, file }) => {
            setStyleRefFile(file || null);
            if (file) {
              setStyleRefLocalPreview(URL.createObjectURL(file));
              if (projectName) {
                api.setStyleReference(projectName, file).then(({ url }) => {
                  if (url) setStyleRefUrl(url);
                }).catch(() => {});
              }
            }
            setConfig((c) => {
              const next = {
                ...c,
                style: {
                  ...c.style,
                  art_style: style.art_style ?? c.style.art_style,
                  color_palette:
                    style.color_palette ?? c.style.color_palette,
                  line_work: style.line_work ?? c.style.line_work,
                  mood: style.mood ?? c.style.mood,
                  panel_borders:
                    style.panel_borders ?? c.style.panel_borders,
                  speech_bubbles:
                    style.speech_bubbles ?? c.style.speech_bubbles,
                  character_rendering:
                    style.character_rendering ?? c.style.character_rendering,
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

function Section({ title, intro, action, children }) {
  return (
    <div className="card p-6">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div className="flex-1 min-w-[12rem]">
          <h3 className="text-base font-semibold">{title}</h3>
          {intro && (
            <p className="text-sm text-[var(--color-mute)] mt-1">{intro}</p>
          )}
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
        <h4 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-ink-soft)]">
          {title}
        </h4>
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

function ModelSelector({ provider, model, optionsByProvider, onChange }) {
  const options = optionsByProvider[provider] || [];
  const known = options.some((option) => option.value === model);
  const selectValue = known ? model : "__custom__";

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
        <option value="__custom__">Modele personnalise...</option>
      </select>
      {selectValue === "__custom__" && (
        <input
          className="input"
          value={model}
          onChange={(e) => onChange(e.target.value)}
          placeholder="Nom exact du modele"
        />
      )}
    </div>
  );
}

function Grid({ cols = 2, children }) {
  return (
    <div className={`grid grid-cols-1 md:grid-cols-${cols} gap-4`}>{children}</div>
  );
}

function ReferenceImagePreview({ url, label }) {
  if (!url) return null;
  return (
    <div className="mb-4 flex items-start gap-4">
      <div className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center shrink-0">
        <img src={url} alt={label || "Image de référence"} className="w-full h-full object-cover" />
      </div>
      <div className="flex-1 min-w-0">
        <label className="label">Image de référence générée</label>
        <p className="text-xs text-[var(--color-mute)]">
          Image utilisée comme guide visuel lors de la composition des planches.
          Pour la régénérer, modifiez la fiche puis relancez l'étape Références.
        </p>
      </div>
    </div>
  );
}

function CharacterPhotoField({ slot, onPick, onClear }) {
  const inputId = `char-photo-${Math.random().toString(36).slice(2, 8)}`;
  const url = slot?.url || null;
  const extracting = slot?.extracting || false;
  const error = slot?.error || null;
  return (
    <div className="mb-4 flex items-start gap-4">
      <div className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center text-xs text-[var(--color-mute)] shrink-0">
        {url ? (
          <img src={url} alt="" className="w-full h-full object-cover" />
        ) : (
          <span>Aucune photo</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <label className="label">Photo de référence (optionnel)</label>
        <p className="text-xs text-[var(--color-mute)] mb-2">
          Si vous ajoutez une photo, l'IA en extrait les caractéristiques pour
          pré-remplir la fiche puis l'utilise comme guide de ressemblance lors
          de la génération de la référence (effet caricature). Le style défini
          reste prioritaire sur la photo.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label
            htmlFor={inputId}
            className="btn btn-secondary text-sm cursor-pointer inline-flex items-center gap-2"
          >
            <FaUpload aria-hidden />
            {url ? "Remplacer" : "Choisir une photo"}
          </label>
          <input
            id={inputId}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) onPick(f);
            }}
          />
          {url && (
            <button
              type="button"
              className="btn btn-ghost text-sm inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
              onClick={onClear}
              title="Retirer la photo"
            >
              <FaTrash aria-hidden /> Retirer
            </button>
          )}
          {extracting && (
            <span className="text-xs text-[var(--color-mute)]">
              Analyse de la photo…
            </span>
          )}
        </div>
        {error && (
          <p className="text-xs text-[var(--color-rose-500)] mt-1">{error}</p>
        )}
      </div>
    </div>
  );
}


function LocationPhotoField({ slot, onPick, onClear }) {
  const inputId = `loc-photo-${Math.random().toString(36).slice(2, 8)}`;
  const url = slot?.url || null;
  const extracting = slot?.extracting || false;
  const error = slot?.error || null;
  return (
    <div className="mb-4 flex items-start gap-4">
      <div className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center text-xs text-[var(--color-mute)] shrink-0">
        {url ? (
          <img src={url} alt="" className="w-full h-full object-cover" />
        ) : (
          <span>Aucune photo</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <label className="label">Photo de référence (optionnel)</label>
        <p className="text-xs text-[var(--color-mute)] mb-2">
          Si vous ajoutez une photo du lieu, l'IA en extrait nom + description
          pour pré-remplir la fiche, puis l'utilise comme guide visuel pour
          dessiner le décor (architecture, ambiance) dans le style de la BD.
          Aucun personnage ne sera repris depuis la photo.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label
            htmlFor={inputId}
            className="btn btn-secondary text-sm cursor-pointer inline-flex items-center gap-2"
          >
            <FaUpload aria-hidden />
            {url ? "Remplacer" : "Choisir une photo"}
          </label>
          <input
            id={inputId}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) onPick(f);
            }}
          />
          {url && (
            <button
              type="button"
              className="btn btn-ghost text-sm inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
              onClick={onClear}
              title="Retirer la photo"
            >
              <FaTrash aria-hidden /> Retirer
            </button>
          )}
          {extracting && (
            <span className="text-xs text-[var(--color-mute)]">
              Analyse de la photo…
            </span>
          )}
        </div>
        {error && (
          <p className="text-xs text-[var(--color-rose-500)] mt-1">{error}</p>
        )}
      </div>
    </div>
  );
}


function ObjectPhotoField({ slot, onPick, onClear }) {
  const inputId = `obj-photo-${Math.random().toString(36).slice(2, 8)}`;
  const url = slot?.url || null;
  const extracting = slot?.extracting || false;
  const error = slot?.error || null;
  return (
    <div className="mb-4 flex items-start gap-4">
      <div className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center text-xs text-[var(--color-mute)] shrink-0">
        {url ? (
          <img src={url} alt="" className="w-full h-full object-cover" />
        ) : (
          <span>Aucune photo</span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <label className="label">Photo de référence (optionnel)</label>
        <p className="text-xs text-[var(--color-mute)] mb-2">
          Si vous ajoutez une photo, l'IA en extrait nom + description pour
          pré-remplir la fiche, puis l'utilise comme guide visuel pour produire
          une version caricaturée de l'objet dans le style de la BD.
        </p>
        <div className="flex flex-wrap items-center gap-2">
          <label
            htmlFor={inputId}
            className="btn btn-secondary text-sm cursor-pointer inline-flex items-center gap-2"
          >
            <FaUpload aria-hidden />
            {url ? "Remplacer" : "Choisir une photo"}
          </label>
          <input
            id={inputId}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) onPick(f);
            }}
          />
          {url && (
            <button
              type="button"
              className="btn btn-ghost text-sm inline-flex items-center gap-1.5 hover:text-[var(--color-rose-500)]"
              onClick={onClear}
              title="Retirer la photo"
            >
              <FaTrash aria-hidden /> Retirer
            </button>
          )}
          {extracting && (
            <span className="text-xs text-[var(--color-mute)]">
              Analyse de la photo…
            </span>
          )}
        </div>
        {error && (
          <p className="text-xs text-[var(--color-rose-500)] mt-1">{error}</p>
        )}
      </div>
    </div>
  );
}


function StyleReferenceCard({ url, onPickImage, config, set }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="flex items-start gap-4">
      <div
        className="w-24 h-24 rounded-lg overflow-hidden bg-[var(--color-paper)] border border-[var(--color-line)] flex items-center justify-center text-xs text-[var(--color-mute)] shrink-0 cursor-pointer"
        onClick={onPickImage}
        title={url ? "Changer l'image de style" : "Choisir une image de style"}
      >
        {url ? (
          <img src={url} alt="Référence de style" className="w-full h-full object-cover" />
        ) : (
          <span className="text-center px-1">Aucune image</span>
        )}
      </div>
      <div className="flex-1 min-w-0 space-y-3">
        <div>
          <label className="label">Style artistique</label>
          <input
            className="input"
            value={config.style.art_style}
            onChange={(e) => set("style.art_style", e.target.value)}
            placeholder="ex. ligne claire, aquarelle douce"
            required
          />
          <p className="text-xs text-[var(--color-mute)] mt-1">
            Évitez de citer des artistes ou marques.
          </p>
        </div>
        <button
          type="button"
          className="text-xs text-[var(--color-mute)] hover:text-[var(--color-ink)] inline-flex items-center gap-1 transition-colors"
          onClick={() => setExpanded((v) => !v)}
        >
          <FaChevronDown
            aria-hidden
            className={"transition-transform " + (expanded ? "rotate-180" : "")}
          />
          {expanded ? "Masquer les détails" : "Détails du style"}
        </button>
        {expanded && (
          <div className="space-y-3">
            <Grid cols={3}>
              <Field label="Palette de couleurs">
                <input
                  className="input"
                  value={config.style.color_palette || ""}
                  onChange={(e) => set("style.color_palette", e.target.value)}
                />
              </Field>
              <Field label="Encrage / traits">
                <input
                  className="input"
                  value={config.style.line_work || ""}
                  onChange={(e) => set("style.line_work", e.target.value)}
                />
              </Field>
              <Field label="Atmosphère">
                <input
                  className="input"
                  value={config.style.mood || ""}
                  onChange={(e) => set("style.mood", e.target.value)}
                />
              </Field>
            </Grid>
            <Grid cols={3}>
              <Field label="Tour des cases">
                <input
                  className="input"
                  value={config.style.panel_borders || ""}
                  onChange={(e) => set("style.panel_borders", e.target.value)}
                  placeholder="ex. cadre noir épais légèrement irrégulier"
                />
              </Field>
              <Field label="Dessin des bulles">
                <input
                  className="input"
                  value={config.style.speech_bubbles || ""}
                  onChange={(e) => set("style.speech_bubbles", e.target.value)}
                  placeholder="ex. bulles blanches contour fin et rond"
                />
              </Field>
              <Field label="Dessin des personnages">
                <input
                  className="input"
                  value={config.style.character_rendering || ""}
                  onChange={(e) => set("style.character_rendering", e.target.value)}
                  placeholder="ex. visages ronds, yeux en points, peu d'ombres"
                />
              </Field>
            </Grid>
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
        <input
          type="checkbox"
          className="sr-only"
          checked={value}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span
          className={
            "absolute top-0.5 w-5 h-5 bg-white rounded-full shadow transition " +
            (value ? "left-[18px]" : "left-0.5")
          }
        />
      </span>
      <span className="text-sm">{label}</span>
    </label>
  );
}
