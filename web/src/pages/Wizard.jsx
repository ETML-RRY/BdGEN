import { useEffect, useState, useCallback } from "react";
import { Routes, Route, Link, useParams, useLocation, useNavigate, Navigate } from "react-router-dom";
import { api } from "../api.js";
import StepNav from "../components/StepNav.jsx";
import PreparationStep from "../components/steps/PreparationStep.jsx";
import ScriptStep from "../components/steps/ScriptStep.jsx";
import ReferencesStep from "../components/steps/ReferencesStep.jsx";
import WireframesStep from "../components/steps/WireframesStep.jsx";
import ComposeStep from "../components/steps/ComposeStep.jsx";

export const STEPS = [
  { id: "preparation", label: "Préparation" },
  { id: "script", label: "Écriture" },
  { id: "references", label: "Références" },
  { id: "wireframes", label: "Esquisses", optional: true },
  { id: "compose", label: "Planches" },
];

export default function Wizard() {
  const { name } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [project, setProject] = useState(null);
  const [error, setError] = useState(null);

  const reload = useCallback(async () => {
    try {
      const p = await api.getProject(name);
      setProject(p);
      return p;
    } catch (e) {
      setError(e.message);
      return null;
    }
  }, [name]);

  useEffect(() => {
    reload();
  }, [reload]);

  // Auto-redirect to the active step when the user lands on /projects/:name (no sub-route).
  useEffect(() => {
    if (!project) return;
    const sub = location.pathname.split(`/projects/${encodeURIComponent(name)}`)[1] || "";
    if (sub === "" || sub === "/") {
      navigate(`/projects/${encodeURIComponent(name)}/${project.state === "done" ? "compose" : project.state}`, { replace: true });
    }
  }, [project, location.pathname, name, navigate]);

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

  const activeStep = location.pathname.split("/").pop();

  return (
    <div className="max-w-6xl mx-auto px-6 py-6">
      <header className="mb-6">
        <div className="flex items-baseline justify-between gap-4 mb-1">
          <h1 className="text-2xl font-semibold">
            {project.config?.metadata?.title || project.name}
          </h1>
          <div className="flex items-center gap-2">
            <a
              href={api.exportUrl(name)}
              className="btn btn-ghost text-sm"
              download
            >
              Télécharger .bdgen
            </a>
          </div>
        </div>
        {project.config?.metadata?.author && (
          <p className="text-sm text-[var(--color-ink-soft)]">
            par {project.config.metadata.author}
          </p>
        )}
      </header>

      <StepNav
        steps={STEPS}
        active={activeStep}
        baseUrl={`/projects/${encodeURIComponent(name)}`}
      />

      <div className="mt-6">
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
            path="wireframes"
            element={<WireframesStep project={project} onChanged={reload} />}
          />
          <Route
            path="compose"
            element={<ComposeStep project={project} onChanged={reload} />}
          />
          <Route path="*" element={<Navigate to="preparation" replace />} />
        </Routes>
      </div>
    </div>
  );
}
