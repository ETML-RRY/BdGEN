import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { FaWandMagicSparkles, FaArrowRotateRight, FaListCheck } from "react-icons/fa6";
import { api } from "../../api.js";
import { useAppContext } from "../../context/AppContext.jsx";
import useRegisterShell from "../../hooks/useRegisterShell.js";
import { projectRibbonGroup } from "../shell/ribbonModel.js";
import useJobStream from "../useJobStream.js";
import ProgressPanel from "../ProgressPanel.jsx";
import RunningBanner from "../RunningBanner.jsx";
import ScriptBrowser, { useScriptTabs } from "../ScriptBrowser.jsx";
import ConfirmDialog from "../ConfirmDialog.jsx";
import { SHOW_COHERENCE_CHECK } from "../../featureFlags.js";
import { formatError } from "../../i18n/formatError.js";

export default function ScriptStep({ project, onChanged }) {
  const { t } = useTranslation();
  const { name } = useParams();
  const { projectActions } = useAppContext();
  const stream = useJobStream({ project: name, step: "script" });
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState(null);
  const [confirmingRegenAll, setConfirmingRegenAll] = useState(false);
  const [checkingCoherence, setCheckingCoherence] = useState(false);
  const [coherenceError, setCoherenceError] = useState(null);
  // Active script sub-section — driven by the left sidebar (like Planches).
  const [scriptTab, setScriptTab] = useState("characters");

  const target = project.config?.structure?.page_count ?? null;
  const written = project.script?.pages?.length ?? 0;
  const isComplete = target !== null && written >= target && (project.script?.characters?.length ?? 0) > 0;
  const isRunning = stream.matchesThisStep && stream.job?.status === "running";
  const otherStepRunning = stream.job?.status === "running" && !stream.matchesThisStep;
  const blocked = otherStepRunning;

  async function start() {
    if (starting || isRunning) return;
    setError(null);
    setStarting(true);
    try {
      await api.startStep(name, "script");
      // Pull the fresh job snapshot so the progress panel renders immediately
      // — without this the UI keeps showing the start button until the first
      // SSE event lands, and the user can click again.
      await stream.refresh();
    } catch (e) {
      setError(formatError(e, t));
    } finally {
      setStarting(false);
    }
  }

  async function checkCoherence() {
    setCoherenceError(null);
    setCheckingCoherence(true);
    try {
      await api.checkScriptCoherence(name);
      await onChanged();
    } catch (e) {
      setCoherenceError(formatError(e, t));
    } finally {
      setCheckingCoherence(false);
    }
  }

  async function regenerateFlaggedPage(pageNumber) {
    const coherence = project.coherence || { issues: [], suggestions: [] };
    const pageIssues = (coherence.issues || []).filter((i) => i.page_number === pageNumber);
    const pageSuggestions = (coherence.suggestions || []).filter((s) => s.page_number === pageNumber);
    const all = [...pageIssues, ...pageSuggestions];
    const feedback =
      all.length > 0
        ? t("scriptBrowser.feedbackImprove", {
            messages: all.map((i) => i.message).join(" "),
          })
        : t("scriptBrowser.feedbackRegen");
    await api.refinePage(name, pageNumber, feedback, true);
    await onChanged();
  }

  async function applySuggestion(suggestionMessage) {
    await api.applyGlobalSuggestion(name, suggestionMessage);
    await onChanged();
  }

  // Refresh project after a terminal event so the script becomes browseable.
  useEffect(() => {
    if (stream.terminal) {
      onChanged();
    }
  }, [stream.terminal, onChanged]);

  // While the job is running, refresh the project whenever a milestone
  // event lands (setup_done, page_N_done, etc.) so the partial-script
  // browser shows the latest content the engine has saved to disk.
  useEffect(() => {
    if (!stream.events.length) return;
    const last = stream.events[stream.events.length - 1];
    if (last?.phase?.endsWith("_done") || last?.phase === "done") {
      onChanged();
    }
  }, [stream.events, onChanged]);

  // Publish this step's actions to the ribbon (shared by all render branches).
  const hasPages = (project.script?.pages?.length ?? 0) > 0;

  const genCommands = [];
  if (!hasPages) {
    genCommands.push({
      id: "write",
      label: t("scriptBrowser.ribbon.write"),
      icon: <FaWandMagicSparkles />,
      tone: "primary",
      onClick: start,
      disabled: starting || blocked || isRunning,
    });
  } else {
    if (!isComplete) {
      genCommands.push({
        id: "resume",
        label: t("scriptBrowser.ribbon.resume"),
        icon: <FaWandMagicSparkles />,
        tone: "primary",
        onClick: start,
        disabled: starting || blocked || isRunning,
      });
    }
    genCommands.push({
      id: "regen-all",
      label: t("scriptBrowser.ribbon.regenAll"),
      icon: <FaArrowRotateRight />,
      tone: "danger",
      onClick: () => setConfirmingRegenAll(true),
      disabled: starting || blocked || isRunning,
      title: t("scriptBrowser.ribbon.regenAllTitle"),
    });
  }
  const ribbonGroups = [
    { id: "gen", label: t("scriptBrowser.ribbon.groupScript"), commands: genCommands },
  ];
  if (hasPages && SHOW_COHERENCE_CHECK) {
    ribbonGroups.push({
      id: "coh",
      label: t("scriptBrowser.ribbon.groupCoherence"),
      commands: [
        {
          id: "check",
          label: t("scriptBrowser.ribbon.check"),
          icon: <FaListCheck />,
          onClick: checkCoherence,
          active: checkingCoherence,
          disabled: checkingCoherence || blocked || isRunning,
          title: t("scriptBrowser.ribbon.checkTitle"),
        },
      ],
    });
  }
  const projectGroup = projectRibbonGroup(projectActions, [], t);
  if (projectGroup) ribbonGroups.push(projectGroup);

  // Script tab labels are language-aware; resolve them via a hook so the
  // sidebar matches the script browser's own tab strip.
  const scriptTabs = useScriptTabs();

  // Left sidebar — script sub-sections, shown whenever the browser is on screen
  // (i.e. some content already exists). Mirrors the Planches phase navigation.
  const script = project.script;
  const charCount = script?.characters?.length ?? 0;
  const pageCount = script?.pages?.length ?? 0;
  const browserVisible = (isRunning && (charCount > 0 || pageCount > 0)) || pageCount > 0;
  const coherenceState = project.coherence || { dirty: false, issues: [] };
  const coherenceIssues = coherenceState.issues?.length ?? 0;
  const coherenceDirty = !!coherenceState.dirty;

  const sidebar = browserVisible
    ? {
        sections: [
          {
            id: "script",
            label: t("scriptBrowser.ribbon.groupScript"),
            items: scriptTabs.map((sub) => {
              const item = { id: sub.id, label: sub.label };
              if (sub.id === "characters") item.badge = charCount || undefined;
              else if (sub.id === "locations") item.badge = script?.locations?.length || undefined;
              else if (sub.id === "objects") item.badge = script?.objects?.length || undefined;
              else if (sub.id === "pages") item.badge = pageCount || undefined;
              else if (sub.id === "coherence") {
                item.badge = coherenceIssues > 0 ? coherenceIssues : coherenceDirty ? "•" : undefined;
                item.tone = "peach";
              }
              return item;
            }),
          },
        ],
        activeItem: scriptTab,
        onSelect: setScriptTab,
      }
    : null;

  useRegisterShell({ ribbon: { groups: ribbonGroups }, sidebar }, [
    hasPages,
    isComplete,
    isRunning,
    blocked,
    starting,
    checkingCoherence,
    projectActions,
    browserVisible,
    scriptTab,
    charCount,
    pageCount,
    script?.locations?.length,
    script?.objects?.length,
    coherenceIssues,
    coherenceDirty,
    scriptTabs,
  ]);

  if (isRunning) {
    const hasPartial = (project.script?.characters?.length ?? 0) > 0 || (project.script?.pages?.length ?? 0) > 0;
    return (
      <div className="space-y-6">
        <ProgressPanel
          title={t("scriptBrowser.progressTitle")}
          job={stream.job}
          events={stream.events}
          onInterrupt={stream.interrupt}
          hint={t("scriptBrowser.progressHint")}
        />
        {hasPartial && (
          <ScriptBrowser
            project={project}
            onChanged={onChanged}
            readOnly
            tab={scriptTab}
            onTabChange={setScriptTab}
            coherence={SHOW_COHERENCE_CHECK ? project.coherence : undefined}
            onRegeneratePage={SHOW_COHERENCE_CHECK ? regenerateFlaggedPage : undefined}
          />
        )}
      </div>
    );
  }

  // Show the post-run browser when a script exists with pages, even if not "complete"
  // (the user can iterate freely).
  if (project.script?.pages?.length > 0) {
    const coherence = project.coherence || { dirty: false, issues: [], suggestions: [], flagged_pages: [] };
    return (
      <div className="space-y-4">
        {blocked && <RunningBanner job={stream.job} />}
        {stream.terminal && stream.terminal.status !== "completed" && (
          <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
        )}
        {!isComplete && target !== null && !blocked && (
          <div className="card p-4 flex items-center justify-between gap-4 bg-[var(--color-peach-100)] border-[var(--color-peach-300)]">
            <span className="text-sm">
              {t("scriptBrowser.partialScript", { written, target })}
            </span>
            <button className="btn btn-primary" onClick={start} disabled={starting}>
              {t("scriptBrowser.resumeGen")}
            </button>
          </div>
        )}
        <ScriptBrowser
          project={project}
          onChanged={onChanged}
          readOnly={blocked}
          tab={scriptTab}
          onTabChange={setScriptTab}
          coherence={SHOW_COHERENCE_CHECK ? coherence : undefined}
          onRegeneratePage={SHOW_COHERENCE_CHECK ? regenerateFlaggedPage : undefined}
          checking={SHOW_COHERENCE_CHECK ? checkingCoherence : false}
          coherenceError={SHOW_COHERENCE_CHECK ? coherenceError : null}
          onCheck={SHOW_COHERENCE_CHECK ? checkCoherence : null}
          onApplySuggestion={SHOW_COHERENCE_CHECK ? applySuggestion : null}
        />
        {confirmingRegenAll && (
          <ConfirmDialog
            title={t("scriptBrowser.regenAllConfirmTitle")}
            body={t("scriptBrowser.regenAllConfirmBody")}
            confirmLabel={t("scriptBrowser.regenAllConfirm")}
            variant="danger"
            onConfirm={async () => {
              await api.regenerateAll(name, "script");
              await stream.refresh();
            }}
            onClose={() => setConfirmingRegenAll(false)}
          />
        )}
      </div>
    );
  }

  // No script yet → invitation to start
  return (
    <div className="space-y-4">
      {blocked && <RunningBanner job={stream.job} />}
      {stream.terminal && stream.terminal.status !== "completed" && (
        <TerminalBanner terminal={stream.terminal} onClear={stream.clear} />
      )}
      <div className="card p-8 text-center">
        <h2 className="text-lg font-semibold mb-2">{t("scriptBrowser.emptyTitle")}</h2>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mx-auto mb-6">
          {t("scriptBrowser.emptyBody")}
        </p>
        {error && <p className="text-[var(--color-rose-500)] text-sm mb-3">{error}</p>}
        <button className="btn btn-primary" onClick={start} disabled={starting || blocked}>
          {starting ? t("scriptBrowser.starting") : t("scriptBrowser.ribbon.write")}
        </button>
      </div>
    </div>
  );
}

function TerminalBanner({ terminal, onClear }) {
  const { t } = useTranslation();
  const tone =
    terminal.status === "completed" ? "chip-mint" : terminal.status === "interrupted" ? "chip-peach" : "chip-rose";
  return (
    <div className="card p-4 flex items-center justify-between gap-4">
      <div className="text-sm">
        <span className={"chip " + tone + " mr-2"}>{terminal.status}</span>
        {terminal.message}
      </div>
      <button className="btn btn-ghost text-sm" onClick={onClear}>
        {t("scriptBrowser.ok")}
      </button>
    </div>
  );
}
