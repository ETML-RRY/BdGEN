import { useNavigate, useParams } from "react-router-dom";
import ImageStep from "../ImageStep.jsx";

export default function ReferencesStep({ project, onChanged }) {
  const navigate = useNavigate();
  const { name } = useParams();

  const items = [
    ...project.references.characters.map((c) => ({
      id: c.id,
      label: `Personnage — ${c.name}`,
      image_url: c.image_url,
      quality: c.quality,
      stale: c.stale,
      description: [c.physical_description, c.outfit].filter(Boolean).join("\n\n"),
    })),
    ...project.references.locations.map((l) => ({
      id: l.id,
      label: `Décor — ${l.name}`,
      image_url: l.image_url,
      quality: l.quality,
      stale: l.stale,
      description: l.description,
    })),
    ...(project.references.objects || []).map((o) => ({
      id: o.id,
      label: `Objet — ${o.name}`,
      image_url: o.image_url,
      quality: o.quality,
      stale: o.stale,
      description: o.description,
    })),
  ];

  return (
    <ImageStep
      project={project}
      onChanged={onChanged}
      stepId="references"
      title="Références visuelles"
      intro="Une planche-modèle est générée pour chaque personnage et chaque décor. Elles servent de référence permanente pour garder les personnages cohérents d'une planche à l'autre."
      items={items}
      layout="square"
      supportsQuality
      emptyLabel="Cette référence n'a pas encore été générée."
      onContinue={() => navigate(`/projects/${encodeURIComponent(name)}/compose`)}
      continueLabel="Continuer vers les planches →"
    />
  );
}
