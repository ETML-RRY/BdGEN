import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useTranslation, Trans } from "react-i18next";
import { FaPlus, FaUpload, FaCopy, FaTrash, FaDownload, FaChartSimple } from "react-icons/fa6";
import { api } from "../api.js";
import StateChip from "../components/StateChip.jsx";
import RunningBanner from "../components/RunningBanner.jsx";
import ConfirmDeleteDialog from "../components/ConfirmDeleteDialog.jsx";
import DuplicateProjectDialog from "../components/DuplicateProjectDialog.jsx";
import ImportProjectDialog from "../components/ImportProjectDialog.jsx";
import { formatError } from "../i18n/formatError.js";

export default function Home() {
  const { t } = useTranslation();
  const [projects, setProjects] = useState(null);
  const [job, setJob] = useState(null);
  const [error, setError] = useState(null);
  const [duplicating, setDuplicating] = useState(null);
  const [duplicateTarget, setDuplicateTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [importFile, setImportFile] = useState(null);
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
      setError(formatError(e, t));
    }
  }

  function onAskDuplicate(e, project) {
    e.preventDefault();
    e.stopPropagation();
    if (duplicating) return;
    setDuplicateTarget(project);
  }

  async function onConfirmDuplicate(options) {
    if (!duplicateTarget) return;
    setDuplicating(duplicateTarget.name);
    setError(null);
    try {
      const { name } = await api.duplicateProject(duplicateTarget.name, options);
      navigate(`/projects/${encodeURIComponent(name)}`);
    } catch (err) {
      setError(err.message);
      throw err;
    } finally {
      setDuplicating(null);
    }
  }

  async function onConfirmImport({ newTitle, newProject }) {
    if (!importFile) return;
    try {
      const { name } = await api.importProject(importFile, { newTitle, newProject });
      navigate(`/projects/${encodeURIComponent(name)}`);
    } catch (err) {
      setError(formatError(err, t));
      throw err;
    }
  }

  function onAskDelete(e, project) {
    e.preventDefault();
    e.stopPropagation();
    setDeleteTarget(project);
  }

  async function onConfirmDelete() {
    if (!deleteTarget) return;
    setError(null);
    await api.deleteProject(deleteTarget.name);
    await refresh();
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, []);

  function onImport(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    setImportFile(file);
    // Reset input so the same file can be picked again if the user cancels
    e.target.value = "";
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {job && job.status === "running" && (
        <RunningBanner job={job} className="mb-6" />
      )}

      <section className="card p-8 mb-8">
        <h1 className="text-2xl font-semibold mb-2">
          {t("home.title")}
        </h1>
        <p className="text-[var(--color-ink-soft)] max-w-2xl mb-6">
          <Trans
            i18nKey="home.intro"
            components={{ code: <code className="px-1 py-0.5 bg-[var(--color-paper-soft)] rounded mx-1" /> }}
          />
        </p>
        <div className="flex flex-wrap gap-3">
          <Link to="/new" className="btn btn-primary inline-flex items-center gap-2">
            <FaPlus aria-hidden /> {t("home.newProject")}
          </Link>
          <button
            type="button"
            className="btn btn-secondary inline-flex items-center gap-2"
            onClick={() => fileRef.current?.click()}
          >
            <FaUpload aria-hidden /> {t("home.importProject")}
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
          <h2 className="text-lg font-semibold">{t("home.currentProjects")}</h2>
          <span className="text-xs text-[var(--color-mute)]">
            {projects ? t("home.projectsCount", { count: projects.length }) : t("common.loading")}
          </span>
        </div>

        {projects === null ? (
          <p className="text-sm text-[var(--color-mute)]">{t("home.loading")}</p>
        ) : projects.length === 0 ? (
          <div className="card p-8 text-center text-[var(--color-mute)]">
            {t("home.empty")}
            <br />
            {t("home.emptyHint")}
          </div>
        ) : (
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {projects.map((p) => (
              <li key={p.name}>
                <Link
                  to={`/projects/${encodeURIComponent(p.name)}`}
                  className="card p-5 block hover:border-[var(--color-primary-300)] transition group relative"
                >
                  <div className="flex items-start gap-4">
                    {p.thumbnail_url ? (
                      <img
                        src={p.thumbnail_url}
                        alt=""
                        loading="lazy"
                        className="w-16 h-24 object-cover rounded-md border border-[var(--color-paper-soft)] bg-[var(--color-paper-soft)] flex-shrink-0"
                      />
                    ) : (
                      <div
                        aria-hidden
                        className="w-16 h-24 rounded-md border border-dashed border-[var(--color-paper-soft)] bg-[var(--color-paper-soft)] flex-shrink-0"
                      />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-3 mb-2">
                        <div className="min-w-0">
                          <div className="font-semibold truncate">
                            {p.display_name || p.title || p.name}
                          </div>
                          {p.display_name && p.title && p.title !== p.display_name && (
                            <div className="text-xs text-[var(--color-mute)] italic truncate">
                              {p.title}
                            </div>
                          )}
                          {p.author && (
                            <div className="text-sm text-[var(--color-ink-soft)] truncate">
                              {p.author}
                            </div>
                          )}
                        </div>
                        <div className="flex items-center gap-2 flex-shrink-0">
                          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                            <Link
                              to={`/projects/${encodeURIComponent(p.name)}/stats`}
                              className="p-1.5 rounded-md text-[var(--color-ink-soft)] hover:bg-[var(--color-paper-soft)] hover:text-[var(--color-primary-600)] transition-colors"
                              title={t("home.openStats")}
                              aria-label={t("home.openStats")}
                              onClick={(e) => e.stopPropagation()}
                            >
                              <FaChartSimple aria-hidden />
                            </Link>
                            {p.pdf_ready && (
                              <a
                                href={`/api/projects/${encodeURIComponent(p.name)}/files/${encodeURIComponent(p.name)}.pdf`}
                                download
                                className="p-1.5 rounded-md text-[var(--color-ink-soft)] hover:bg-[var(--color-mint-100)] hover:text-[var(--color-mint-700)] transition-colors"
                                title={t("home.downloadPdf")}
                                aria-label={t("home.downloadPdf")}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <FaDownload aria-hidden />
                              </a>
                            )}
                            <button
                              type="button"
                              className="p-1.5 rounded-md text-[var(--color-ink-soft)] hover:bg-[var(--color-paper-soft)] hover:text-[var(--color-primary-600)] transition-colors disabled:opacity-50"
                              title={t("home.duplicateTitle")}
                              aria-label={t("home.duplicateAria")}
                              onClick={(e) => onAskDuplicate(e, p)}
                              disabled={duplicating === p.name}
                            >
                              <FaCopy aria-hidden />
                            </button>
                            <button
                              type="button"
                              className="p-1.5 rounded-md text-[var(--color-ink-soft)] hover:bg-[var(--color-rose-100)] hover:text-[var(--color-rose-500)] transition-colors"
                              title={t("home.deleteTitle")}
                              aria-label={t("home.deleteAria")}
                              onClick={(e) => onAskDelete(e, p)}
                            >
                              <FaTrash aria-hidden />
                            </button>
                          </div>
                          <StateChip state={p.state} />
                        </div>
                      </div>
                      <div className="text-xs text-[var(--color-mute)] flex flex-wrap gap-x-4 gap-y-1 mt-3">
                        {p.page_count !== null && (
                          <span>
                            {t("home.pagesWritten")}{" "}
                            <strong className="text-[var(--color-ink-soft)]">
                              {p.pages_written}/{p.page_count}
                            </strong>
                          </span>
                        )}
                        {p.references_total > 0 && (
                          <span>
                            {t("home.references")}{" "}
                            <strong className="text-[var(--color-ink-soft)]">
                              {p.references_ready}/{p.references_total}
                            </strong>
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      {deleteTarget && (
        <ConfirmDeleteDialog
          title={t("home.deleteConfirmTitle")}
          body={t("home.deleteConfirmBody", {
            name: deleteTarget.display_name || deleteTarget.title || deleteTarget.name,
          })}
          confirmLabel={t("common.deleteForever")}
          onConfirm={onConfirmDelete}
          onClose={() => setDeleteTarget(null)}
        />
      )}

      {duplicateTarget && (
        <DuplicateProjectDialog
          sourceLabel={
            duplicateTarget.display_name ||
            duplicateTarget.title ||
            duplicateTarget.name
          }
          onClose={() => setDuplicateTarget(null)}
          onConfirm={onConfirmDuplicate}
        />
      )}

      {importFile && (
        <ImportProjectDialog
          fileName={importFile.name}
          onClose={() => setImportFile(null)}
          onConfirm={onConfirmImport}
        />
      )}
    </div>
  );
}
