import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { FaFilePdf } from "react-icons/fa6";
import ImageStep from "../ImageStep.jsx";
import { SHOW_UPSCALE } from "../../featureFlags.js";

function composeMeta(id, t) {
  if (id === "cover") return { group: t("stepsUi.compose.cover"), shortLabel: t("stepsUi.compose.cover"), label: t("stepsUi.compose.cover") };
  if (id === "back") return { group: t("stepsUi.compose.cover"), shortLabel: t("stepsUi.compose.backCover"), label: t("stepsUi.compose.backCover") };
  const n = id.replace("page_", "");
  return { group: t("stepsUi.compose.title"), shortLabel: t("stepsUi.compose.page", { n }), label: t("stepsUi.compose.page", { n }) };
}

export default function ComposeStep({ project, onChanged }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { name } = useParams();
  const items = project.composed.map((w) => {
    const meta = composeMeta(w.id, t);
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
          label: t("stepsUi.compose.downloadPdf"),
          icon: <FaFilePdf />,
          onClick: () => {
            const a = document.createElement("a");
            a.href = project.pdf_url;
            a.download = "";
            document.body.appendChild(a);
            a.click();
            a.remove();
          },
          title: t("stepsUi.compose.downloadPdfTitle"),
        },
      ]
    : null;

  return (
    <ImageStep
      project={project}
      onChanged={onChanged}
      stepId="compose"
      title={t("stepsUi.compose.title")}
      intro={t("stepsUi.compose.intro")}
      items={items}
      layout={project.config?.structure?.page_format || "portrait"}
      genGroupLabel={t("stepsUi.compose.groupLabel")}
      startLabel={t("stepsUi.compose.startLabel")}
      projectExtraCommands={projectExtraCommands}
      onContinue={
        SHOW_UPSCALE ? () => navigate(`/projects/${encodeURIComponent(name)}/upscale`) : undefined
      }
      continueLabel={SHOW_UPSCALE ? t("stepsUi.compose.continueLabel") : undefined}
    />
  );
}
