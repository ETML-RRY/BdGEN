import { useNavigate, useParams } from "react-router-dom";
import ImageStep from "../ImageStep.jsx";

export default function WireframesStep({ project, onChanged }) {
  const navigate = useNavigate();
  const { name } = useParams();

  const items = project.wireframes.map((w) => ({
    id: w.id,
    label:
      w.id === "cover"
        ? "Couverture"
        : w.id === "back"
        ? "4ᵉ de couverture"
        : `Planche ${w.id.replace("page_", "")}`,
    image_url: w.image_url,
    stale: w.stale,
  }));

  return (
    <ImageStep
      project={project}
      onChanged={onChanged}
      stepId="wireframes"
      title="Esquisses (optionnel)"
      intro="Esquisse rapide en niveaux de gris de chaque planche, pour valider la mise en page et le découpage avant la composition finale. Bon marché et utile, mais facultatif."
      items={items}
      allowSkip
      onSkip={() => navigate(`/projects/${encodeURIComponent(name)}/compose`)}
      onContinue={() => navigate(`/projects/${encodeURIComponent(name)}/compose`)}
      continueLabel="Continuer vers les planches →"
    />
  );
}
