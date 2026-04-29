import { useNavigate, useParams } from "react-router-dom";
import ImageStep from "../ImageStep.jsx";

export default function UpscaleStep({ project, onChanged }) {
  const navigate = useNavigate();
  const { name } = useParams();
  const options = project.upscale || {};
  const enabled = !!options.enabled;
  const available = !!project.upscale_available;
  const items = (project.upscaled || []).map((item) => ({
    id: item.id,
    label:
      item.id === "cover"
        ? "Couverture upscalée"
        : item.id === "back"
        ? "4ᵉ de couverture upscalée"
        : `Planche upscalée ${item.id.replace("page_", "")}`,
    image_url: item.image_url,
    stale: item.stale,
  }));

  if (!enabled) {
    return (
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">Upscale (Pruna)</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-4">
          L'upscale n'est pas activé pour ce projet. Activez-le dans la section
          Préparation (Modèles de génération &rarr; Upscale local CPU) pour
          agrandir les planches via le modèle Pruna local.
        </p>
        <button
          className="btn btn-secondary"
          onClick={() =>
            navigate(
              `/projects/${encodeURIComponent(name)}/preparation`
            )
          }
        >
          Aller à la Préparation
        </button>
      </div>
    );
  }

  if (!available) {
    return (
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">Upscale (Pruna via Replicate)</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-4">
          L'upscale est activé mais la clé API Replicate n'est pas configurée
          sur le serveur. Ajoutez{" "}
          <code className="text-xs bg-[var(--color-paper-soft)] px-1 py-0.5 rounded">
            REPLICATE_API_TOKEN
          </code>{" "}
          dans le fichier <code className="text-xs bg-[var(--color-paper-soft)] px-1 py-0.5 rounded">.env</code> du serveur.
        </p>
      </div>
    );
  }

  const hasComposed = (project.composed || []).some((c) => c.image_url);
  if (!hasComposed) {
    return (
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">Upscale (Pruna)</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-4">
          Aucune planche composée n'est disponible. Générez d'abord les
          planches à l'étape précédente avant de lancer l'upscale.
        </p>
        <button
          className="btn btn-secondary"
          onClick={() =>
            navigate(
              `/projects/${encodeURIComponent(name)}/compose`
            )
          }
        >
          Aller aux Planches
        </button>
      </div>
    );
  }

  return (
    <ImageStep
      project={project}
      onChanged={onChanged}
      stepId="upscale"
      title="Upscale (Pruna)"
      intro="Agrandissement des planches via Pruna P-Image-Upscale (Replicate). Coût : ~$0.005/image (1-4 MP) ou ~$0.01/image (5-8 MP)."
      items={items}
      layout="portrait"
      allowRefine={false}
      emptyLabel="Aucune planche upscalée pour l'instant."
    />
  );
}
