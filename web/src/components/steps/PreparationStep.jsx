import { useNavigate, useParams } from "react-router-dom";
import { api } from "../../api.js";
import ProjectForm from "../ProjectForm.jsx";

export default function PreparationStep({ project, onSaved }) {
  const navigate = useNavigate();
  const { name } = useParams();

  if (!project.config) {
    return (
      <div className="card p-6 text-[var(--color-mute)]">
        Pas de configuration enregistrée pour ce projet.
      </div>
    );
  }

  async function onSubmit(config) {
    await api.updateProject(name, config);
    await onSaved();
    navigate(`/projects/${encodeURIComponent(name)}/script`);
  }

  return (
    <ProjectForm
      initial={project.config}
      projectName={name}
      onSubmit={onSubmit}
      submitLabel="Enregistrer & passer à l'écriture"
    />
  );
}
