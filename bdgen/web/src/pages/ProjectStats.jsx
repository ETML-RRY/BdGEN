import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FaArrowLeft, FaClock, FaCoins, FaCubesStacked, FaWandMagicSparkles } from "react-icons/fa6";
import { api } from "../api.js";
import { SHOW_UPSCALE } from "../featureFlags.js";

function fmtNumber(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("fr-CH").format(value);
}

function fmtMoney(value) {
  if (value === null || value === undefined) return "—";
  return `$${Number(value).toFixed(4)}`;
}

function fmtSeconds(value) {
  if (!value) return "—";
  if (value < 60) return `${value.toFixed(1)} s`;
  const minutes = Math.floor(value / 60);
  const seconds = Math.round(value % 60);
  return `${minutes} min ${seconds} s`;
}

function StatCard({ label, value, icon }) {
  return (
    <div className="card p-4">
      <div className="text-[var(--color-mute)] mb-2">{icon}</div>
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-sm text-[var(--color-ink-soft)]">{label}</div>
    </div>
  );
}

function BucketTable({ title, rows }) {
  const entries = Object.entries(rows || {});
  if (!entries.length) return null;
  return (
    <section className="card p-5">
      <h2 className="font-semibold mb-4">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-[var(--color-mute)]">
            <tr>
              <th className="py-2 pr-4">Groupe</th>
              <th className="py-2 pr-4">Appels</th>
              <th className="py-2 pr-4">Temps</th>
              <th className="py-2 pr-4">Coût</th>
              <th className="py-2 pr-4">Entrée</th>
              <th className="py-2 pr-4">Sortie</th>
              <th className="py-2 pr-4">Cache</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, b]) => (
              <tr key={name} className="border-t border-[var(--color-line)]">
                <td className="py-2 pr-4 font-medium">{name}</td>
                <td className="py-2 pr-4">{fmtNumber(b.events)}</td>
                <td className="py-2 pr-4">{fmtSeconds(b.seconds)}</td>
                <td className="py-2 pr-4">{b.known_cost_events ? fmtMoney(b.cost_usd) : "—"}</td>
                <td className="py-2 pr-4">{fmtNumber(b.input_tokens + b.image_input_tokens)}</td>
                <td className="py-2 pr-4">{fmtNumber(b.output_tokens + b.image_output_tokens)}</td>
                <td className="py-2 pr-4">{fmtNumber(b.cached_input_tokens + b.cache_creation_input_tokens)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function ProjectStats() {
  const { name } = useParams();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    api.getProjectStatistics(name)
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      });
    return () => { cancelled = true; };
  }, [name]);

  const recentEvents = useMemo(
    () => [...(stats?.events || [])].reverse().slice(0, 40),
    [stats]
  );

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <Link to="/" className="btn btn-secondary inline-flex items-center gap-2 mb-6">
          <FaArrowLeft aria-hidden /> Retour
        </Link>
        <div className="card p-6 text-[var(--color-rose-500)]">{error}</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <p className="text-sm text-[var(--color-mute)]">Chargement…</p>
      </div>
    );
  }

  const s = stats.structure;
  const g = stats.generation;

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-6">
      <div className="flex items-center justify-between gap-4">
        <div>
          <Link to="/" className="text-sm text-[var(--color-ink-soft)] hover:text-[var(--color-ink)] inline-flex items-center gap-2 mb-2">
            <FaArrowLeft aria-hidden /> Projets
          </Link>
          <h1 className="text-2xl font-semibold">Statistiques</h1>
          <p className="text-sm text-[var(--color-mute)]">{stats.project}</p>
        </div>
        <Link to={`/projects/${encodeURIComponent(stats.project)}`} className="btn btn-secondary">
          Ouvrir la BD
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Temps génération" value={fmtSeconds(g.total_seconds)} icon={<FaClock />} />
        <StatCard label="Coût estimé" value={fmtMoney(g.total_cost_usd)} icon={<FaCoins />} />
        <StatCard label="Appels modèles" value={fmtNumber(g.event_count)} icon={<FaWandMagicSparkles />} />
        <StatCard label="Mots générés" value={fmtNumber(s.generated_words)} icon={<FaCubesStacked />} />
      </div>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label="Planches" value={fmtNumber(s.pages)} />
        <StatCard label="Cases" value={fmtNumber(s.panels)} />
        <StatCard label="Bulles" value={fmtNumber(s.bubbles)} />
        <StatCard label="Images composées" value={fmtNumber(s.composed_images)} />
        <StatCard label="Personnages" value={fmtNumber(s.characters)} />
        <StatCard label="Décors" value={fmtNumber(s.locations)} />
        <StatCard label="Objets" value={fmtNumber(s.objects)} />
        {SHOW_UPSCALE && <StatCard label="Images upscalées" value={fmtNumber(s.upscaled_images)} />}
        <StatCard label="Références attendues" value={fmtNumber(s.references_expected)} />
        <StatCard label="Références générées" value={fmtNumber(s.references_generated)} />
        <StatCard label="Références utilisées" value={fmtNumber(s.references_used_total)} />
        <StatCard label="Références uniques" value={fmtNumber(s.references_used_unique)} />
      </section>

      <BucketTable title="Par étape" rows={g.by_step} />
      <BucketTable title="Par modèle" rows={g.by_model} />

      <section className="card p-5">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="font-semibold">Derniers éléments générés</h2>
          <span className="text-xs text-[var(--color-mute)]">{stats.pricing_note}</span>
        </div>
        {recentEvents.length === 0 ? (
          <p className="text-sm text-[var(--color-mute)]">
            Aucune génération instrumentée pour ce projet pour l'instant.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-[var(--color-mute)]">
                <tr>
                  <th className="py-2 pr-4">Élément</th>
                  <th className="py-2 pr-4">Étape</th>
                  <th className="py-2 pr-4">Modèle</th>
                  <th className="py-2 pr-4">Temps</th>
                  <th className="py-2 pr-4">Coût</th>
                  <th className="py-2 pr-4">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {recentEvents.map((event) => {
                  const usage = event.usage || {};
                  const tokens =
                    (usage.input_tokens || 0) +
                    (usage.output_tokens || 0) +
                    (usage.image_input_tokens || 0) +
                    (usage.image_output_tokens || 0);
                  return (
                    <tr key={event.id} className="border-t border-[var(--color-line)]">
                      <td className="py-2 pr-4 font-medium">{event.target_id}</td>
                      <td className="py-2 pr-4">{event.step}</td>
                      <td className="py-2 pr-4">{event.provider}/{event.model}</td>
                      <td className="py-2 pr-4">{fmtSeconds(event.elapsed_seconds)}</td>
                      <td className="py-2 pr-4">{fmtMoney(event.cost_usd)}</td>
                      <td className="py-2 pr-4">{tokens ? fmtNumber(tokens) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
