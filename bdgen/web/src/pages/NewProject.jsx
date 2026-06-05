import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import ProjectForm, { DEFAULT_CONFIG, slugifyProjectName } from "../components/ProjectForm.jsx";
import QuickCreatePanel from "../components/QuickCreatePanel.jsx";

// Merge a quick-create draft onto DEFAULT_CONFIG. Sub-objects
// (metadata/story/style/structure) are shallow-merged so untouched defaults
// (e.g. metadata.language) survive; casting arrays are replaced wholesale.
// generation_options / output_root / project always come from DEFAULT_CONFIG.
function mergeDraft(draft) {
  const merged = structuredClone(DEFAULT_CONFIG);
  for (const key of ["metadata", "story", "style", "structure"]) {
    if (draft[key]) merged[key] = { ...merged[key], ...draft[key] };
  }
  for (const key of ["characters", "locations", "objects"]) {
    if (Array.isArray(draft[key])) merged[key] = draft[key];
  }
  return merged;
}

// Create a project, ensuring a unique slug. The quick path derives the slug
// from the (LLM-invented) title with no chance for the user to resolve a
// collision, so we retry with numeric suffixes when the name already exists.
async function createUniqueProject(config) {
  const base = slugifyProjectName(config.display_name || config.metadata?.title);
  for (let attempt = 1; ; attempt += 1) {
    const project = attempt === 1 ? base : `${base}_${attempt}`;
    try {
      const { name } = await api.createProject({ ...config, project });
      return name;
    } catch (e) {
      if (e.status === 409 && attempt < 50) continue;
      throw e;
    }
  }
}

export default function NewProject() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("quick"); // "quick" | "form"
  const [initialConfig, setInitialConfig] = useState(DEFAULT_CONFIG);
  const [error, setError] = useState(null);

  async function onSubmit(config) {
    const { name } = await api.createProject(config);
    navigate(`/projects/${encodeURIComponent(name)}`);
  }

  // The backend draft already carries an invented title and a chosen style.
  // Save it as a real project straight away so the user lands directly on the
  // detailed form (the project's preparation step), already persisted.
  async function onGenerated(draft) {
    const config = mergeDraft(draft);
    try {
      const name = await createUniqueProject(config);
      navigate(`/projects/${encodeURIComponent(name)}`);
    } catch (e) {
      // Couldn't auto-save: fall back to the manual form with the draft
      // pre-filled so the user can review and create it themselves.
      setError(e.message || "La sauvegarde automatique a échoué.");
      setInitialConfig(config);
      setMode("form");
    }
  }

  function onSkip() {
    setInitialConfig(DEFAULT_CONFIG);
    setMode("form");
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold mb-2">Nouveau projet</h1>
      <p className="text-[var(--color-ink-soft)] mb-6">
        {mode === "quick"
          ? "Partez d'une simple idée : nous créons le projet et pré-remplissons le formulaire pour vous."
          : "Relisez et ajustez les informations ci-dessous. Vous pourrez les affiner à tout moment depuis l'étape « Préparation »."}
      </p>
      {error && (
        <p className="card p-4 mb-6 text-[var(--color-rose-500)]">{error}</p>
      )}
      {mode === "quick" ? (
        <QuickCreatePanel onGenerated={onGenerated} onSkip={onSkip} />
      ) : (
        <ProjectForm
          initial={initialConfig}
          isNew
          onSubmit={onSubmit}
          onCancel={() => navigate("/")}
          submitLabel="Créer le projet"
        />
      )}
    </div>
  );
}
