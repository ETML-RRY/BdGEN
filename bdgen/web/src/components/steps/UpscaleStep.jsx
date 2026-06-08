import { useTranslation, Trans } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import ImageStep from "../ImageStep.jsx";

export default function UpscaleStep({ project, onChanged }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { name } = useParams();
  const options = project.upscale || {};
  const enabled = !!options.enabled;
  const available = !!project.upscale_available;
  const items = (project.upscaled || []).map((item) => {
    const isCover = item.id === "cover" || item.id === "back";
    const shortLabel =
      item.id === "cover"
        ? t("stepsUi.upscale.cover")
        : item.id === "back"
        ? t("stepsUi.upscale.backCover")
        : t("stepsUi.upscale.page", { n: item.id.replace("page_", "") });
    return {
      id: item.id,
      label:
        item.id === "cover"
          ? t("stepsUi.upscale.coverUpscaled")
          : item.id === "back"
          ? t("stepsUi.upscale.backCoverUpscaled")
          : t("stepsUi.upscale.pageUpscaled", { n: item.id.replace("page_", "") }),
      shortLabel,
      group: isCover ? t("stepsUi.upscale.groupCover") : t("stepsUi.upscale.groupPages"),
      image_url: item.image_url,
      stale: item.stale,
    };
  });

  if (!enabled) {
    return (
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">{t("stepsUi.upscale.title")}</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-4">
          {t("stepsUi.upscale.notEnabled")}
        </p>
        <button
          className="btn btn-secondary"
          onClick={() =>
            navigate(
              `/projects/${encodeURIComponent(name)}/preparation`
            )
          }
        >
          {t("stepsUi.upscale.goPreparation")}
        </button>
      </div>
    );
  }

  if (!available) {
    return (
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">{t("stepsUi.upscale.titleReplicate")}</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-4">
          <Trans
            i18nKey="stepsUi.upscale.missingReplicate"
            components={{
              code: <code className="text-xs bg-[var(--color-paper-soft)] px-1 py-0.5 rounded" />,
            }}
          />
        </p>
      </div>
    );
  }

  const hasComposed = (project.composed || []).some((c) => c.image_url);
  if (!hasComposed) {
    return (
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">{t("stepsUi.upscale.title")}</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-4">
          {t("stepsUi.upscale.noPages")}
        </p>
        <button
          className="btn btn-secondary"
          onClick={() =>
            navigate(
              `/projects/${encodeURIComponent(name)}/compose`
            )
          }
        >
          {t("stepsUi.upscale.goPages")}
        </button>
      </div>
    );
  }

  return (
    <ImageStep
      project={project}
      onChanged={onChanged}
      stepId="upscale"
      title={t("stepsUi.upscale.imageStepTitle")}
      intro={t("stepsUi.upscale.intro")}
      items={items}
      layout={project.config?.structure?.page_format || "portrait"}
      allowRefine={false}
      startLabel={t("stepsUi.upscale.startLabel")}
      emptyLabel={t("stepsUi.upscale.emptyLabel")}
    />
  );
}
