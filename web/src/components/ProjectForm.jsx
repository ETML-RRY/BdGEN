import { useState, useEffect } from "react";
import { api } from "../api.js";
import StyleFromImageDialog from "./StyleFromImageDialog.jsx";

export const DEFAULT_CONFIG = {
  project: "",
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
  },
  characters: [],
  locations: [],
  structure: {
    page_count: 6,
    panels_per_page_avg: 4,
    panels_per_page_range: [2, 6],
    include_cover: true,
    include_back_cover: true,
    narrative_pacing: "",
    allow_extra_characters: true,
    allow_extra_locations: true,
  },
  generation_options: {
    script_model: {
      provider: "anthropic",
      model: "claude-opus-4-7",
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
    render_dialogs_separately: true,
    output_format: "pdf",
  },
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

function dedupeId(base, used) {
  let id = base;
  let suffix = 2;
  while (used.has(id)) id = `${base}_${suffix++}`;
  used.add(id);
  return id;
}

function normalize(cfg) {
  // Tolerate configs saved before locations / allow_extra_* existed.
  const out = structuredClone(cfg);
  if (!Array.isArray(out.locations)) out.locations = [];
  if (!out.structure) out.structure = {};
  if (typeof out.structure.allow_extra_characters !== "boolean") {
    out.structure.allow_extra_characters = true;
  }
  if (typeof out.structure.allow_extra_locations !== "boolean") {
    out.structure.allow_extra_locations = true;
  }
  return out;
}

export default function ProjectForm({
  initial,
  isNew = false,
  projectName = null,
  onSubmit,
  onCancel,
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

  useEffect(() => {
    if (initial) setConfig(normalize(initial));
  }, [initial]);

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

  function addCharacter() {
    setConfig((c) => ({
      ...c,
      characters: [...c.characters, blankCharacter(c.characters.length + 1)],
    }));
  }
  function updateCharacter(i, field, value) {
    setConfig((c) => {
      const next = structuredClone(c);
      next.characters[i][field] = value;
      return next;
    });
  }
  function removeCharacter(i) {
    setConfig((c) => {
      const next = structuredClone(c);
      next.characters.splice(i, 1);
      return next;
    });
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
      next.locations[i][field] = value;
      return next;
    });
  }
  function removeLocation(i) {
    setConfig((c) => {
      const next = structuredClone(c);
      next.locations.splice(i, 1);
      return next;
    });
  }

  function prepareConfig() {
    const out = structuredClone(config);
    if (isNew && !out.project) {
      out.project = (out.metadata.title || "projet")
        .toLowerCase()
        .normalize("NFD")
        .replace(/[̀-ͯ]/g, "")
        .replace(/[^a-z0-9]+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 60) || "projet";
    }
    out.structure.page_count = Number(out.structure.page_count);
    out.structure.panels_per_page_avg = Number(out.structure.panels_per_page_avg);
    out.structure.panels_per_page_range = [
      Number(out.structure.panels_per_page_range[0]),
      Number(out.structure.panels_per_page_range[1]),
    ];
    out.generation_options.script_model.temperature = Number(
      out.generation_options.script_model.temperature
    );
    return out;
  }

  async function maybeUploadStyleRef(out) {
    if (!styleRefFile) return;
    const projName = projectName || out.project;
    if (!projName) return;
    try { await api.setStyleReference(projName, styleRefFile); } catch { /* non-fatal */ }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const out = prepareConfig();
      await onSubmit(out);
      await maybeUploadStyleRef(out);
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
      "personnages, planches) reste intact, mais les images de référence, " +
      "esquisses et planches composées seront supprimées pour pouvoir être " +
      "régénérées avec le nouveau style.\n\nContinuer ?"
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
        {isNew && (
          <Field label="Identifiant du projet (slug)" hint="Optionnel — déduit du titre si vide. Lettres, chiffres et underscores.">
            <input
              className="input"
              value={config.project}
              onChange={(e) => set("project", e.target.value.replace(/\s+/g, "_"))}
              placeholder="ex. mon_super_projet"
            />
          </Field>
        )}
        <Grid cols={2}>
          <Field label="Titre">
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
            className="btn btn-secondary text-sm"
            onClick={() => setStyleFromImageOpen(true)}
          >
            <span aria-hidden>🖼</span> Inspirez-vous d'une image
          </button>
        }
      >
        <Field label="Style artistique" hint="Évitez de citer des artistes ou marques.">
          <input
            className="input"
            value={config.style.art_style}
            onChange={(e) => set("style.art_style", e.target.value)}
            placeholder="ex. ligne claire, aquarelle douce"
            required
          />
        </Field>
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
      </Section>

      <Section
        title="Personnages"
        action={
          <button type="button" className="btn btn-secondary text-sm" onClick={addCharacter}>
            ＋ Ajouter
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
                  className="btn btn-ghost text-xs"
                  onClick={() => removeCharacter(i)}
                >
                  Supprimer
                </button>
              </div>
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
      </Section>

      <Section
        title="Décors"
        action={
          <button type="button" className="btn btn-secondary text-sm" onClick={addLocation}>
            ＋ Ajouter
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
                  className="btn btn-ghost text-xs"
                  onClick={() => removeLocation(i)}
                >
                  Supprimer
                </button>
              </div>
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
              onChange={(e) => set("generation_options.script_model.provider", e.target.value)}
            >
              <option value="anthropic">Anthropic</option>
              <option value="openai">OpenAI</option>
            </select>
          </Field>
          <Field label="LLM scénario — modèle">
            <input
              className="input"
              value={config.generation_options.script_model.model}
              onChange={(e) => set("generation_options.script_model.model", e.target.value)}
            />
          </Field>
          <Field label="Image — fournisseur">
            <select
              className="select"
              value={config.generation_options.image_model.provider}
              onChange={(e) => set("generation_options.image_model.provider", e.target.value)}
            >
              <option value="openai">OpenAI</option>
            </select>
          </Field>
          <Field label="Image — modèle">
            <input
              className="input"
              value={config.generation_options.image_model.model}
              onChange={(e) => set("generation_options.image_model.model", e.target.value)}
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
            className="btn btn-secondary"
            onClick={handleApplyStyleOnly}
            disabled={submitting || applyingStyleOnly}
            title="Mettre à jour le style et réinitialiser les images sans toucher au scénario."
          >
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
            if (file && projectName) {
              api.setStyleReference(projectName, file).catch(() => {});
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

function Section({ title, action, children }) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-base font-semibold">{title}</h3>
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

function Grid({ cols = 2, children }) {
  return (
    <div className={`grid grid-cols-1 md:grid-cols-${cols} gap-4`}>{children}</div>
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
