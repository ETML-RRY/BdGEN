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

  // Surface a "restyle only" path once a script already exists: keep the
  // text intact (characters, locations, panels, dialogs) but swap the visual
  // style and wipe the downstream images so the user can rerun references
  // and compose under the new look.
  const hasScript = Boolean(project.script);

  async function onApplyStyleOnly(config) {
    await api.updateProject(name, config);
    await api.restyleProject(name, config.style);
    await onSaved();
    navigate(`/projects/${encodeURIComponent(name)}/references`);
  }

  return (
    <ProjectForm
      initial={project.config}
      projectName={name}
      initialCharacterPhotos={project.character_photos || {}}
      initialLocationPhotos={project.location_photos || {}}
      initialObjectPhotos={project.object_photos || {}}
      onSubmit={onSubmit}
      onReferencesImported={onSaved}
      submitLabel="Enregistrer & passer à l'écriture"
      onApplyStyleOnly={hasScript ? onApplyStyleOnly : null}
      applyStyleOnlyLabel="Restyler sans réécrire"
    />
  );
}
