import { useState } from "react";
import { FiEdit2 } from "react-icons/fi";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { SHOW_COHERENCE_CHECK } from "../featureFlags.js";
import RefineDialog from "./RefineDialog.jsx";
import ConfirmDeleteDialog from "./ConfirmDeleteDialog.jsx";
import ConfirmDialog from "./ConfirmDialog.jsx";

export const SCRIPT_TABS = [
  { id: "characters", label: "Personnages" },
  { id: "locations", label: "Décors" },
  { id: "objects", label: "Objets" },
  { id: "pages", label: "Planches" },
  { id: "covers", label: "Couvertures" },
  ...(SHOW_COHERENCE_CHECK ? [{ id: "coherence", label: "Cohérence" }] : []),
];

const TABS = SCRIPT_TABS;

const DIALOG_TYPES = ["speech", "thought", "shout", "whisper", "narration"];

function csvToList(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

export default function ScriptBrowser({
  project,
  onChanged,
  readOnly = false,
  coherence: coherenceProp,
  onRegeneratePage,
  checking = false,
  coherenceError = null,
  onCheck = null,
  onApplySuggestion = null,
  tab: tabProp,
  onTabChange,
}) {
  // The active sub-section can be driven from outside (left sidebar). When no
  // controlled value is supplied we fall back to a local state and render the
  // in-card tab strip ourselves.
  const [tabState, setTabState] = useState("characters");
  const controlled = tabProp != null;
  const tab = controlled ? tabProp : tabState;
  const setTab = controlled ? onTabChange : setTabState;
  const script = project.script;
  const coherence =
    SHOW_COHERENCE_CHECK && coherenceProp
      ? coherenceProp
      : { dirty: false, issues: [], suggestions: [], flagged_pages: [] };

  const issueCount = coherence.issues?.length ?? 0;
  const isDirty = !!coherence.dirty;

  return (
    <div className="card overflow-hidden">
      <div className="px-5 pt-4 pb-3 flex items-center justify-between gap-3">
        <p className="text-sm text-[var(--color-ink-soft)]">
          {script.characters.length} personnages · {script.locations.length} décors · {script.objects?.length ?? 0}{" "}
          objets · {script.pages.length} planches
        </p>
        {readOnly && <span className="chip chip-peach text-xs">Aperçu — édition désactivée</span>}
      </div>

      {!controlled && (
        <div className="border-b border-[var(--color-line)] flex">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={
                "px-4 py-2.5 text-sm font-medium -mb-px border-b-2 transition-colors inline-flex items-center gap-1 " +
                (tab === t.id
                  ? "border-[var(--color-primary-500)] text-[var(--color-primary-600)]"
                  : "border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-soft)]")
              }
              onClick={() => setTab(t.id)}
            >
              {t.label}
              {t.id === "coherence" && isDirty && (
                <span className="w-2 h-2 rounded-full bg-[var(--color-peach-300)] inline-block" />
              )}
              {t.id === "coherence" && !isDirty && issueCount > 0 && (
                <span className="text-xs text-[var(--color-rose-500)]">{issueCount}</span>
              )}
            </button>
          ))}
        </div>
      )}

      <div className={controlled ? "p-5 border-t border-[var(--color-line)]" : "p-5"}>
        {tab === "characters" && (
          <CharactersList characters={script.characters} onChanged={onChanged} readOnly={readOnly} />
        )}
        {tab === "locations" && (
          <LocationsList locations={script.locations} onChanged={onChanged} readOnly={readOnly} />
        )}
        {tab === "objects" && <ObjectsList objects={script.objects || []} onChanged={onChanged} readOnly={readOnly} />}
        {tab === "pages" && (
          <PagesBrowser
            script={script}
            coherence={SHOW_COHERENCE_CHECK ? coherence : null}
            onChanged={onChanged}
            onRegeneratePage={onRegeneratePage || (() => {})}
            readOnly={readOnly}
          />
        )}
        {tab === "covers" && <CoversView script={script} onChanged={onChanged} readOnly={readOnly} />}
        {SHOW_COHERENCE_CHECK && tab === "coherence" && (
          <CoherenceTabContent
            coherence={coherence}
            checking={checking}
            error={coherenceError}
            readOnly={readOnly}
            onCheck={onCheck}
            onRegeneratePage={onRegeneratePage || (() => {})}
            onApplySuggestion={onApplySuggestion}
          />
        )}
      </div>
    </div>
  );
}

function CharactersList({ characters, onChanged, readOnly = false }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const [refining, setRefining] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [adding, setAdding] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [savingField, setSavingField] = useState(null);
  const [manualError, setManualError] = useState(null);
  async function updateCharacter(character, mutator, fieldKey) {
    const next = structuredClone(character);
    mutator(next);
    setManualError(null);
    setSavingField(fieldKey);
    try {
      await api.updateScriptCharacter(name, character.id, next);
      await onChanged();
    } catch (e) {
      setManualError(e.message);
      throw e;
    } finally {
      setSavingField(null);
    }
  }
  async function addCharacter(character) {
    setManualError(null);
    try {
      await api.addScriptCharacter(name, character);
      await onChanged();
      setAdding(false);
    } catch (e) {
      setManualError(e.message);
      throw e;
    }
  }
  return (
    <div className="space-y-3">
      {!readOnly && (
        <div className="flex justify-end">
          <button className="btn btn-secondary text-sm" onClick={() => setAdding(true)}>
            Ajouter un personnage
          </button>
        </div>
      )}
      {characters.length === 0 && <p className="text-sm text-[var(--color-mute)]">Aucun personnage.</p>}
      <ul className="space-y-3">
        {characters.map((c) => (
          <li key={c.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="font-semibold editable-heading">
                  <EditableText
                    label={`Personnage ${c.id} - Nom`}
                    value={c.name}
                    readOnly={readOnly}
                    multiline={false}
                    saving={savingField === `${c.id}_name`}
                    onSave={(value) =>
                      updateCharacter(
                        c,
                        (draft) => {
                          draft.name = value.trim();
                        },
                        `${c.id}_name`,
                      )
                    }
                  />
                </div>
                <div className="text-xs text-[var(--color-mute)]">id: {c.id}</div>
              </div>
              {!readOnly && (
                <div className="flex gap-1">
                  <button className="btn btn-ghost text-xs" onClick={() => setRegenerating(c)}>
                    ↻ Régénérer
                  </button>
                  <button className="btn btn-ghost text-xs" onClick={() => setRefining(c)}>
                    Retoucher
                  </button>
                  <button className="btn btn-ghost text-xs text-[var(--color-rose-500)]" onClick={() => setDeleting(c)}>
                    Supprimer
                  </button>
                </div>
              )}
            </div>
            <div className="text-sm whitespace-pre-wrap">
              <EditableText
                label={`Personnage ${c.id} - Description physique`}
                value={c.physical_description}
                readOnly={readOnly}
                saving={savingField === `${c.id}_physical_description`}
                onSave={(value) =>
                  updateCharacter(
                    c,
                    (draft) => {
                      draft.physical_description = value;
                    },
                    `${c.id}_physical_description`,
                  )
                }
              />
            </div>
            <div className="text-sm text-[var(--color-ink-soft)] mt-2">
              <span className="text-xs uppercase tracking-wide text-[var(--color-mute)]">Tenue — </span>
              <EditableText
                label={`Personnage ${c.id} - Tenue`}
                value={c.outfit || ""}
                placeholder="Aucune tenue."
                readOnly={readOnly}
                saving={savingField === `${c.id}_outfit`}
                onSave={(value) =>
                  updateCharacter(
                    c,
                    (draft) => {
                      draft.outfit = value.trim() ? value : null;
                    },
                    `${c.id}_outfit`,
                  )
                }
              />
            </div>
          </li>
        ))}
      </ul>
      {manualError && <p className="text-sm text-[var(--color-rose-500)]">Sauvegarde impossible : {manualError}</p>}
      {adding && (
        <AddScriptItemDialog
          type="character"
          title="Ajouter un personnage"
          onClose={() => setAdding(false)}
          onSubmit={addCharacter}
        />
      )}
      {refining && (
        <RefineDialog
          title={`Retoucher « ${refining.name} »`}
          hint="Décrivez la modification à apporter au personnage. Le LLM mettra à jour ce personnage uniquement."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineCharacter(name, refining.id, text);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={`Régénérer « ${regenerating.name} » ?`}
          body="La description de ce personnage sera réécrite par le LLM. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await api.refineCharacter(
              name,
              regenerating.id,
              "Propose une version alternative complète de ce personnage, avec une nouvelle description physique et une nouvelle tenue.",
            );
            await onChanged();
          }}
          onClose={() => setRegenerating(null)}
        />
      )}
      {deleting && (
        <ConfirmDeleteDialog
          title={`Supprimer « ${deleting.name} » ?`}
          body="Ce personnage et toutes ses apparitions vont être retirés du scénario."
          loadPreview={() => api.previewDeleteCharacter(name, deleting.id)}
          confirmLabel="Supprimer"
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            const info = await api.deleteCharacter(name, deleting.id, true);
            await onChanged();
            if (info?.job) {
              navigate(`/projects/${encodeURIComponent(name)}/script`);
            }
          }}
        />
      )}
    </div>
  );
}

function LocationsList({ locations, onChanged, readOnly = false }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const [refining, setRefining] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [adding, setAdding] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [savingField, setSavingField] = useState(null);
  const [manualError, setManualError] = useState(null);
  async function updateLocation(location, mutator, fieldKey) {
    const next = structuredClone(location);
    mutator(next);
    setManualError(null);
    setSavingField(fieldKey);
    try {
      await api.updateScriptLocation(name, location.id, next);
      await onChanged();
    } catch (e) {
      setManualError(e.message);
      throw e;
    } finally {
      setSavingField(null);
    }
  }
  async function addLocation(location) {
    setManualError(null);
    try {
      await api.addScriptLocation(name, location);
      await onChanged();
      setAdding(false);
    } catch (e) {
      setManualError(e.message);
      throw e;
    }
  }
  return (
    <div className="space-y-3">
      {!readOnly && (
        <div className="flex justify-end">
          <button className="btn btn-secondary text-sm" onClick={() => setAdding(true)}>
            Ajouter un decor
          </button>
        </div>
      )}
      {locations.length === 0 && <p className="text-sm text-[var(--color-mute)]">Aucun decor.</p>}
      <ul className="space-y-3">
        {locations.map((l) => (
          <li key={l.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="font-semibold editable-heading">
                  <EditableText
                    label={`Décor ${l.id} - Nom`}
                    value={l.name}
                    readOnly={readOnly}
                    multiline={false}
                    saving={savingField === `${l.id}_name`}
                    onSave={(value) =>
                      updateLocation(
                        l,
                        (draft) => {
                          draft.name = value.trim();
                        },
                        `${l.id}_name`,
                      )
                    }
                  />
                </div>
                <div className="text-xs text-[var(--color-mute)]">id: {l.id}</div>
              </div>
              {!readOnly && (
                <div className="flex gap-1">
                  <button className="btn btn-ghost text-xs" onClick={() => setRegenerating(l)}>
                    ↻ Régénérer
                  </button>
                  <button className="btn btn-ghost text-xs" onClick={() => setRefining(l)}>
                    Retoucher
                  </button>
                  <button className="btn btn-ghost text-xs text-[var(--color-rose-500)]" onClick={() => setDeleting(l)}>
                    Supprimer
                  </button>
                </div>
              )}
            </div>
            <div className="text-sm whitespace-pre-wrap">
              <EditableText
                label={`Décor ${l.id} - Description`}
                value={l.description}
                readOnly={readOnly}
                saving={savingField === `${l.id}_description`}
                onSave={(value) =>
                  updateLocation(
                    l,
                    (draft) => {
                      draft.description = value;
                    },
                    `${l.id}_description`,
                  )
                }
              />
            </div>
          </li>
        ))}
      </ul>
      {manualError && <p className="text-sm text-[var(--color-rose-500)]">Sauvegarde impossible : {manualError}</p>}
      {adding && (
        <AddScriptItemDialog
          type="location"
          title="Ajouter un decor"
          onClose={() => setAdding(false)}
          onSubmit={addLocation}
        />
      )}
      {refining && (
        <RefineDialog
          title={`Retoucher « ${refining.name} »`}
          hint="Décrivez la modification à apporter au décor. Le LLM mettra à jour ce décor uniquement."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineLocation(name, refining.id, text);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={`Régénérer « ${regenerating.name} » ?`}
          body="La description de ce décor sera réécrite par le LLM. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await api.refineLocation(
              name,
              regenerating.id,
              "Propose une version alternative complète de ce décor, avec une nouvelle description.",
            );
            await onChanged();
          }}
          onClose={() => setRegenerating(null)}
        />
      )}
      {deleting && (
        <ConfirmDeleteDialog
          title={`Supprimer « ${deleting.name} » ?`}
          body="Ce décor et toutes les scènes qui s'y déroulent vont être retirés du scénario."
          loadPreview={() => api.previewDeleteLocation(name, deleting.id)}
          confirmLabel="Supprimer"
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            const info = await api.deleteLocation(name, deleting.id, true);
            await onChanged();
            if (info?.job) {
              navigate(`/projects/${encodeURIComponent(name)}/script`);
            }
          }}
        />
      )}
    </div>
  );
}

function ObjectsList({ objects, onChanged, readOnly = false }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const [refining, setRefining] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [adding, setAdding] = useState(false);
  const [regenerating, setRegenerating] = useState(null);
  const [savingField, setSavingField] = useState(null);
  const [manualError, setManualError] = useState(null);
  async function updateObject(obj, mutator, fieldKey) {
    const next = structuredClone(obj);
    mutator(next);
    setManualError(null);
    setSavingField(fieldKey);
    try {
      await api.updateScriptObject(name, obj.id, next);
      await onChanged();
    } catch (e) {
      setManualError(e.message);
      throw e;
    } finally {
      setSavingField(null);
    }
  }
  async function addObject(obj) {
    setManualError(null);
    try {
      await api.addScriptObject(name, obj);
      await onChanged();
      setAdding(false);
    } catch (e) {
      setManualError(e.message);
      throw e;
    }
  }
  return (
    <div className="space-y-3">
      {!readOnly && (
        <div className="flex justify-end">
          <button className="btn btn-secondary text-sm" onClick={() => setAdding(true)}>
            Ajouter un objet
          </button>
        </div>
      )}
      {objects.length === 0 && (
        <p className="text-sm text-[var(--color-mute)]">Aucun objet / produit / reference pour ce projet.</p>
      )}
      <ul className="space-y-3">
        {objects.map((o) => (
          <li key={o.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="font-semibold editable-heading">
                  <EditableText
                    label={`Objet ${o.id} - Nom`}
                    value={o.name}
                    readOnly={readOnly}
                    multiline={false}
                    saving={savingField === `${o.id}_name`}
                    onSave={(value) =>
                      updateObject(
                        o,
                        (draft) => {
                          draft.name = value.trim();
                        },
                        `${o.id}_name`,
                      )
                    }
                  />
                </div>
                <div className="text-xs text-[var(--color-mute)]">id: {o.id}</div>
              </div>
              {!readOnly && (
                <div className="flex gap-1">
                  <button className="btn btn-ghost text-xs" onClick={() => setRegenerating(o)}>
                    ↻ Régénérer
                  </button>
                  <button className="btn btn-ghost text-xs" onClick={() => setRefining(o)}>
                    Retoucher
                  </button>
                  <button className="btn btn-ghost text-xs text-[var(--color-rose-500)]" onClick={() => setDeleting(o)}>
                    Supprimer
                  </button>
                </div>
              )}
            </div>
            <div className="text-sm whitespace-pre-wrap">
              <EditableText
                label={`Objet ${o.id} - Description`}
                value={o.description}
                readOnly={readOnly}
                saving={savingField === `${o.id}_description`}
                onSave={(value) =>
                  updateObject(
                    o,
                    (draft) => {
                      draft.description = value;
                    },
                    `${o.id}_description`,
                  )
                }
              />
            </div>
          </li>
        ))}
      </ul>
      {manualError && <p className="text-sm text-[var(--color-rose-500)]">Sauvegarde impossible : {manualError}</p>}
      {adding && (
        <AddScriptItemDialog
          type="object"
          title="Ajouter un objet"
          onClose={() => setAdding(false)}
          onSubmit={addObject}
        />
      )}
      {refining && (
        <RefineDialog
          title={`Retoucher « ${refining.name} »`}
          hint="Décrivez la modification à apporter à l'objet. Le LLM mettra à jour cet objet uniquement."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineObject(name, refining.id, text);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={`Régénérer « ${regenerating.name} » ?`}
          body="La description de cet objet sera réécrite par le LLM. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await api.refineObject(
              name,
              regenerating.id,
              "Propose une version alternative complète de cet objet, avec une nouvelle description.",
            );
            await onChanged();
          }}
          onClose={() => setRegenerating(null)}
        />
      )}
      {deleting && (
        <ConfirmDeleteDialog
          title={`Supprimer « ${deleting.name} » ?`}
          body="Cet objet et toutes les cases qui s'y réfèrent vont être retirés du scénario."
          loadPreview={() => api.previewDeleteObject(name, deleting.id)}
          confirmLabel="Supprimer"
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            const info = await api.deleteObject(name, deleting.id, true);
            await onChanged();
            if (info?.job) {
              navigate(`/projects/${encodeURIComponent(name)}/script`);
            }
          }}
        />
      )}
    </div>
  );
}

function PagesBrowser({ script, coherence, onChanged, onRegeneratePage, readOnly = false }) {
  const { name } = useParams();
  const [idx, setIdx] = useState(0);
  const [refining, setRefining] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [savingField, setSavingField] = useState(null);
  const [manualError, setManualError] = useState(null);
  const pages = script.pages;
  if (pages.length === 0) return <p className="text-sm text-[var(--color-mute)]">Aucune planche.</p>;
  const currentIdx = Math.min(idx, pages.length - 1);
  const page = pages[currentIdx];
  const pageCoherenceIssues = (coherence?.issues || []).filter((issue) => issue.page_number === page.page_number);
  const pageCoherenceSuggestions = (coherence?.suggestions || []).filter((s) => s.page_number === page.page_number);

  async function saveManualPage(nextPage, fieldKey) {
    setManualError(null);
    setSavingField(fieldKey);
    try {
      await api.updateScriptPage(name, page.page_number, nextPage);
      await onChanged();
    } catch (e) {
      setManualError(e.message);
      throw e;
    } finally {
      setSavingField(null);
    }
  }

  function updatePage(mutator, fieldKey) {
    const nextPage = structuredClone(page);
    mutator(nextPage);
    return saveManualPage(nextPage, fieldKey);
  }

  return (
    <div>
      <PageNavigation idx={currentIdx} pageCount={pages.length} onChange={setIdx} className="mb-3" />

      <div className="script-page-reader">
        {pageCoherenceIssues.length > 0 && (
          <div className="mb-3 rounded-lg border border-[var(--color-rose-500)]/30 bg-white p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold text-[var(--color-rose-500)]">
                  Erreurs de cohérence sur cette planche
                </p>
                <ul className="mt-1 list-disc pl-5 text-xs text-[var(--color-ink-soft)]">
                  {pageCoherenceIssues.map((issue, issueIndex) => (
                    <li key={`${issue.kind}_${issue.target}_${issueIndex}`}>{issue.message}</li>
                  ))}
                </ul>
              </div>
              {!readOnly && (
                <button className="btn btn-secondary text-xs" onClick={() => onRegeneratePage(page.page_number)}>
                  Régénérer la planche
                </button>
              )}
            </div>
          </div>
        )}
        {pageCoherenceSuggestions.length > 0 && (
          <div className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-paper-soft)] p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold">Suggestions pour cette planche</p>
                <ul className="mt-1 list-disc pl-5 text-xs text-[var(--color-ink-soft)]">
                  {pageCoherenceSuggestions.map((s, i) => (
                    <li key={`${s.kind}_${s.target}_${i}`}>{s.message}</li>
                  ))}
                </ul>
              </div>
              {!readOnly && (
                <button className="btn btn-ghost text-xs" onClick={() => onRegeneratePage(page.page_number)}>
                  Améliorer la planche
                </button>
              )}
            </div>
          </div>
        )}
        {!readOnly && (
          <div className="script-page-actions">
            <button className="btn btn-ghost text-xs" onClick={() => setRegenerating(true)}>
              ↻ Régénérer
            </button>
            <button className="btn btn-ghost text-xs" onClick={() => setRefining(true)}>
              Retoucher la planche
            </button>
          </div>
        )}

        <div className="script-layout-block">
          <div className="min-w-0">
            <p className="script-layout-title">Découpage</p>
            <EditableText
              label="Découpage"
              value={page.layout || ""}
              placeholder="Aucun découpage renseigné."
              readOnly={readOnly}
              saving={savingField === "layout"}
              onSave={(value) =>
                updatePage((draft) => {
                  draft.layout = value;
                }, "layout")
              }
            />
          </div>
        </div>
        <ol className="space-y-4">
          {page.panels.map((p, panelIndex) => (
            <li key={p.panel_number} className="script-panel">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div>
                  <h3 className="text-base font-semibold">Case {p.panel_number}</h3>
                </div>
                {p.sound_effects?.length > 0 && <span className="script-sfx-chip">{p.sound_effects.join(", ")}</span>}
              </div>

              <dl className="script-panel-facts">
                <div>
                  <dt>Taille</dt>
                  <dd>
                    <EditableText
                      label={`Case ${p.panel_number} - Taille`}
                      value={p.size || ""}
                      placeholder="medium"
                      readOnly={readOnly}
                      multiline={false}
                      saving={savingField === `panel_${p.panel_number}_size`}
                      onSave={(value) =>
                        updatePage((draft) => {
                          draft.panels[panelIndex].size = value.trim() ? value.trim() : null;
                        }, `panel_${p.panel_number}_size`)
                      }
                    />
                  </dd>
                </div>
                <div>
                  <dt>Cadrage</dt>
                  <dd>
                    <EditableText
                      label={`Case ${p.panel_number} - Cadrage`}
                      value={p.shot || ""}
                      placeholder="medium shot"
                      readOnly={readOnly}
                      multiline={false}
                      saving={savingField === `panel_${p.panel_number}_shot`}
                      onSave={(value) =>
                        updatePage((draft) => {
                          draft.panels[panelIndex].shot = value.trim() ? value.trim() : null;
                        }, `panel_${p.panel_number}_shot`)
                      }
                    />
                  </dd>
                </div>
                <div>
                  <dt>Lieu</dt>
                  <dd>
                    <EditableText
                      label={`Case ${p.panel_number} - Lieu`}
                      value={p.location || ""}
                      placeholder="Non précisé"
                      readOnly={readOnly}
                      multiline={false}
                      saving={savingField === `panel_${p.panel_number}_location`}
                      onSave={(value) =>
                        updatePage((draft) => {
                          draft.panels[panelIndex].location = value.trim();
                        }, `panel_${p.panel_number}_location`)
                      }
                    />
                  </dd>
                </div>
                <div>
                  <dt>Personnages</dt>
                  <dd>
                    <EditableText
                      label={`Case ${p.panel_number} - Personnages`}
                      value={(p.characters || []).join(", ")}
                      placeholder="Aucun"
                      readOnly={readOnly}
                      multiline={false}
                      saving={savingField === `panel_${p.panel_number}_characters`}
                      onSave={(value) =>
                        updatePage((draft) => {
                          draft.panels[panelIndex].characters = csvToList(value);
                        }, `panel_${p.panel_number}_characters`)
                      }
                    />
                  </dd>
                </div>
                <div>
                  <dt>Objets</dt>
                  <dd>
                    <EditableText
                      label={`Case ${p.panel_number} - Objets`}
                      value={(p.objects || []).join(", ")}
                      placeholder="Aucun"
                      readOnly={readOnly}
                      multiline={false}
                      saving={savingField === `panel_${p.panel_number}_objects`}
                      onSave={(value) =>
                        updatePage((draft) => {
                          draft.panels[panelIndex].objects = csvToList(value);
                        }, `panel_${p.panel_number}_objects`)
                      }
                    />
                  </dd>
                </div>
              </dl>

              <section className="script-section">
                <h4>Scène</h4>
                <EditableText
                  label={`Case ${p.panel_number} - Scène`}
                  value={p.scene_description || ""}
                  readOnly={readOnly}
                  saving={savingField === `panel_${p.panel_number}_scene`}
                  onSave={(value) =>
                    updatePage((draft) => {
                      draft.panels[panelIndex].scene_description = value;
                    }, `panel_${p.panel_number}_scene`)
                  }
                />
              </section>

              <section className="script-section script-narration">
                <h4>Narration</h4>
                <EditableText
                  label={`Case ${p.panel_number} - Narration`}
                  value={p.narration || ""}
                  placeholder="Aucune narration."
                  readOnly={readOnly}
                  saving={savingField === `panel_${p.panel_number}_narration`}
                  onSave={(value) =>
                    updatePage((draft) => {
                      draft.panels[panelIndex].narration = value.trim() ? value : null;
                    }, `panel_${p.panel_number}_narration`)
                  }
                />
              </section>

              <section className="script-section">
                <h4>SFX</h4>
                <EditableText
                  label={`Case ${p.panel_number} - SFX`}
                  value={(p.sound_effects || []).join(", ")}
                  placeholder="Aucun SFX."
                  readOnly={readOnly}
                  saving={savingField === `panel_${p.panel_number}_sfx`}
                  onSave={(value) =>
                    updatePage((draft) => {
                      draft.panels[panelIndex].sound_effects = csvToList(value);
                    }, `panel_${p.panel_number}_sfx`)
                  }
                />
              </section>

              {p.dialogs?.length > 0 && (
                <section className="script-section">
                  <h4>Dialogues</h4>
                  <ul className="space-y-2">
                    {p.dialogs.map((d, i) => (
                      <li key={i} className="script-dialog">
                        <div className="script-dialog-header">
                          <div>
                            <span className="script-dialog-label">Personnage</span>
                            <EditableText
                              label={`Case ${p.panel_number} - Dialogue ${i + 1} - Personnage`}
                              value={d.speaker || ""}
                              readOnly={readOnly}
                              multiline={false}
                              saving={savingField === `panel_${p.panel_number}_dialog_${i}_speaker`}
                              onSave={(value) =>
                                updatePage((draft) => {
                                  draft.panels[panelIndex].dialogs[i].speaker = value.trim();
                                }, `panel_${p.panel_number}_dialog_${i}_speaker`)
                              }
                            />
                          </div>
                          <div>
                            <span className="script-dialog-label">Type</span>
                            <EditableSelect
                              label={`Case ${p.panel_number} - Dialogue ${i + 1} - Type`}
                              value={d.type || "speech"}
                              options={DIALOG_TYPES}
                              readOnly={readOnly}
                              saving={savingField === `panel_${p.panel_number}_dialog_${i}_type`}
                              onSave={(value) =>
                                updatePage((draft) => {
                                  draft.panels[panelIndex].dialogs[i].type = value;
                                }, `panel_${p.panel_number}_dialog_${i}_type`)
                              }
                            />
                          </div>
                        </div>
                        <EditableText
                          label={`Case ${p.panel_number} - Dialogue ${i + 1} - Texte`}
                          value={d.text || ""}
                          readOnly={readOnly}
                          saving={savingField === `panel_${p.panel_number}_dialog_${i}`}
                          onSave={(value) =>
                            updatePage((draft) => {
                              draft.panels[panelIndex].dialogs[i].text = value;
                            }, `panel_${p.panel_number}_dialog_${i}`)
                          }
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </li>
          ))}
        </ol>
        {manualError && (
          <p className="text-sm text-[var(--color-rose-500)] mt-4">Sauvegarde impossible : {manualError}</p>
        )}
      </div>

      <PageNavigation idx={currentIdx} pageCount={pages.length} onChange={setIdx} className="mt-3" />

      {refining && (
        <RefineDialog
          title={`Retoucher la planche ${page.page_number}`}
          hint="Décrivez le changement à apporter à cette planche. Le LLM réécrira uniquement cette page."
          extraField={{
            type: "checkbox",
            id: "cascade",
            label:
              "Régénérer aussi les planches suivantes pour cohérence (recommandé pour des changements importants).",
          }}
          onClose={() => setRefining(false)}
          onSubmit={async (text, extras) => {
            await api.refinePage(name, page.page_number, text, !!extras.cascade);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={`Régénérer la planche ${page.page_number} ?`}
          body="Le scénario de cette planche sera réécrit par le LLM avec de nouvelles idées. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await api.refinePage(
              name,
              page.page_number,
              "Réécris cette planche avec de nouvelles idées pour les cases, les dialogues et la mise en scène.",
            );
            await onChanged();
          }}
          onClose={() => setRegenerating(false)}
        />
      )}
    </div>
  );
}

function buildReferencePrompt(...parts) {
  return parts
    .map((part) => (part || "").trim())
    .filter(Boolean)
    .join(" ");
}

function AddScriptItemDialog({ type, title, onClose, onSubmit }) {
  const isCharacter = type === "character";
  const [draft, setDraft] = useState({
    id: "",
    name: "",
    description: "",
    outfit: "",
    referencePrompt: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  function updateField(field, value) {
    setDraft((current) => ({ ...current, [field]: value }));
  }

  async function submit(event) {
    event.preventDefault();
    const id = draft.id.trim();
    const name = draft.name.trim();
    const description = draft.description.trim();
    const outfit = draft.outfit.trim();
    const referencePrompt = draft.referencePrompt.trim() || buildReferencePrompt(description, outfit, name);
    if (!id || !name || !description) {
      setError("L'id, le nom et la description sont obligatoires.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload = isCharacter
        ? {
            id,
            name,
            physical_description: description,
            outfit: outfit || null,
            reference_prompt: referencePrompt,
          }
        : {
            id,
            name,
            description,
            reference_prompt: referencePrompt,
          };
      await onSubmit(payload);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <EditValueDialog title={title}>
      <form className="space-y-3" onSubmit={submit}>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <label className="text-sm font-medium">
            ID
            <input
              autoFocus
              className="input mt-1"
              value={draft.id}
              onChange={(event) => updateField("id", event.target.value)}
              disabled={saving}
              placeholder={isCharacter ? "perso_2" : type === "location" ? "decor_2" : "objet_2"}
            />
          </label>
          <label className="text-sm font-medium">
            Nom
            <input
              className="input mt-1"
              value={draft.name}
              onChange={(event) => updateField("name", event.target.value)}
              disabled={saving}
            />
          </label>
        </div>
        <label className="text-sm font-medium block">
          {isCharacter ? "Description physique" : "Description"}
          <textarea
            className="textarea editable-modal-textarea mt-1"
            value={draft.description}
            onChange={(event) => updateField("description", event.target.value)}
            disabled={saving}
          />
        </label>
        {isCharacter && (
          <label className="text-sm font-medium block">
            Tenue
            <input
              className="input mt-1"
              value={draft.outfit}
              onChange={(event) => updateField("outfit", event.target.value)}
              disabled={saving}
            />
          </label>
        )}
        <label className="text-sm font-medium block">
          Prompt image de reference
          <textarea
            className="textarea editable-modal-textarea mt-1"
            value={draft.referencePrompt}
            onChange={(event) => updateField("referencePrompt", event.target.value)}
            disabled={saving}
            placeholder="Si vide, il sera repris depuis la description."
          />
        </label>
        {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
        <div className="editable-actions">
          <button type="button" className="btn btn-ghost text-xs" onClick={onClose} disabled={saving}>
            Annuler
          </button>
          <button type="submit" className="btn btn-primary text-xs" disabled={saving}>
            {saving ? "Ajout..." : "Ajouter"}
          </button>
        </div>
      </form>
    </EditValueDialog>
  );
}

function EditableText({
  label = "Champ",
  value,
  onSave,
  placeholder = "Texte vide.",
  readOnly = false,
  saving = false,
  multiline = true,
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || "");

  function startEdit() {
    setDraft(value || "");
    setEditing(true);
  }

  async function submit() {
    await onSave(draft);
    setEditing(false);
  }

  return (
    <div className="editable-text editable-text-read">
      {!readOnly && (
        <div className="editable-toolbar">
          <button
            type="button"
            className="editable-edit-button"
            onClick={startEdit}
            disabled={saving}
            title="Modifier"
            aria-label="Modifier ce texte"
          >
            <FiEdit2 aria-hidden="true" />
          </button>
        </div>
      )}
      <p className={value ? "" : "text-[var(--color-mute)] italic"}>{value || placeholder}</p>
      {editing && (
        <EditValueDialog title={label}>
          {multiline ? (
            <textarea
              autoFocus
              className="textarea editable-modal-textarea"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={saving}
            />
          ) : (
            <input
              autoFocus
              className="input"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              disabled={saving}
            />
          )}
          <div className="editable-actions">
            <button
              type="button"
              className="btn btn-ghost text-xs"
              onClick={() => {
                setDraft(value || "");
                setEditing(false);
              }}
              disabled={saving}
            >
              Annuler
            </button>
            <button type="button" className="btn btn-primary text-xs" onClick={submit} disabled={saving}>
              {saving ? "Sauvegarde..." : "Sauvegarder"}
            </button>
          </div>
        </EditValueDialog>
      )}
    </div>
  );
}

function EditableSelect({ label = "Champ", value, options, onSave, readOnly = false, saving = false }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value || options[0]);

  async function submit() {
    await onSave(draft);
    setEditing(false);
  }

  return (
    <div className="editable-text editable-text-read">
      {!readOnly && (
        <div className="editable-toolbar">
          <button
            type="button"
            className="editable-edit-button"
            onClick={() => {
              setDraft(value || options[0]);
              setEditing(true);
            }}
            disabled={saving}
            title="Modifier"
            aria-label="Modifier ce type"
          >
            <FiEdit2 aria-hidden="true" />
          </button>
        </div>
      )}
      <p>{value}</p>
      {editing && (
        <EditValueDialog title={label}>
          <select
            autoFocus
            className="select"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={saving}
          >
            {options.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
          <div className="editable-actions">
            <button
              type="button"
              className="btn btn-ghost text-xs"
              onClick={() => {
                setDraft(value || options[0]);
                setEditing(false);
              }}
              disabled={saving}
            >
              Annuler
            </button>
            <button type="button" className="btn btn-primary text-xs" onClick={submit} disabled={saving}>
              {saving ? "Sauvegarde..." : "Sauvegarder"}
            </button>
          </div>
        </EditValueDialog>
      )}
    </div>
  );
}

function EditValueDialog({ title, children }) {
  return (
    <div className="editable-modal-positioner">
      <div className="editable-modal" role="dialog" aria-modal="true" aria-label={`Modifier ${title}`}>
        <div className="editable-modal-header">
          <p className="editable-modal-kicker">Modifier</p>
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        {children}
      </div>
    </div>
  );
}

function CoherenceTabContent({ coherence, checking, error, readOnly, onCheck, onRegeneratePage, onApplySuggestion }) {
  const [confirmSuggestion, setConfirmSuggestion] = useState(null);
  const issues = coherence.issues || [];
  const suggestions = coherence.suggestions || [];
  const dirty = !!coherence.dirty;

  const issuesByPage = issues.reduce((acc, issue) => {
    const pageNumber = issue.page_number;
    if (!pageNumber) return acc;
    acc[pageNumber] = acc[pageNumber] || [];
    acc[pageNumber].push(issue);
    return acc;
  }, {});

  const suggestionsByPage = suggestions.reduce((acc, s) => {
    const pageNumber = s.page_number;
    if (!pageNumber) return acc;
    acc[pageNumber] = acc[pageNumber] || [];
    acc[pageNumber].push(s);
    return acc;
  }, {});

  const globalSuggestions = suggestions.filter((s) => !s.page_number);

  const statusText = dirty
    ? "Des modifications manuelles sont en attente de vérification."
    : issues.length > 0
      ? `${issues.length} erreur(s) détectée(s).`
      : suggestions.length > 0
        ? `Aucune erreur · ${suggestions.length} suggestion(s).`
        : coherence.checked_at
          ? "Dernière vérification sans erreur ni suggestion."
          : "Aucune vérification lancée depuis les dernières modifications.";

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-[var(--color-mute)]">{statusText}</p>
        <button
          type="button"
          className={"btn text-sm " + (dirty ? "btn-primary" : "btn-ghost")}
          onClick={onCheck}
          disabled={readOnly || checking || !dirty || !onCheck}
          title={!dirty ? "Aucune modification manuelle non vérifiée" : "Vérifier la cohérence du scénario"}
        >
          {checking ? "Vérification..." : "Vérifier la cohérence"}
        </button>
      </div>
      {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}

      {Object.keys(issuesByPage).length > 0 && (
        <div className="space-y-2">
          {Object.entries(issuesByPage).map(([pageNumber, pageIssues]) => (
            <div
              key={pageNumber}
              className="rounded-md border border-[var(--color-rose-500)]/30 bg-[var(--color-paper-soft)] p-2"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm font-semibold text-[var(--color-rose-500)]">Planche {pageNumber} — erreur</p>
                  <ul className="mt-1 list-disc pl-5 text-xs text-[var(--color-ink-soft)]">
                    {pageIssues.map((issue, index) => (
                      <li key={`${issue.kind}_${issue.target}_${index}`}>{issue.message}</li>
                    ))}
                  </ul>
                </div>
                {!readOnly && (
                  <button
                    type="button"
                    className="btn btn-secondary text-xs"
                    onClick={() => onRegeneratePage(Number(pageNumber))}
                  >
                    Régénérer la planche
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {Object.keys(suggestionsByPage).length > 0 && (
        <div className="space-y-2">
          {Object.entries(suggestionsByPage).map(([pageNumber, pageSuggestions]) => (
            <div
              key={pageNumber}
              className="rounded-md border border-[var(--color-line)] bg-[var(--color-paper-soft)] p-2"
            >
              <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <p className="text-sm font-semibold">Planche {pageNumber} — suggestion</p>
                  <ul className="mt-1 list-disc pl-5 text-xs text-[var(--color-ink-soft)]">
                    {pageSuggestions.map((s, index) => (
                      <li key={`${s.kind}_${s.target}_${index}`}>{s.message}</li>
                    ))}
                  </ul>
                </div>
                {!readOnly && (
                  <button
                    type="button"
                    className="btn btn-ghost text-xs"
                    onClick={() => onRegeneratePage(Number(pageNumber))}
                  >
                    Améliorer la planche
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {globalSuggestions.length > 0 && (
        <div className="rounded-md border border-[var(--color-line)] bg-[var(--color-paper-soft)] p-2">
          <p className="text-sm font-semibold">Suggestions générales</p>
          <ul className="mt-2 space-y-2">
            {globalSuggestions.map((s, index) => (
              <li key={`global_${index}`} className="flex items-start justify-between gap-2">
                <span className="text-xs text-[var(--color-ink-soft)] flex-1">{s.message}</span>
                {!readOnly && onApplySuggestion && (
                  <button
                    type="button"
                    className="btn btn-ghost text-xs flex-shrink-0"
                    onClick={() => setConfirmSuggestion(s)}
                  >
                    Appliquer cette suggestion
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {issues.length === 0 && suggestions.length === 0 && !dirty && (
        <p className="text-sm text-[var(--color-mute)]">
          {coherence.checked_at
            ? "Aucune erreur ni suggestion détectée lors de la dernière vérification."
            : "Lancez une vérification pour analyser la cohérence du scénario."}
        </p>
      )}

      {confirmSuggestion && (
        <ConfirmDialog
          title="Appliquer cette suggestion ?"
          body="Le LLM va analyser le scénario et appliquer cette modification. Selon la nature du changement, des planches, des personnages ou des décors pourront être mis à jour. Cette action consomme des crédits API."
          confirmLabel="Appliquer"
          onConfirm={async () => {
            await onApplySuggestion(confirmSuggestion.message);
          }}
          onClose={() => setConfirmSuggestion(null)}
        />
      )}
    </div>
  );
}

function PageNavigation({ idx, pageCount, onChange, className = "" }) {
  return (
    <div className={"flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between " + className}>
      <button
        className="btn btn-ghost text-sm"
        disabled={idx === 0}
        onClick={() => onChange((i) => Math.max(0, i - 1))}
      >
        ← Précédente
      </button>
      <div className="flex items-center justify-center gap-2 text-sm font-medium">
        <span>Planche</span>
        <select className="select page-select" value={idx} onChange={(event) => onChange(Number(event.target.value))}>
          {Array.from({ length: pageCount }, (_, i) => (
            <option key={i} value={i}>
              {i + 1}
            </option>
          ))}
        </select>
        <span>/ {pageCount}</span>
      </div>
      <button
        className="btn btn-ghost text-sm"
        disabled={idx === pageCount - 1}
        onClick={() => onChange((i) => Math.min(pageCount - 1, i + 1))}
      >
        Suivante →
      </button>
    </div>
  );
}

function CoversView({ script, onChanged, readOnly = false }) {
  const { name } = useParams();
  const [refining, setRefining] = useState(null);
  const [regenerating, setRegenerating] = useState(null);
  const [savingField, setSavingField] = useState(null);
  const [manualError, setManualError] = useState(null);

  async function updateCover(mutator, fieldKey) {
    const next = structuredClone(script.cover);
    mutator(next);
    setManualError(null);
    setSavingField(fieldKey);
    try {
      await api.updateScriptCover(name, next);
      await onChanged();
    } catch (e) {
      setManualError(e.message);
      throw e;
    } finally {
      setSavingField(null);
    }
  }

  async function updateBackCover(mutator, fieldKey) {
    const next = structuredClone(script.back_cover);
    mutator(next);
    setManualError(null);
    setSavingField(fieldKey);
    try {
      await api.updateScriptBackCover(name, next);
      await onChanged();
    } catch (e) {
      setManualError(e.message);
      throw e;
    } finally {
      setSavingField(null);
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {script.cover && (
        <div className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="font-semibold">Couverture</h3>
            {!readOnly && (
              <div className="flex gap-1">
                <button className="btn btn-ghost text-xs" onClick={() => setRegenerating("cover")}>
                  ↻ Régénérer
                </button>
                <button className="btn btn-ghost text-xs" onClick={() => setRefining("cover")}>
                  Retoucher
                </button>
              </div>
            )}
          </div>
          <div className="text-sm whitespace-pre-wrap">
            <EditableText
              label="Couverture - Illustration"
              value={script.cover.scene_description}
              readOnly={readOnly}
              saving={savingField === "cover_scene"}
              onSave={(value) =>
                updateCover((draft) => {
                  draft.scene_description = value;
                }, "cover_scene")
              }
            />
          </div>
          {script.cover.title_placement && (
            <p className="text-xs text-[var(--color-ink-soft)] mt-2">
              <span className="uppercase tracking-wide text-[var(--color-mute)]">Placement du titre — </span>
              <EditableText
                label="Couverture - Placement du titre"
                value={script.cover.title_placement || ""}
                placeholder="Non précisé."
                readOnly={readOnly}
                saving={savingField === "cover_title_placement"}
                onSave={(value) =>
                  updateCover((draft) => {
                    draft.title_placement = value.trim() ? value : null;
                  }, "cover_title_placement")
                }
              />
            </p>
          )}
          {script.cover.subtitle && (
            <p className="text-sm mt-2">
              <strong>Sous-titre&nbsp;:</strong>{" "}
              <EditableText
                label="Couverture - Sous-titre"
                value={script.cover.subtitle || ""}
                readOnly={readOnly}
                multiline={false}
                saving={savingField === "cover_subtitle"}
                onSave={(value) =>
                  updateCover((draft) => {
                    draft.subtitle = value.trim() ? value : null;
                  }, "cover_subtitle")
                }
              />
            </p>
          )}
          {script.cover.tagline && (
            <div className="text-sm italic mt-2">
              <EditableText
                label="Couverture - Tagline"
                value={script.cover.tagline || ""}
                readOnly={readOnly}
                saving={savingField === "cover_tagline"}
                onSave={(value) =>
                  updateCover((draft) => {
                    draft.tagline = value.trim() ? value : null;
                  }, "cover_tagline")
                }
              />
            </div>
          )}
        </div>
      )}
      {script.back_cover && (
        <div className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="font-semibold">4ᵉ de couverture</h3>
            {!readOnly && (
              <div className="flex gap-1">
                <button className="btn btn-ghost text-xs" onClick={() => setRegenerating("back_cover")}>
                  ↻ Régénérer
                </button>
                <button className="btn btn-ghost text-xs" onClick={() => setRefining("back_cover")}>
                  Retoucher
                </button>
              </div>
            )}
          </div>
          <div className="text-sm whitespace-pre-wrap">
            <EditableText
              label="4e de couverture - Synopsis"
              value={script.back_cover.synopsis_blurb}
              readOnly={readOnly}
              saving={savingField === "back_synopsis"}
              onSave={(value) =>
                updateBackCover((draft) => {
                  draft.synopsis_blurb = value;
                }, "back_synopsis")
              }
            />
          </div>
          {script.back_cover.scene_description && (
            <p className="text-xs text-[var(--color-ink-soft)] mt-2">
              <span className="uppercase tracking-wide text-[var(--color-mute)]">Illustration — </span>
              <EditableText
                label="4e de couverture - Illustration"
                value={script.back_cover.scene_description || ""}
                readOnly={readOnly}
                saving={savingField === "back_scene"}
                onSave={(value) =>
                  updateBackCover((draft) => {
                    draft.scene_description = value.trim() ? value : null;
                  }, "back_scene")
                }
              />
            </p>
          )}
          {script.back_cover.tagline && (
            <div className="text-sm italic mt-2">
              <EditableText
                label="4e de couverture - Tagline"
                value={script.back_cover.tagline || ""}
                readOnly={readOnly}
                saving={savingField === "back_tagline"}
                onSave={(value) =>
                  updateBackCover((draft) => {
                    draft.tagline = value.trim() ? value : null;
                  }, "back_tagline")
                }
              />
            </div>
          )}
          {script.back_cover.layout_notes && (
            <div className="text-xs text-[var(--color-mute)] mt-2">
              <EditableText
                label="4e de couverture - Notes de mise en page"
                value={script.back_cover.layout_notes || ""}
                readOnly={readOnly}
                saving={savingField === "back_layout_notes"}
                onSave={(value) =>
                  updateBackCover((draft) => {
                    draft.layout_notes = value.trim() ? value : null;
                  }, "back_layout_notes")
                }
              />
            </div>
          )}
        </div>
      )}
      {!script.cover && !script.back_cover && (
        <p className="text-sm text-[var(--color-mute)]">Aucune couverture définie.</p>
      )}
      {manualError && <p className="text-sm text-[var(--color-rose-500)]">Sauvegarde impossible : {manualError}</p>}

      {refining === "cover" && (
        <RefineDialog
          title="Retoucher la couverture"
          hint="Décrivez la modification à apporter à la couverture (illustration, placement du titre, tagline…)."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineCover(name, text);
            await onChanged();
          }}
        />
      )}
      {refining === "back_cover" && (
        <RefineDialog
          title="Retoucher la 4ᵉ de couverture"
          hint="Décrivez la modification à apporter (synopsis, tagline, mise en page…)."
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineBackCover(name, text);
            await onChanged();
          }}
        />
      )}
      {regenerating === "cover" && (
        <ConfirmDialog
          title="Régénérer la couverture ?"
          body="La description de la couverture sera réécrite par le LLM. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await api.refineCover(
              name,
              "Propose une version alternative complète de la couverture, avec une nouvelle mise en scène et un nouveau placement du titre.",
            );
            await onChanged();
          }}
          onClose={() => setRegenerating(null)}
        />
      )}
      {regenerating === "back_cover" && (
        <ConfirmDialog
          title="Régénérer la 4ᵉ de couverture ?"
          body="Le synopsis et la mise en page de la 4ᵉ de couverture seront réécrits par le LLM. Cette action consomme des crédits API."
          confirmLabel="Régénérer"
          onConfirm={async () => {
            await api.refineBackCover(
              name,
              "Propose une version alternative complète de la 4ᵉ de couverture, avec un nouveau synopsis et une nouvelle tagline.",
            );
            await onChanged();
          }}
          onClose={() => setRegenerating(null)}
        />
      )}
    </div>
  );
}
