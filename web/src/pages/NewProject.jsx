import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import ProjectForm, { DEFAULT_CONFIG } from "../components/ProjectForm.jsx";

export default function NewProject() {
  const navigate = useNavigate();

  async function onSubmit(config) {
    const { name } = await api.createProject(config);
    navigate(`/projects/${encodeURIComponent(name)}`);
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-semibold mb-2">Nouveau projet</h1>
      <p className="text-[var(--color-ink-soft)] mb-6">
        Remplissez les informations de base ci-dessous. Vous pourrez les
        affiner à tout moment depuis l'étape «&nbsp;Préparation&nbsp;».
      </p>
      <ProjectForm
        initial={DEFAULT_CONFIG}
        isNew
        onSubmit={onSubmit}
        onCancel={() => navigate("/")}
        submitLabel="Créer le projet"
      />
    </div>
  );
}
