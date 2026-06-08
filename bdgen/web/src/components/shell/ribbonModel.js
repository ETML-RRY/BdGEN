import { FaDownload, FaCopy } from "react-icons/fa6";
import { FiActivity } from "react-icons/fi";
import { createElement } from "react";

/**
 * Triggers a same-origin file download without leaving the SPA.
 */
function downloadUrl(url) {
  const a = document.createElement("a");
  a.href = url;
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

/**
 * Builds the shared "Project" ribbon group (Export / Duplicate / Trace) from
 * the project-level actions Wizard publishes into context. Every in-project
 * step appends this group so these commands are reachable from any phase.
 *
 * Steps may inject step-specific project commands (e.g. "Download the PDF"
 * on the Pages phase) through `extraCommands`; they land after Duplicate and
 * before the debug-only Trace command.
 *
 * The `t` argument is an i18next `t` function — it owns the localized labels
 * for the project group so callers can keep the rest of the ribbon in their
 * own language.
 *
 * @param {{ exportUrl?: string, onDuplicate?: () => void, onTrace?: () => void }} actions
 * @param {Array<object>} [extraCommands] extra project-level ribbon commands
 * @param {(key: string) => string} t
 * @returns ribbon group or null when no actions are available
 */
export function projectRibbonGroup(actions, extraCommands = [], t) {
  if (!actions) return null;
  const commands = [];

  if (actions.exportUrl) {
    commands.push({
      id: "export",
      label: t("ribbon.export"),
      icon: createElement(FaDownload),
      onClick: () => downloadUrl(actions.exportUrl),
      title: t("ribbon.exportTitle"),
    });
  }
  if (actions.onDuplicate) {
    commands.push({
      id: "duplicate",
      label: t("ribbon.duplicate"),
      icon: createElement(FaCopy),
      onClick: actions.onDuplicate,
      title: t("ribbon.duplicateTitle"),
    });
  }
  if (extraCommands?.length) commands.push(...extraCommands);
  if (actions.onTrace) {
    commands.push({
      id: "trace",
      label: t("ribbon.trace"),
      icon: createElement(FiActivity),
      onClick: actions.onTrace,
      title: t("ribbon.traceTitle"),
    });
  }

  if (!commands.length) return null;
  return { id: "projet", label: t("ribbon.groupProject"), commands };
}
