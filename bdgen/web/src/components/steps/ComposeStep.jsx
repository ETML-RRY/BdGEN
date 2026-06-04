import { useNavigate, useParams } from "react-router-dom";
import ImageStep from "../ImageStep.jsx";
import { SHOW_UPSCALE } from "../../featureFlags.js";

export default function ComposeStep({ project, onChanged }) {
  const navigate = useNavigate();
  const { name } = useParams();
  const items = project.composed.map((w) => ({
    id: w.id,
    label:
      w.id === "cover"
        ? "Couverture"
        : w.id === "back"
        ? "4ᵉ de couverture"
        : `Planche ${w.id.replace("page_", "")}`,
    image_url: w.image_url,
    quality: w.quality,
    stale: w.stale,
  }));

  return (
    <div className="space-y-6">
      <ImageStep
        project={project}
        onChanged={onChanged}
        stepId="compose"
        title="Planches finales"
        intro="Génération de chaque planche en pleine page avec bulles, texte, couleurs et finitions. Étape la plus longue et la plus coûteuse en API — lancez d'abord en brouillon pour valider l'ensemble, puis montez en qualité ce qui le mérite."
        items={items}
        layout={project.config?.structure?.page_format || "portrait"}
        supportsQuality
        onContinue={
          SHOW_UPSCALE
            ? () => navigate(`/projects/${encodeURIComponent(name)}/upscale`)
            : undefined
        }
        continueLabel={SHOW_UPSCALE ? "Continuer vers l'upscale →" : undefined}
      />
      {project.pdf_url && (
        <div className="card p-6 bg-[var(--color-mint-100)] border-[var(--color-mint-200)] flex items-center justify-between">
          <div>
            <h3 className="font-semibold">PDF prêt</h3>
            <p className="text-sm text-[var(--color-ink-soft)]">
              Toutes les planches ont été assemblées en album.
            </p>
          </div>
          <a href={project.pdf_url} className="btn btn-primary" download>
            Télécharger le PDF
          </a>
        </div>
      )}
    </div>
  );
}
