import { useEffect, useState, useCallback } from "react";
import { Routes, Route, Link, useParams, useLocation, useNavigate, Navigate } from "react-router-dom";
import { api } from "../api.js";
import { useAppContext } from "../context/AppContext.jsx";
import { STEPS } from "../steps.js";
import PreparationStep from "../components/steps/PreparationStep.jsx";
import ScriptStep from "../components/steps/ScriptStep.jsx";
import ReferencesStep from "../components/steps/ReferencesStep.jsx";
import ComposeStep from "../components/steps/ComposeStep.jsx";
import UpscaleStep from "../components/steps/UpscaleStep.jsx";
import DuplicateProjectDialog from "../components/DuplicateProjectDialog.jsx";
import TracePanel from "../components/TracePanel.jsx";
import { useDebugEnabled } from "../components/useDebugEnabled.js";
import { SHOW_UPSCALE } from "../featureFlags.js";

export { STEPS };

export default function Wizard() {
  const { name } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [project, setProject] = useState(null);
  const [runningJob, setRunningJobLocal] = useState(undefined); // undefined = not yet fetched
  const [error, setError] = useState(null);
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const debug = useDebugEnabled();

  const { setProjectMeta, setRunningJob, setProjectActions } = useAppContext();

  const reload = useCallback(async () => {
    try {
      const [p, { job }] = await Promise.all([api.getProject(name), api.currentJob()]);
      setProject(p);
      setRunningJobLocal(job);
      setRunningJob(job);
      return p;
    } catch (e) {
      setError(e.message);
      return null;
    }
  }, [name, setRunningJob]);

  async function onDuplicate(options) {
    try {
      const { name: newName } = await api.duplicateProject(name, options);
      navigate(`/projects/${encodeURIComponent(newName)}`);
    } catch (e) {
      setError(e.message);
      throw e;
    }
  }

  useEffect(() => {
    reload();
  }, [reload]);

  // Auto-redirect to the active step on first load
  useEffect(() => {
    if (!project || runningJob === undefined) return;
    const sub = location.pathname.split(`/projects/${encodeURIComponent(name)}`)[1] || "";
    if (sub === "" || sub === "/") {
      let targetStep;
      if (runningJob && runningJob.status === "running" && runningJob.project === name) {
        targetStep = runningJob.step;
      } else {
        targetStep = project.state === "done" ? "compose" : project.state;
      }
      navigate(`/projects/${encodeURIComponent(name)}/${targetStep}`, { replace: true });
    }
  }, [project, runningJob, location.pathname, name, navigate]);

  // Sync project metadata to AppBar breadcrumb
  useEffect(() => {
    if (!project) return;
    const activeStep = location.pathname.split("/").pop();
    setProjectMeta({
      name,
      displayName: project.config?.display_name || project.config?.metadata?.title || name,
      activeStep,
    });
  }, [project, location.pathname, name, setProjectMeta]);

  // Publish project-level actions to the ribbon (shared "Projet" tab)
  useEffect(() => {
    if (!project) return;
    setProjectActions({
      exportUrl: api.exportUrl(name),
      onDuplicate: () => setShowDuplicateDialog(true),
      onTrace: debug.enabled
        ? () => navigate(`/projects/${encodeURIComponent(name)}/trace`)
        : null,
    });
  }, [project, name, debug.enabled, setProjectActions, navigate]);

  // Clear context on unmount
  useEffect(() => {
    return () => {
      setProjectMeta(null);
      setProjectActions(null);
    };
  }, [setProjectMeta, setProjectActions]);

  if (error) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <p className="card p-4 text-[var(--color-rose-500)]">Erreur : {error}</p>
        <Link to="/" className="btn btn-secondary mt-4">Retour à l'accueil</Link>
      </div>
    );
  }
  if (!project) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8 text-[var(--color-mute)]">
        Chargement…
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-6">
      <Routes>
        <Route
          path="preparation"
          element={<PreparationStep project={project} onSaved={reload} />}
        />
        <Route
          path="script"
          element={<ScriptStep project={project} onChanged={reload} />}
        />
        <Route
          path="references"
          element={<ReferencesStep project={project} onChanged={reload} />}
        />
        <Route
          path="compose"
          element={<ComposeStep project={project} onChanged={reload} />}
        />
        <Route
          path="upscale"
          element={
            SHOW_UPSCALE ? (
              <UpscaleStep project={project} onChanged={reload} />
            ) : (
              <Navigate to="../compose" replace />
            )
          }
        />
        {debug.enabled && (
          <Route path="trace" element={<TracePanel projectName={name} />} />
        )}
        <Route path="*" element={<Navigate to="preparation" replace />} />
      </Routes>

      {showDuplicateDialog && (
        <DuplicateProjectDialog
          sourceLabel={
            project.config?.display_name ||
            project.config?.metadata?.title ||
            project.name
          }
          onClose={() => setShowDuplicateDialog(false)}
          onConfirm={onDuplicate}
        />
      )}
    </div>
  );
}
