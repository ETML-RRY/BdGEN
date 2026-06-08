import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { FiEdit2 } from "react-icons/fi";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { SHOW_COHERENCE_CHECK } from "../featureFlags.js";
import RefineDialog from "./RefineDialog.jsx";
import ConfirmDeleteDialog from "./ConfirmDeleteDialog.jsx";
import ConfirmDialog from "./ConfirmDialog.jsx";

// Tab ids are stable across languages; the human label is resolved by the
// `useScriptTabs` hook so consumers (this file + the left sidebar in
// ScriptStep) render the right label for the active language.
export const SCRIPT_TAB_IDS = ["characters", "locations", "objects", "pages", "covers", "coherence"];

export function useScriptTabs() {
  const { t } = useTranslation();
  return useMemo(
    () => [
      { id: "characters", label: t("scriptBrowser.tabs.characters") },
      { id: "locations", label: t("scriptBrowser.tabs.locations") },
      { id: "objects", label: t("scriptBrowser.tabs.objects") },
      { id: "pages", label: t("scriptBrowser.tabs.pages") },
      { id: "covers", label: t("scriptBrowser.tabs.covers") },
      ...(SHOW_COHERENCE_CHECK ? [{ id: "coherence", label: t("scriptBrowser.tabs.coherence") }] : []),
    ],
    [t],
  );
}

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
  const { t } = useTranslation();
  const tabs = useScriptTabs();
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
          {t("scriptBrowser.summary", {
            characters: script.characters.length,
            locations: script.locations.length,
            objects: script.objects?.length ?? 0,
            pages: script.pages.length,
          })}
        </p>
        {readOnly && <span className="chip chip-peach text-xs">{t("scriptBrowser.previewChip")}</span>}
      </div>

      {!controlled && (
        <div className="border-b border-[var(--color-line)] flex">
          {tabs.map((tabDef) => (
            <button
              key={tabDef.id}
              className={
                "px-4 py-2.5 text-sm font-medium -mb-px border-b-2 transition-colors inline-flex items-center gap-1 " +
                (tab === tabDef.id
                  ? "border-[var(--color-primary-500)] text-[var(--color-primary-600)]"
                  : "border-transparent text-[var(--color-mute)] hover:text-[var(--color-ink)] hover:bg-[var(--color-paper-soft)]")
              }
              onClick={() => setTab(tabDef.id)}
            >
              {tabDef.label}
              {tabDef.id === "coherence" && isDirty && (
                <span className="w-2 h-2 rounded-full bg-[var(--color-peach-300)] inline-block" />
              )}
              {tabDef.id === "coherence" && !isDirty && issueCount > 0 && (
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
  const { t } = useTranslation();
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
            {t("scriptBrowser.characters.add")}
          </button>
        </div>
      )}
      {characters.length === 0 && <p className="text-sm text-[var(--color-mute)]">{t("scriptBrowser.characters.empty")}</p>}
      <ul className="space-y-3">
        {characters.map((c) => (
          <li key={c.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="font-semibold editable-heading">
                  <EditableText
                    label={t("scriptBrowser.editor.fieldLabel", { id: c.id })}
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
                    ↻ {t("common.regenerate")}
                  </button>
                  <button className="btn btn-ghost text-xs" onClick={() => setRefining(c)}>
                    {t("common.retouch")}
                  </button>
                  <button className="btn btn-ghost text-xs text-[var(--color-rose-500)]" onClick={() => setDeleting(c)}>
                    {t("common.delete")}
                  </button>
                </div>
              )}
            </div>
            <div className="text-sm whitespace-pre-wrap">
              <EditableText
                label={t("scriptBrowser.editor.fieldLabel", { id: c.id })}
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
              <span className="text-xs uppercase tracking-wide text-[var(--color-mute)]">
                {t("scriptBrowser.characters.outfitLabel")}
              </span>
              <EditableText
                label={t("scriptBrowser.editor.fieldLabel", { id: c.id })}
                value={c.outfit || ""}
                placeholder={t("scriptBrowser.characters.outfitPlaceholder")}
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
      {manualError && (
        <p className="text-sm text-[var(--color-rose-500)]">
          {t("scriptBrowser.characters.saveError", { error: manualError })}
        </p>
      )}
      {adding && (
        <AddScriptItemDialog
          type="character"
          title={t("scriptBrowser.characters.addDialogTitle")}
          onClose={() => setAdding(false)}
          onSubmit={addCharacter}
        />
      )}
      {refining && (
        <RefineDialog
          title={t("scriptBrowser.characters.refineTitle", { name: refining.name })}
          hint={t("scriptBrowser.characters.refineHint")}
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineCharacter(name, refining.id, text);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={t("scriptBrowser.characters.regenTitle", { name: regenerating.name })}
          body={t("scriptBrowser.characters.regenBody")}
          confirmLabel={t("common.regenerate")}
          onConfirm={async () => {
            // LLM prompt — not localized
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
          title={t("scriptBrowser.characters.deleteTitle", { name: deleting.name })}
          body={t("scriptBrowser.characters.deleteBody")}
          loadPreview={() => api.previewDeleteCharacter(name, deleting.id)}
          confirmLabel={t("common.delete")}
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
  const { t } = useTranslation();
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
            {t("scriptBrowser.locations.add")}
          </button>
        </div>
      )}
      {locations.length === 0 && <p className="text-sm text-[var(--color-mute)]">{t("scriptBrowser.locations.empty")}</p>}
      <ul className="space-y-3">
        {locations.map((l) => (
          <li key={l.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="font-semibold editable-heading">
                  <EditableText
                    label={t("scriptBrowser.editor.fieldLabel", { id: l.id })}
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
                    ↻ {t("common.regenerate")}
                  </button>
                  <button className="btn btn-ghost text-xs" onClick={() => setRefining(l)}>
                    {t("common.retouch")}
                  </button>
                  <button className="btn btn-ghost text-xs text-[var(--color-rose-500)]" onClick={() => setDeleting(l)}>
                    {t("common.delete")}
                  </button>
                </div>
              )}
            </div>
            <div className="text-sm whitespace-pre-wrap">
              <EditableText
                label={t("scriptBrowser.editor.fieldLabel", { id: l.id })}
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
      {manualError && (
        <p className="text-sm text-[var(--color-rose-500)]">
          {t("scriptBrowser.locations.saveError", { error: manualError })}
        </p>
      )}
      {adding && (
        <AddScriptItemDialog
          type="location"
          title={t("scriptBrowser.locations.addDialogTitle")}
          onClose={() => setAdding(false)}
          onSubmit={addLocation}
        />
      )}
      {refining && (
        <RefineDialog
          title={t("scriptBrowser.locations.refineTitle", { name: refining.name })}
          hint={t("scriptBrowser.locations.refineHint")}
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineLocation(name, refining.id, text);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={t("scriptBrowser.locations.regenTitle", { name: regenerating.name })}
          body={t("scriptBrowser.locations.regenBody")}
          confirmLabel={t("common.regenerate")}
          onConfirm={async () => {
            // LLM prompt — not localized
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
          title={t("scriptBrowser.locations.deleteTitle", { name: deleting.name })}
          body={t("scriptBrowser.locations.deleteBody")}
          loadPreview={() => api.previewDeleteLocation(name, deleting.id)}
          confirmLabel={t("common.delete")}
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
  const { t } = useTranslation();
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
            {t("scriptBrowser.objects.add")}
          </button>
        </div>
      )}
      {objects.length === 0 && <p className="text-sm text-[var(--color-mute)]">{t("scriptBrowser.objects.empty")}</p>}
      <ul className="space-y-3">
        {objects.map((o) => (
          <li key={o.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
            <div className="flex items-start justify-between gap-3 mb-2">
              <div>
                <div className="font-semibold editable-heading">
                  <EditableText
                    label={t("scriptBrowser.editor.fieldLabel", { id: o.id })}
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
                    ↻ {t("common.regenerate")}
                  </button>
                  <button className="btn btn-ghost text-xs" onClick={() => setRefining(o)}>
                    {t("common.retouch")}
                  </button>
                  <button className="btn btn-ghost text-xs text-[var(--color-rose-500)]" onClick={() => setDeleting(o)}>
                    {t("common.delete")}
                  </button>
                </div>
              )}
            </div>
            <div className="text-sm whitespace-pre-wrap">
              <EditableText
                label={t("scriptBrowser.editor.fieldLabel", { id: o.id })}
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
      {manualError && (
        <p className="text-sm text-[var(--color-rose-500)]">
          {t("scriptBrowser.objects.saveError", { error: manualError })}
        </p>
      )}
      {adding && (
        <AddScriptItemDialog
          type="object"
          title={t("scriptBrowser.objects.addDialogTitle")}
          onClose={() => setAdding(false)}
          onSubmit={addObject}
        />
      )}
      {refining && (
        <RefineDialog
          title={t("scriptBrowser.objects.refineTitle", { name: refining.name })}
          hint={t("scriptBrowser.objects.refineHint")}
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineObject(name, refining.id, text);
            await onChanged();
          }}
        />
      )}
      {regenerating && (
        <ConfirmDialog
          title={t("scriptBrowser.objects.regenTitle", { name: regenerating.name })}
          body={t("scriptBrowser.objects.regenBody")}
          confirmLabel={t("common.regenerate")}
          onConfirm={async () => {
            // LLM prompt — not localized
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
          title={t("scriptBrowser.objects.deleteTitle", { name: deleting.name })}
          body={t("scriptBrowser.objects.deleteBody")}
          loadPreview={() => api.previewDeleteObject(name, deleting.id)}
          confirmLabel={t("common.delete")}
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
  const { t } = useTranslation();
  const { name } = useParams();
  const [idx, setIdx] = useState(0);
  const [refining, setRefining] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [savingField, setSavingField] = useState(null);
  const [manualError, setManualError] = useState(null);
  const pages = script.pages;
  if (pages.length === 0) return <p className="text-sm text-[var(--color-mute)]">{t("scriptBrowser.pages.empty")}</p>;
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
                  {t("scriptBrowser.pages.issuesTitle")}
                </p>
                <ul className="mt-1 list-disc pl-5 text-xs text-[var(--color-ink-soft)]">
                  {pageCoherenceIssues.map((issue, issueIndex) => (
                    <li key={`${issue.kind}_${issue.target}_${issueIndex}`}>{issue.message}</li>
                  ))}
                </ul>
              </div>
              {!readOnly && (
                <button className="btn btn-secondary text-xs" onClick={() => onRegeneratePage(page.page_number)}>
                  {t("scriptBrowser.pages.regenPage")}
                </button>
              )}
            </div>
          </div>
        )}
        {pageCoherenceSuggestions.length > 0 && (
          <div className="mb-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-paper-soft)] p-3">
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-sm font-semibold">{t("scriptBrowser.pages.suggestionsTitle")}</p>
                <ul className="mt-1 list-disc pl-5 text-xs text-[var(--color-ink-soft)]">
                  {pageCoherenceSuggestions.map((s, i) => (
                    <li key={`${s.kind}_${s.target}_${i}`}>{s.message}</li>
                  ))}
                </ul>
              </div>
              {!readOnly && (
                <button className="btn btn-ghost text-xs" onClick={() => onRegeneratePage(page.page_number)}>
                  {t("scriptBrowser.pages.improvePage")}
                </button>
              )}
            </div>
          </div>
        )}
        {!readOnly && (
          <div className="script-page-actions">
            <button className="btn btn-ghost text-xs" onClick={() => setRegenerating(true)}>
              ↻ {t("common.regenerate")}
            </button>
            <button className="btn btn-ghost text-xs" onClick={() => setRefining(true)}>
              {t("scriptBrowser.pages.refineTitle", { n: page.page_number })}
            </button>
          </div>
        )}

        <div className="script-layout-block">
          <div className="min-w-0">
            <p className="script-layout-title">{t("scriptBrowser.pages.layout")}</p>
            <EditableText
              label={t("scriptBrowser.pages.layout")}
              value={page.layout || ""}
              placeholder={t("scriptBrowser.pages.layoutPlaceholder")}
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
                  <h3 className="text-base font-semibold">{t("scriptBrowser.pages.panel", { n: p.panel_number })}</h3>
                </div>
                {p.sound_effects?.length > 0 && <span className="script-sfx-chip">{p.sound_effects.join(", ")}</span>}
              </div>

              <dl className="script-panel-facts">
                <div>
                  <dt>{t("scriptBrowser.pages.size")}</dt>
                  <dd>
                    <EditableText
                      label={t("scriptBrowser.pages.size")}
                      value={p.size || ""}
                      placeholder={t("scriptBrowser.pages.sizePlaceholder")}
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
                  <dt>{t("scriptBrowser.pages.shot")}</dt>
                  <dd>
                    <EditableText
                      label={t("scriptBrowser.pages.shot")}
                      value={p.shot || ""}
                      placeholder={t("scriptBrowser.pages.shotPlaceholder")}
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
                  <dt>{t("scriptBrowser.pages.location")}</dt>
                  <dd>
                    <EditableText
                      label={t("scriptBrowser.pages.location")}
                      value={p.location || ""}
                      placeholder={t("scriptBrowser.pages.locationPlaceholder")}
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
                  <dt>{t("scriptBrowser.pages.characters")}</dt>
                  <dd>
                    <EditableText
                      label={t("scriptBrowser.pages.characters")}
                      value={(p.characters || []).join(", ")}
                      placeholder={t("scriptBrowser.pages.charactersPlaceholder")}
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
                  <dt>{t("scriptBrowser.pages.objects")}</dt>
                  <dd>
                    <EditableText
                      label={t("scriptBrowser.pages.objects")}
                      value={(p.objects || []).join(", ")}
                      placeholder={t("scriptBrowser.pages.objectsPlaceholder")}
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
                <h4>{t("scriptBrowser.pages.scene")}</h4>
                <EditableText
                  label={t("scriptBrowser.pages.scene")}
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
                <h4>{t("scriptBrowser.pages.narration")}</h4>
                <EditableText
                  label={t("scriptBrowser.pages.narration")}
                  value={p.narration || ""}
                  placeholder={t("scriptBrowser.pages.narrationPlaceholder")}
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
                <h4>{t("scriptBrowser.pages.sfx")}</h4>
                <EditableText
                  label={t("scriptBrowser.pages.sfx")}
                  value={(p.sound_effects || []).join(", ")}
                  placeholder={t("scriptBrowser.pages.sfxPlaceholder")}
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
                  <h4>{t("scriptBrowser.pages.dialogs")}</h4>
                  <ul className="space-y-2">
                    {p.dialogs.map((d, i) => (
                      <li key={i} className="script-dialog">
                        <div className="script-dialog-header">
                          <div>
                            <span className="script-dialog-label">{t("scriptBrowser.pages.dialogCharacter")}</span>
                            <EditableText
                              label={t("scriptBrowser.pages.dialogCharacter")}
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
                            <span className="script-dialog-label">{t("scriptBrowser.pages.dialogType")}</span>
                            <EditableSelect
                              label={t("scriptBrowser.pages.dialogType")}
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
                          label={t("scriptBrowser.pages.dialogCharacter")}
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
          <p className="text-sm text-[var(--color-rose-500)] mt-4">
            {t("scriptBrowser.pages.saveError", { error: manualError })}
          </p>
        )}
      </div>

      <PageNavigation idx={currentIdx} pageCount={pages.length} onChange={setIdx} className="mt-3" />

      {refining && (
        <RefineDialog
          title={t("scriptBrowser.pages.refineTitle", { n: page.page_number })}
          hint={t("scriptBrowser.pages.refineHint")}
          extraField={{
            type: "checkbox",
            id: "cascade",
            label: t("scriptBrowser.pages.refineCascadeLabel"),
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
          title={t("scriptBrowser.pages.regenTitle", { n: page.page_number })}
          body={t("scriptBrowser.pages.regenBody")}
          confirmLabel={t("common.regenerate")}
          onConfirm={async () => {
            // LLM prompt — not localized
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
  const { t } = useTranslation();
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
      setError(t("scriptBrowser.addItem.idNameDescriptionRequired"));
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
            {t("scriptBrowser.addItem.idName")}
            <input
              autoFocus
              className="input mt-1"
              value={draft.id}
              onChange={(event) => updateField("id", event.target.value)}
              disabled={saving}
              placeholder={
                isCharacter
                  ? "perso_2"
                  : type === "location"
                    ? "decor_2"
                    : "objet_2"
              }
            />
          </label>
          <label className="text-sm font-medium">
            {t("scriptBrowser.addItem.name")}
            <input
              className="input mt-1"
              value={draft.name}
              onChange={(event) => updateField("name", event.target.value)}
              disabled={saving}
            />
          </label>
        </div>
        <label className="text-sm font-medium block">
          {isCharacter ? t("scriptBrowser.addItem.physicalDescription") : t("scriptBrowser.addItem.description")}
          <textarea
            className="textarea editable-modal-textarea mt-1"
            value={draft.description}
            onChange={(event) => updateField("description", event.target.value)}
            disabled={saving}
          />
        </label>
        {isCharacter && (
          <label className="text-sm font-medium block">
            {t("scriptBrowser.addItem.outfit")}
            <input
              className="input mt-1"
              value={draft.outfit}
              onChange={(event) => updateField("outfit", event.target.value)}
              disabled={saving}
            />
          </label>
        )}
        <label className="text-sm font-medium block">
          {t("scriptBrowser.addItem.referencePrompt")}
          <textarea
            className="textarea editable-modal-textarea mt-1"
            value={draft.referencePrompt}
            onChange={(event) => updateField("referencePrompt", event.target.value)}
            disabled={saving}
            placeholder={t("scriptBrowser.addItem.referencePromptPlaceholder")}
          />
        </label>
        {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
        <div className="editable-actions">
          <button type="button" className="btn btn-ghost text-xs" onClick={onClose} disabled={saving}>
            {t("common.cancel")}
          </button>
          <button type="submit" className="btn btn-primary text-xs" disabled={saving}>
            {saving ? t("common.add") + "…" : t("common.add")}
          </button>
        </div>
      </form>
    </EditValueDialog>
  );
}

function EditableText({ label, value, onSave, placeholder, readOnly = false, saving = false, multiline = true }) {
  const { t } = useTranslation();
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
            title={t("scriptBrowser.editor.editTitle")}
            aria-label={t("scriptBrowser.editor.editAriaText")}
          >
            <FiEdit2 aria-hidden="true" />
          </button>
        </div>
      )}
      <p className={value ? "" : "text-[var(--color-mute)] italic"}>{value || placeholder || t("scriptBrowser.editor.emptyText")}</p>
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
              {t("common.cancel")}
            </button>
            <button type="button" className="btn btn-primary text-xs" onClick={submit} disabled={saving}>
              {saving ? t("scriptBrowser.editor.saving") : t("scriptBrowser.editor.save")}
            </button>
          </div>
        </EditValueDialog>
      )}
    </div>
  );
}

function EditableSelect({ label, value, options, onSave, readOnly = false, saving = false }) {
  const { t } = useTranslation();
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
            title={t("scriptBrowser.editor.editTitle")}
            aria-label={t("scriptBrowser.editor.editAriaType")}
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
              {t("common.cancel")}
            </button>
            <button type="button" className="btn btn-primary text-xs" onClick={submit} disabled={saving}>
              {saving ? t("scriptBrowser.editor.saving") : t("scriptBrowser.editor.save")}
            </button>
          </div>
        </EditValueDialog>
      )}
    </div>
  );
}

function EditValueDialog({ title, children }) {
  const { t } = useTranslation();
  return (
    <div className="editable-modal-positioner">
      <div className="editable-modal" role="dialog" aria-modal="true" aria-label={`${t("scriptBrowser.editor.editTitle")} ${title}`}>
        <div className="editable-modal-header">
          <p className="editable-modal-kicker">{t("scriptBrowser.editor.kicker")}</p>
          <h3 className="text-lg font-semibold">{title}</h3>
        </div>
        {children}
      </div>
    </div>
  );
}

function CoherenceTabContent({ coherence, checking, error, readOnly, onCheck, onRegeneratePage, onApplySuggestion }) {
  const { t } = useTranslation();
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
    ? t("scriptBrowser.coherence.statusDirty")
    : issues.length > 0
      ? t("scriptBrowser.coherence.statusIssues", { count: issues.length })
      : suggestions.length > 0
        ? t("scriptBrowser.coherence.statusSuggestions", { count: suggestions.length })
        : coherence.checked_at
          ? t("scriptBrowser.coherence.statusCheckedClean")
          : t("scriptBrowser.coherence.statusUnchecked");

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm text-[var(--color-mute)]">{statusText}</p>
        <button
          type="button"
          className={"btn text-sm " + (dirty ? "btn-primary" : "btn-ghost")}
          onClick={onCheck}
          disabled={readOnly || checking || !dirty || !onCheck}
          title={!dirty ? t("scriptBrowser.coherence.checkTitleNoChanges") : t("scriptBrowser.coherence.checkTitleHasChanges")}
        >
          {checking ? t("scriptBrowser.coherence.checkingButton") : t("scriptBrowser.coherence.checkButton")}
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
                  <p className="text-sm font-semibold text-[var(--color-rose-500)]">
                    {t("scriptBrowser.coherence.pageIssueTitle", { n: pageNumber })}
                  </p>
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
                    {t("scriptBrowser.pages.regenPage")}
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
                  <p className="text-sm font-semibold">{t("scriptBrowser.coherence.pageSuggestionTitle", { n: pageNumber })}</p>
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
                    {t("scriptBrowser.pages.improvePage")}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {globalSuggestions.length > 0 && (
        <div className="rounded-md border border-[var(--color-line)] bg-[var(--color-paper-soft)] p-2">
          <p className="text-sm font-semibold">{t("scriptBrowser.coherence.globalSuggestionsTitle")}</p>
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
                    {t("scriptBrowser.coherence.applySuggestion")}
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
            ? t("scriptBrowser.coherence.emptyChecked")
            : t("scriptBrowser.coherence.emptyUnchecked")}
        </p>
      )}

      {confirmSuggestion && (
        <ConfirmDialog
          title={t("scriptBrowser.coherence.applyTitle")}
          body={t("scriptBrowser.coherence.applyBody")}
          confirmLabel={t("common.apply")}
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
  const { t } = useTranslation();
  return (
    <div className={"flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between " + className}>
      <button
        className="btn btn-ghost text-sm"
        disabled={idx === 0}
        onClick={() => onChange((i) => Math.max(0, i - 1))}
      >
        {t("scriptBrowser.navigation.previous")}
      </button>
      <div className="flex items-center justify-center gap-2 text-sm font-medium">
        <span>{t("scriptBrowser.navigation.page")}</span>
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
        {t("scriptBrowser.navigation.next")}
      </button>
    </div>
  );
}

function CoversView({ script, onChanged, readOnly = false }) {
  const { t } = useTranslation();
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
            <h3 className="font-semibold">{t("scriptBrowser.covers.cover")}</h3>
            {!readOnly && (
              <div className="flex gap-1">
                <button className="btn btn-ghost text-xs" onClick={() => setRegenerating("cover")}>
                  ↻ {t("common.regenerate")}
                </button>
                <button className="btn btn-ghost text-xs" onClick={() => setRefining("cover")}>
                  {t("common.retouch")}
                </button>
              </div>
            )}
          </div>
          <div className="text-sm whitespace-pre-wrap">
            <EditableText
              label={t("scriptBrowser.covers.cover")}
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
              <span className="uppercase tracking-wide text-[var(--color-mute)]">
                {t("scriptBrowser.covers.titlePlacementLabel")}
              </span>
              <EditableText
                label={t("scriptBrowser.covers.cover")}
                value={script.cover.title_placement || ""}
                placeholder={t("scriptBrowser.covers.titlePlacementPlaceholder")}
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
              <strong>{t("scriptBrowser.covers.subtitle")}</strong>{" "}
              <EditableText
                label={t("scriptBrowser.covers.cover")}
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
                label={t("scriptBrowser.covers.cover")}
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
            <h3 className="font-semibold">{t("scriptBrowser.covers.backCover")}</h3>
            {!readOnly && (
              <div className="flex gap-1">
                <button className="btn btn-ghost text-xs" onClick={() => setRegenerating("back_cover")}>
                  ↻ {t("common.regenerate")}
                </button>
                <button className="btn btn-ghost text-xs" onClick={() => setRefining("back_cover")}>
                  {t("common.retouch")}
                </button>
              </div>
            )}
          </div>
          <div className="text-sm whitespace-pre-wrap">
            <EditableText
              label={t("scriptBrowser.covers.backCover")}
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
              <span className="uppercase tracking-wide text-[var(--color-mute)]">
                {t("scriptBrowser.covers.backIllustrationLabel")}
              </span>
              <EditableText
                label={t("scriptBrowser.covers.backCover")}
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
                label={t("scriptBrowser.covers.backCover")}
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
                label={t("scriptBrowser.covers.backCover")}
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
        <p className="text-sm text-[var(--color-mute)]">{t("scriptBrowser.covers.noCover")}</p>
      )}
      {manualError && (
        <p className="text-sm text-[var(--color-rose-500)]">
          {t("scriptBrowser.covers.saveError", { error: manualError })}
        </p>
      )}

      {refining === "cover" && (
        <RefineDialog
          title={t("scriptBrowser.covers.refineCoverTitle")}
          hint={t("scriptBrowser.covers.refineCoverHint")}
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineCover(name, text);
            await onChanged();
          }}
        />
      )}
      {refining === "back_cover" && (
        <RefineDialog
          title={t("scriptBrowser.covers.refineBackCoverTitle")}
          hint={t("scriptBrowser.covers.refineBackCoverHint")}
          onClose={() => setRefining(null)}
          onSubmit={async (text) => {
            await api.refineBackCover(name, text);
            await onChanged();
          }}
        />
      )}
      {regenerating === "cover" && (
        <ConfirmDialog
          title={t("scriptBrowser.covers.regenCoverTitle")}
          body={t("scriptBrowser.covers.regenCoverBody")}
          confirmLabel={t("common.regenerate")}
          onConfirm={async () => {
            // LLM prompt — not localized
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
          title={t("scriptBrowser.covers.regenBackCoverTitle")}
          body={t("scriptBrowser.covers.regenBackCoverBody")}
          confirmLabel={t("common.regenerate")}
          onConfirm={async () => {
            // LLM prompt — not localized
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
