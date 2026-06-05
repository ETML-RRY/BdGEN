import { useNavigate, useParams } from "react-router-dom";
import { FaFilePdf } from "react-icons/fa6";
import ImageStep from "../ImageStep.jsx";
import { SHOW_UPSCALE } from "../../featureFlags.js";

function composeMeta(id) {
  if (id === "cover") return { group: "Couverture", shortLabel: "Couverture", label: "Couverture" };
  if (id === "back") return { group: "Couverture", shortLabel: "4ᵉ de couverture", label: "4ᵉ de couverture" };
  const n = id.replace("page_", "");
  return { group: "Planches", shortLabel: `Planche ${n}`, label: `Planche ${n}` };
}

export default function ComposeStep({ project, onChanged }) {
  const navigate = useNavigate();
  const { name } = useParams();
  const items = project.composed.map((w) => {
    const meta = composeMeta(w.id);
    return {
      id: w.id,
      label: meta.label,
      shortLabel: meta.shortLabel,
      group: meta.group,
      image_url: w.image_url,
      stale: w.stale,
    };
  });

  const projectExtraCommands = project.pdf_url
    ? [
        {
          id: "pdf",
          label: "Télécharger le PDF",
          icon: <FaFilePdf />,
          onClick: () => {
            const a = document.createElement("a");
            a.href = project.pdf_url;
            a.download = "";
            document.body.appendChild(a);
            a.click();
            a.remove();
          },
          title: "Toutes les planches assemblées en album PDF.",
        },
      ]
    : null;

  return (
    <ImageStep
      project={project}
      onChanged={onChanged}
      stepId="compose"
      title="Planches finales"
      intro="Génération de chaque planche en pleine page avec bulles, texte, couleurs et finitions. Étape la plus longue et la plus coûteuse en API — la qualité utilisée est celle définie en phase de préparation."
      items={items}
      layout={project.config?.structure?.page_format || "portrait"}
      genGroupLabel="Planches"
      startLabel="Générer les planches"
      projectExtraCommands={projectExtraCommands}
      onContinue={
        SHOW_UPSCALE ? () => navigate(`/projects/${encodeURIComponent(name)}/upscale`) : undefined
      }
      continueLabel={SHOW_UPSCALE ? "Continuer vers l'upscale →" : undefined}
    />
  );
}
