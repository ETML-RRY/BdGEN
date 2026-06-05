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
 * Builds the shared "Projet" ribbon group (Export / Duplicate / Trace) from the
 * project-level actions Wizard publishes into context. Every in-project step
 * appends this group so these commands are reachable from any phase.
 *
 * Steps may inject step-specific project commands (e.g. "Télécharger le PDF"
 * on the Planches phase) through `extraCommands`; they land after Dupliquer and
 * before the debug-only Trace command.
 *
 * @param {{ exportUrl?: string, onDuplicate?: () => void, onTrace?: () => void }} actions
 * @param {Array<object>} [extraCommands] extra project-level ribbon commands
 * @returns ribbon group or null when no actions are available
 */
export function projectRibbonGroup(actions, extraCommands = []) {
  if (!actions) return null;
  const commands = [];

  if (actions.exportUrl) {
    commands.push({
      id: "export",
      label: "Exporter",
      icon: createElement(FaDownload),
      onClick: () => downloadUrl(actions.exportUrl),
      title: "Exporter le projet complet en archive .bdgen",
    });
  }
  if (actions.onDuplicate) {
    commands.push({
      id: "duplicate",
      label: "Dupliquer",
      icon: createElement(FaCopy),
      onClick: actions.onDuplicate,
      title: "Dupliquer ce projet (choisir les éléments à reprendre)",
    });
  }
  if (extraCommands?.length) commands.push(...extraCommands);
  if (actions.onTrace) {
    commands.push({
      id: "trace",
      label: "Trace",
      icon: createElement(FiActivity),
      onClick: actions.onTrace,
      title: "Inspecter la trace d'exécution (debug)",
    });
  }

  if (!commands.length) return null;
  return { id: "projet", label: "Projet", commands };
}
