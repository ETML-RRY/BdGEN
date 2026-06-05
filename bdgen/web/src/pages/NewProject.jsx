import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import ProjectForm, { DEFAULT_CONFIG } from "../components/ProjectForm.jsx";
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

export default function NewProject() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("quick"); // "quick" | "form"
  const [initialConfig, setInitialConfig] = useState(DEFAULT_CONFIG);

  async function onSubmit(config) {
    const { name } = await api.createProject(config);
    navigate(`/projects/${encodeURIComponent(name)}`);
  }

  function onGenerated(draft) {
    setInitialConfig(mergeDraft(draft));
    setMode("form");
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
          ? "Partez d'une simple idée : nous pré-remplissons le formulaire pour vous."
          : "Relisez et ajustez les informations ci-dessous. Vous pourrez les affiner à tout moment depuis l'étape « Préparation »."}
      </p>
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
