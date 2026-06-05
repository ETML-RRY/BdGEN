import ImageStep from "../ImageStep.jsx";

export default function ReferencesStep({ project, onChanged }) {
  const items = [
    ...project.references.characters.map((c) => ({
      id: c.id,
      label: `Personnage — ${c.name}`,
      shortLabel: c.name,
      group: "Personnages",
      image_url: c.image_url,
      stale: c.stale,
      description: [c.physical_description, c.outfit].filter(Boolean).join("\n\n"),
    })),
    ...project.references.locations.map((l) => ({
      id: l.id,
      label: `Décor — ${l.name}`,
      shortLabel: l.name,
      group: "Décors",
      image_url: l.image_url,
      stale: l.stale,
      description: l.description,
    })),
    ...(project.references.objects || []).map((o) => ({
      id: o.id,
      label: `Objet — ${o.name}`,
      shortLabel: o.name,
      group: "Objets",
      image_url: o.image_url,
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
      genGroupLabel="Références"
      startLabel="Générer les références"
      emptyLabel="Cette référence n'a pas encore été générée."
    />
  );
}
