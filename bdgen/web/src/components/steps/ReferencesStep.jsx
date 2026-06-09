import { useTranslation } from "react-i18next";
import ImageStep from "../ImageStep.jsx";

export default function ReferencesStep({ project, onChanged }) {
  const { t } = useTranslation();
  const items = [
    ...project.references.characters.map((c) => ({
      id: c.id,
      label: t("stepsUi.references.itemCharacter", { name: c.name }),
      shortLabel: c.name,
      group: t("stepsUi.references.groupCharacters"),
      image_url: c.image_url,
      stale: c.stale,
      description: [c.physical_description, c.outfit].filter(Boolean).join("\n\n"),
    })),
    ...project.references.locations.map((l) => ({
      id: l.id,
      label: t("stepsUi.references.itemLocation", { name: l.name }),
      shortLabel: l.name,
      group: t("stepsUi.references.groupLocations"),
      image_url: l.image_url,
      stale: l.stale,
      description: l.description,
    })),
    ...(project.references.objects || []).map((o) => ({
      id: o.id,
      label: t("stepsUi.references.itemObject", { name: o.name }),
      shortLabel: o.name,
      group: t("stepsUi.references.groupObjects"),
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
      title={t("stepsUi.references.title")}
      intro={t("stepsUi.references.intro")}
      items={items}
      layout="square"
      genGroupLabel={t("stepsUi.references.groupLabel")}
      startLabel={t("stepsUi.references.startLabel")}
      emptyLabel={t("stepsUi.references.emptyLabel")}
    />
  );
}
