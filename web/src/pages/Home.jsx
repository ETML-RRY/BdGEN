import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { FaPlus, FaUpload, FaCopy } from "react-icons/fa6";
import { api } from "../api.js";
import StateChip from "../components/StateChip.jsx";
import RunningBanner from "../components/RunningBanner.jsx";

const STATE_LABELS = {
  preparation: "Préparation",
  script: "Écriture",
  references: "Références",
  compose: "Planches",
  done: "Terminé",
};

export default function Home() {
  const [projects, setProjects] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [duplicating, setDuplicating] = useState(null);
  const fileRef = useRef(null);
  const navigate = useNavigate();

  async function refresh() {
    try {
      const [{ projects }, { job }] = await Promise.all([
        api.listProjects(),
        api.currentJob(),
      ]);
      setProjects(projects);
      setJob(job);
    } catch (e) {
      setError(e.message);
    }
  }

  async function onDuplicate(e, sourceName) {
    e.preventDefault();
    e.stopPropagation();
    if (duplicating) return;
    const includeReferences = window.confirm(
      "Inclure les images de référence (personnages, décors, objets) dans la copie ?\n\n" +
      "OK : conserver les références déjà générées (utile pour un Tome 2 — pas besoin de les régénérer).\n" +
      "Annuler : repartir d'une copie sans images, à régénérer."
    );
    setDuplicating(sourceName);
    setError(null);
    try {
      const { name } = await api.duplicateProject(sourceName, { includeReferences });
      navigate(`/projects/${encodeURIComponent(name)}`);
    } catch (err) {
      setError(err.message);
    } finally {
      setDuplicating(null);
    }
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  async function onImport(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const { name } = await api.importProject(file);
      navigate(`/projects/${encodeURIComponent(name)}`);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {job && job.status === "running" && (
        <RunningBanner job={job} className="mb-6" />
      )}

      <section className="card p-8 mb-8">
        <h1 className="text-2xl font-semibold mb-2">
          Bienvenue sur BdGEN
        </h1>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mb-6">
          BdGEN écrit le scénario, dessine les références puis assemble une BD
          complète à partir d'une simple description. Lancez
          un nouveau projet, reprenez-en un en cours, ou importez une archive
          <code className="px-1 py-0.5 bg-[var(--color-paper-soft)] rounded mx-1">.bdgen</code>
          pour continuer où vous l'aviez laissé.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link to="/new" className="btn btn-primary inline-flex items-center gap-2">
            <FaPlus aria-hidden /> Nouveau projet
          </Link>
          <button
            type="button"
            className="btn btn-secondary inline-flex items-center gap-2"
            onClick={() => fileRef.current?.click()}
          >
            <FaUpload aria-hidden /> Importer un projet
          </button>
          <input
            ref={fileRef}
            type="file"
            accept=".bdgen,.zip"
            className="hidden"
            onChange={onImport}
          />
        </div>
        {error && (
          <p className="mt-4 text-sm text-[var(--color-rose-500)]">{error}</p>
        )}
      </section>

      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="text-lg font-semibold">Projets en cours</h2>
          <span className="text-xs text-[var(--color-mute)]">
            {projects ? `${projects.length} projet${projects.length > 1 ? "s" : ""}` : "…"}
          </span>
        </div>

        {projects === null ? (
          <p className="text-sm text-[var(--color-mute)]">Chargement…</p>
        ) : projects.length === 0 ? (
          <div className="card p-8 text-center text-[var(--color-mute)]">
            Aucun projet pour l'instant.
            <br />
            Démarrez avec « Nouveau projet ».
          </div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((p) => (
              <li key={p.name}>
                <Link
                  to={`/projects/${encodeURIComponent(p.name)}`}
                  className="card p-5 block hover:border-[var(--color-primary-300)] transition"
                >
                  <div className="flex items-start justify-between gap-3 mb-2">
                    <div>
                      <div className="font-semibold">
                        {p.display_name || p.title || p.name}
                      </div>
                      {p.display_name && p.title && p.title !== p.display_name && (
                        <div className="text-xs text-[var(--color-mute)] italic">
                          {p.title}
                        </div>
                      )}
                      {p.author && (
                        <div className="text-sm text-[var(--color-ink-soft)]">
                          {p.author}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        className="btn btn-ghost text-xs inline-flex items-center gap-1.5"
                        title="Dupliquer ce projet (avec ou sans les références images)"
                        onClick={(e) => onDuplicate(e, p.name)}
                        disabled={duplicating === p.name}
                      >
                        <FaCopy aria-hidden />
                        {duplicating === p.name ? "…" : "Dupliquer"}
                      </button>
                      <StateChip state={p.state} label={STATE_LABELS[p.state]} />
                    </div>
                  </div>
                  <div className="text-xs text-[var(--color-mute)] flex flex-wrap gap-x-4 gap-y-1 mt-3">
                    {p.page_count !== null && (
                      <span>
                        Planches écrites&nbsp;:{" "}
                        <strong className="text-[var(--color-ink-soft)]">
                          {p.pages_written}/{p.page_count}
                        </strong>
                      </span>
                    )}
                    {p.references_total > 0 && (
                      <span>
                        Références&nbsp;:{" "}
                        <strong className="text-[var(--color-ink-soft)]">
                          {p.references_ready}/{p.references_total}
                        </strong>
                      </span>
                    )}
                    {p.pdf_ready && (
                      <span className="chip chip-mint">PDF prêt</span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
