import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { FaArrowLeft, FaClock, FaCoins, FaCubesStacked, FaWandMagicSparkles } from "react-icons/fa6";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { SHOW_UPSCALE } from "../featureFlags.js";
import { useStepLabelMap } from "../hooks/useTranslatedSteps.js";
import { formatError } from "../i18n/formatError.js";

const NUMBER_FMT = new Intl.NumberFormat(navigator.language);

function fmtNumber(value) {
  if (value === null || value === undefined) return "—";
  return NUMBER_FMT.format(value);
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

function BucketTable({ title, rows, t }) {
  const entries = Object.entries(rows || {});
  if (!entries.length) return null;
  return (
    <section className="card p-5">
      <h2 className="font-semibold mb-4">{title}</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-[var(--color-mute)]">
            <tr>
              <th className="py-2 pr-4">{t("projectStats.colGroup")}</th>
              <th className="py-2 pr-4">{t("projectStats.colCalls")}</th>
              <th className="py-2 pr-4">{t("projectStats.colTime")}</th>
              <th className="py-2 pr-4">{t("projectStats.colCost")}</th>
              <th className="py-2 pr-4">{t("projectStats.colInput")}</th>
              <th className="py-2 pr-4">{t("projectStats.colOutput")}</th>
              <th className="py-2 pr-4">{t("projectStats.colCache")}</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([name, b]) => (
              <tr key={name} className="border-t border-[var(--color-line)]">
                <td className="py-2 pr-4 font-medium">{stepDisplay(name, t)}</td>
                <td className="py-2 pr-4">{fmtNumber(b.events)}</td>
                <td className="py-2 pr-4">{fmtSeconds(b.seconds)}</td>
                <td className="py-2 pr-4">{b.known_cost_events ? fmtMoney(b.cost_usd) : t("projectStats.dash")}</td>
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

// The bucket key from the API is the step id (preparation / script / …) or
// a model id like "openai/gpt-5". We translate the step id but pass the model
// id through unchanged.
function stepDisplay(key, t) {
  return t(`steps.${key}`, { defaultValue: key });
}

export default function ProjectStats() {
  const { name } = useParams();
  const { t } = useTranslation();
  const [stats, setStats] = useState(null);
  const [error, setError] = useState(null);
  useStepLabelMap(); // warm up the i18n cache for stepDisplay

  useEffect(() => {
    let cancelled = false;
    api.getProjectStatistics(name)
      .then((data) => {
        if (!cancelled) setStats(data);
      })
      .catch((err) => {
        if (!cancelled) setError(formatError(err, t));
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
          <FaArrowLeft aria-hidden /> {t("projectStats.back")}
        </Link>
        <div className="card p-6 text-[var(--color-rose-500)]">{error}</div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <p className="text-sm text-[var(--color-mute)]">{t("projectStats.loading")}</p>
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
            <FaArrowLeft aria-hidden /> {t("projectStats.backLabel")}
          </Link>
          <h1 className="text-2xl font-semibold">{t("projectStats.title")}</h1>
          <p className="text-sm text-[var(--color-mute)]">{stats.project}</p>
        </div>
        <Link to={`/projects/${encodeURIComponent(stats.project)}`} className="btn btn-secondary">
          {t("projectStats.openComic")}
        </Link>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t("projectStats.generationTime")} value={fmtSeconds(g.total_seconds)} icon={<FaClock />} />
        <StatCard label={t("projectStats.estimatedCost")} value={fmtMoney(g.total_cost_usd)} icon={<FaCoins />} />
        <StatCard label={t("projectStats.modelCalls")} value={fmtNumber(g.event_count)} icon={<FaWandMagicSparkles />} />
        <StatCard label={t("projectStats.wordsGenerated")} value={fmtNumber(s.generated_words)} icon={<FaCubesStacked />} />
      </div>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t("projectStats.pages")} value={fmtNumber(s.pages)} />
        <StatCard label={t("projectStats.panels")} value={fmtNumber(s.panels)} />
        <StatCard label={t("projectStats.bubbles")} value={fmtNumber(s.bubbles)} />
        <StatCard label={t("projectStats.composedImages")} value={fmtNumber(s.composed_images)} />
        <StatCard label={t("projectStats.characters")} value={fmtNumber(s.characters)} />
        <StatCard label={t("projectStats.locations")} value={fmtNumber(s.locations)} />
        <StatCard label={t("projectStats.objects")} value={fmtNumber(s.objects)} />
        {SHOW_UPSCALE && <StatCard label={t("projectStats.upscaledImages")} value={fmtNumber(s.upscaled_images)} />}
        <StatCard label={t("projectStats.expectedReferences")} value={fmtNumber(s.references_expected)} />
        <StatCard label={t("projectStats.generatedReferences")} value={fmtNumber(s.references_generated)} />
        <StatCard label={t("projectStats.usedReferences")} value={fmtNumber(s.references_used_total)} />
        <StatCard label={t("projectStats.uniqueReferences")} value={fmtNumber(s.references_used_unique)} />
      </section>

      <BucketTable title={t("projectStats.perStage")} rows={g.by_step} t={t} />
      <BucketTable title={t("projectStats.perModel")} rows={g.by_model} t={t} />

      <section className="card p-5">
        <div className="flex items-baseline justify-between mb-4">
          <h2 className="font-semibold">{t("projectStats.recentSection")}</h2>
          <span className="text-xs text-[var(--color-mute)]">{stats.pricing_note}</span>
        </div>
        {recentEvents.length === 0 ? (
          <p className="text-sm text-[var(--color-mute)]">
            {t("projectStats.recentEmpty")}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-[var(--color-mute)]">
                <tr>
                  <th className="py-2 pr-4">{t("projectStats.colItem")}</th>
                  <th className="py-2 pr-4">{t("projectStats.colStep")}</th>
                  <th className="py-2 pr-4">{t("projectStats.colModel")}</th>
                  <th className="py-2 pr-4">{t("projectStats.colTime")}</th>
                  <th className="py-2 pr-4">{t("projectStats.colCost")}</th>
                  <th className="py-2 pr-4">{t("projectStats.colTokens")}</th>
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
                      <td className="py-2 pr-4">{stepDisplay(event.step, t)}</td>
                      <td className="py-2 pr-4">{event.provider}/{event.model}</td>
                      <td className="py-2 pr-4">{fmtSeconds(event.elapsed_seconds)}</td>
                      <td className="py-2 pr-4">{fmtMoney(event.cost_usd)}</td>
                      <td className="py-2 pr-4">{tokens ? fmtNumber(tokens) : t("projectStats.dash")}</td>
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
