import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import RefineDialog from "./RefineDialog.jsx";
import ConfirmDeleteDialog from "./ConfirmDeleteDialog.jsx";

const TABS = [
  { id: "characters", label: "Personnages" },
  { id: "locations", label: "Décors" },
  { id: "objects", label: "Objets" },
  { id: "pages", label: "Planches" },
  { id: "covers", label: "Couvertures" },
];

export default function ScriptBrowser({ project, onChanged, readOnly = false }) {
  const [tab, setTab] = useState("characters");
  const script = project.script;

  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-4 gap-3">
        <div className="text-sm text-[var(--color-ink-soft)]">
          {script.characters.length} personnages · {script.locations.length}{" "}
          décors · {(script.objects?.length ?? 0)} objets ·{" "}
          {script.pages.length} planches
          {readOnly && (
            <span className="ml-3 chip chip-peach">
              Aperçu — édition désactivée pendant la génération
            </span>
          )}
        </div>
        <div className="flex gap-1 p-1 rounded-lg bg-[var(--color-paper-soft)]">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={
                "px-3 py-1.5 text-sm rounded-md transition " +
                (tab === t.id
                  ? "bg-white shadow-sm text-[var(--color-ink)]"
                  : "text-[var(--color-ink-soft)] hover:text-[var(--color-ink)]")
              }
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "characters" && (
        <CharactersList characters={script.characters} onChanged={onChanged} readOnly={readOnly} />
      )}
      {tab === "locations" && (
        <LocationsList locations={script.locations} onChanged={onChanged} readOnly={readOnly} />
      )}
      {tab === "objects" && (
        <ObjectsList objects={script.objects || []} onChanged={onChanged} readOnly={readOnly} />
      )}
      {tab === "pages" && (
        <PagesBrowser script={script} onChanged={onChanged} readOnly={readOnly} />
      )}
      {tab === "covers" && (
        <CoversView script={script} onChanged={onChanged} readOnly={readOnly} />
      )}
    </div>
  );
}

function CharactersList({ characters, onChanged, readOnly = false }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const [refining, setRefining] = useState(null);
  const [deleting, setDeleting] = useState(null);
  if (characters.length === 0)
    return <p className="text-sm text-[var(--color-mute)]">Aucun personnage.</p>;
  return (
    <ul className="space-y-3">
      {characters.map((c) => (
        <li key={c.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div>
              <div className="font-semibold">{c.name}</div>
              <div className="text-xs text-[var(--color-mute)]">id: {c.id}</div>
            </div>
            {!readOnly && (
              <div className="flex gap-1">
                <button
                  className="btn btn-ghost text-xs"
                  onClick={() => setRefining(c)}
                >
                  Retoucher
                </button>
                <button
                  className="btn btn-ghost text-xs text-[var(--color-rose-500)]"
                  onClick={() => setDeleting(c)}
                >
                  Supprimer
                </button>
              </div>
            )}
          </div>
          <p className="text-sm whitespace-pre-wrap">{c.physical_description}</p>
          {c.outfit && (
            <p className="text-sm text-[var(--color-ink-soft)] mt-2">
              <span className="text-xs uppercase tracking-wide text-[var(--color-mute)]">
                Tenue —{" "}
              </span>
              {c.outfit}
            </p>
          )}
        </li>
      ))}
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
            // If the backend auto-launched a regen job, take the user to the
            // script step so they see progress.
            if (info?.job) {
              navigate(`/projects/${encodeURIComponent(name)}/script`);
            }
          }}
        />
      )}
    </ul>
  );
}

function LocationsList({ locations, onChanged, readOnly = false }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const [refining, setRefining] = useState(null);
  const [deleting, setDeleting] = useState(null);
  if (locations.length === 0)
    return <p className="text-sm text-[var(--color-mute)]">Aucun décor.</p>;
  return (
    <ul className="space-y-3">
      {locations.map((l) => (
        <li key={l.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div>
              <div className="font-semibold">{l.name}</div>
              <div className="text-xs text-[var(--color-mute)]">id: {l.id}</div>
            </div>
            {!readOnly && (
              <div className="flex gap-1">
                <button
                  className="btn btn-ghost text-xs"
                  onClick={() => setRefining(l)}
                >
                  Retoucher
                </button>
                <button
                  className="btn btn-ghost text-xs text-[var(--color-rose-500)]"
                  onClick={() => setDeleting(l)}
                >
                  Supprimer
                </button>
              </div>
            )}
          </div>
          <p className="text-sm whitespace-pre-wrap">{l.description}</p>
        </li>
      ))}
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
    </ul>
  );
}

function ObjectsList({ objects, onChanged, readOnly = false }) {
  const { name } = useParams();
  const navigate = useNavigate();
  const [refining, setRefining] = useState(null);
  const [deleting, setDeleting] = useState(null);
  if (objects.length === 0)
    return (
      <p className="text-sm text-[var(--color-mute)]">
        Aucun objet / produit / référence pour ce projet.
      </p>
    );
  return (
    <ul className="space-y-3">
      {objects.map((o) => (
        <li key={o.id} className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div>
              <div className="font-semibold">{o.name}</div>
              <div className="text-xs text-[var(--color-mute)]">id: {o.id}</div>
            </div>
            {!readOnly && (
              <div className="flex gap-1">
                <button
                  className="btn btn-ghost text-xs"
                  onClick={() => setRefining(o)}
                >
                  Retoucher
                </button>
                <button
                  className="btn btn-ghost text-xs text-[var(--color-rose-500)]"
                  onClick={() => setDeleting(o)}
                >
                  Supprimer
                </button>
              </div>
            )}
          </div>
          <p className="text-sm whitespace-pre-wrap">{o.description}</p>
        </li>
      ))}
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
    </ul>
  );
}


function PagesBrowser({ script, onChanged, readOnly = false }) {
  const { name } = useParams();
  const [idx, setIdx] = useState(0);
  const [refining, setRefining] = useState(false);
  const pages = script.pages;
  if (pages.length === 0)
    return <p className="text-sm text-[var(--color-mute)]">Aucune planche.</p>;
  const page = pages[idx];
  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <button
          className="btn btn-ghost text-sm"
          disabled={idx === 0}
          onClick={() => setIdx((i) => Math.max(0, i - 1))}
        >
          ← Précédente
        </button>
        <span className="text-sm font-medium">
          Planche {page.page_number} / {pages.length}
        </span>
        <button
          className="btn btn-ghost text-sm"
          disabled={idx === pages.length - 1}
          onClick={() => setIdx((i) => Math.min(pages.length - 1, i + 1))}
        >
          Suivante →
        </button>
      </div>

      <div className="card p-4 bg-[var(--color-paper-soft)]/40">
        <div className="flex items-start justify-between mb-2">
          <p className="text-xs text-[var(--color-mute)] uppercase tracking-wide">
            Layout&nbsp;: {page.layout || "—"}
          </p>
          {!readOnly && (
            <button
              className="btn btn-ghost text-xs"
              onClick={() => setRefining(true)}
            >
              Retoucher la planche
            </button>
          )}
        </div>
        <ol className="space-y-3">
          {page.panels.map((p) => (
            <li key={p.panel_number} className="border-l-4 border-[var(--color-primary-200)] pl-3">
              <div className="text-xs text-[var(--color-mute)]">
                Case {p.panel_number} · {p.size || "medium"} · {p.shot || "medium shot"}
              </div>
              <div className="text-sm">
                <strong>Lieu&nbsp;:</strong> {p.location} ·{" "}
                <strong>Personnages&nbsp;:</strong>{" "}
                {p.characters.length === 0 ? "(aucun)" : p.characters.join(", ")}
                {p.objects?.length > 0 && (
                  <>
                    {" "}
                    · <strong>Objets&nbsp;:</strong> {p.objects.join(", ")}
                  </>
                )}
              </div>
              <p className="text-sm mt-1 whitespace-pre-wrap">
                {p.scene_description}
              </p>
              {p.narration && (
                <p className="text-sm italic text-[var(--color-ink-soft)] mt-1">
                  Narration : « {p.narration} »
                </p>
              )}
              {p.dialogs?.length > 0 && (
                <ul className="text-sm mt-1 space-y-0.5">
                  {p.dialogs.map((d, i) => (
                    <li key={i}>
                      <span className="text-[var(--color-mute)] text-xs">
                        ({d.type})
                      </span>{" "}
                      <strong>{d.speaker}&nbsp;:</strong> « {d.text} »
                    </li>
                  ))}
                </ul>
              )}
              {p.sound_effects?.length > 0 && (
                <p className="text-sm mt-1">
                  <strong className="text-[var(--color-peach-500)]">SFX&nbsp;:</strong>{" "}
                  {p.sound_effects.join(", ")}
                </p>
              )}
            </li>
          ))}
        </ol>
      </div>

      {refining && (
        <RefineDialog
          title={`Retoucher la planche ${page.page_number}`}
          hint="Décrivez le changement à apporter à cette planche. Le LLM réécrira uniquement cette page."
          extraField={{
            type: "checkbox",
            id: "cascade",
            label: "Régénérer aussi les planches suivantes pour cohérence (recommandé pour des changements importants).",
          }}
          onClose={() => setRefining(false)}
          onSubmit={async (text, extras) => {
            await api.refinePage(name, page.page_number, text, !!extras.cascade);
            await onChanged();
          }}
        />
      )}
    </div>
  );
}

function CoversView({ script, onChanged, readOnly = false }) {
  const { name } = useParams();
  const [refining, setRefining] = useState(null); // "cover" | "back_cover" | null

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {script.cover && (
        <div className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="font-semibold">Couverture</h3>
            {!readOnly && (
              <button
                className="btn btn-ghost text-xs"
                onClick={() => setRefining("cover")}
              >
                Retoucher
              </button>
            )}
          </div>
          <p className="text-sm whitespace-pre-wrap">
            {script.cover.scene_description}
          </p>
          {script.cover.title_placement && (
            <p className="text-xs text-[var(--color-ink-soft)] mt-2">
              <span className="uppercase tracking-wide text-[var(--color-mute)]">
                Placement du titre —{" "}
              </span>
              {script.cover.title_placement}
            </p>
          )}
          {script.cover.subtitle && (
            <p className="text-sm mt-2">
              <strong>Sous-titre&nbsp;:</strong> {script.cover.subtitle}
            </p>
          )}
          {script.cover.tagline && (
            <p className="text-sm italic mt-2">« {script.cover.tagline} »</p>
          )}
        </div>
      )}
      {script.back_cover && (
        <div className="card p-4 bg-[var(--color-paper-soft)]/40">
          <div className="flex items-start justify-between gap-3 mb-1">
            <h3 className="font-semibold">4ᵉ de couverture</h3>
            {!readOnly && (
              <button
                className="btn btn-ghost text-xs"
                onClick={() => setRefining("back_cover")}
              >
                Retoucher
              </button>
            )}
          </div>
          <p className="text-sm whitespace-pre-wrap">
            {script.back_cover.synopsis_blurb}
          </p>
          {script.back_cover.scene_description && (
            <p className="text-xs text-[var(--color-ink-soft)] mt-2">
              <span className="uppercase tracking-wide text-[var(--color-mute)]">
                Illustration —{" "}
              </span>
              {script.back_cover.scene_description}
            </p>
          )}
          {script.back_cover.tagline && (
            <p className="text-sm italic mt-2">
              « {script.back_cover.tagline} »
            </p>
          )}
          {script.back_cover.layout_notes && (
            <p className="text-xs text-[var(--color-mute)] mt-2">
              {script.back_cover.layout_notes}
            </p>
          )}
        </div>
      )}
      {!script.cover && !script.back_cover && (
        <p className="text-sm text-[var(--color-mute)]">
          Aucune couverture définie.
        </p>
      )}

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
    </div>
  );
}
