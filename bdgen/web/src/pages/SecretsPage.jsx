import { useEffect, useMemo, useState } from "react";
import { FaArrowUpRightFromSquare, FaBookOpen, FaKey } from "react-icons/fa6";
import { useTranslation } from "react-i18next";
import { api } from "../api.js";
import { formatError } from "../i18n/formatError.js";

const PROVIDERS = [
  {
    id: "openai",
    label: "OpenAI",
    secret: "OPENAI_API_KEY",
    required: true,
    docsUrl: "https://developers.openai.com/api/reference/overview",
    tokenUrl: "https://platform.openai.com/api-keys",
  },
  {
    id: "anthropic",
    label: "Anthropic",
    secret: "ANTHROPIC_API_KEY",
    docsUrl: "https://platform.claude.com/docs/en/api/overview",
    tokenUrl: "https://console.anthropic.com/settings/keys",
  },
  {
    id: "xai",
    label: "xAI",
    secret: "XAI_API_KEY",
    docsUrl: "https://docs.x.ai/developers/quickstart",
    tokenUrl: "https://console.x.ai/team/default/api-keys",
  },
  {
    id: "replicate",
    label: "Replicate",
    secret: "REPLICATE_API_TOKEN",
    docsUrl: "https://replicate.com/docs/topics/security/api-tokens/",
    tokenUrl: "https://replicate.com/account/api-tokens",
  },
];

const EMPTY_KEYS = Object.fromEntries(PROVIDERS.map((p) => [p.secret, ""]));

export default function SecretsPage({ mode = "page", onReady }) {
  const { t } = useTranslation();
  const [status, setStatus] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [keys, setKeys] = useState(EMPTY_KEYS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const providers = useMemo(() => status?.providers || {}, [status?.providers]);
  const hasConfiguredProvider = useMemo(
    () => Object.values(providers).some((p) => p.configured),
    [providers]
  );
  const needsSetup = status && !status.vault_exists && !hasConfiguredProvider;
  const needsUnlock = status?.vault_exists && !status?.unlocked;
  const isGate = mode === "gate";

  useEffect(() => {
    refresh();
  }, []);

  async function refresh() {
    setStatus(await api.secretsStatus());
  }

  async function submitUnlock(e) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      const next = await api.unlockSecretsVault(password);
      setStatus(next);
      setPassword("");
      onReady?.(next);
    } catch (err) {
      setError(formatError(err, t));
    } finally {
      setSaving(false);
    }
  }

  async function submitCreate(e) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError(t("secrets.passwordTooShort"));
      return;
    }
    if (password !== confirm) {
      setError(t("secrets.passwordMismatch"));
      return;
    }
    setSaving(true);
    try {
      const next = await api.createSecretsVault(password, keys);
      setStatus(next);
      setPassword("");
      setConfirm("");
      setKeys(EMPTY_KEYS);
      onReady?.(next);
    } catch (err) {
      setError(formatError(err, t));
    } finally {
      setSaving(false);
    }
  }

  async function updateProvider(provider) {
    setError(null);
    const item = PROVIDERS.find((p) => p.id === provider);
    const value = keys[item.secret];
    if (!value.trim()) return;
    setSaving(true);
    try {
      const next = await api.updateSecretProvider(provider, value);
      setStatus(next);
      setKeys((prev) => ({ ...prev, [item.secret]: "" }));
    } catch (err) {
      setError(formatError(err, t));
    } finally {
      setSaving(false);
    }
  }

  if (!status) {
    return <Shell isGate={isGate}><p className="text-sm text-[var(--color-mute)]">{t("secrets.loading")}</p></Shell>;
  }

  if (needsUnlock) {
    return (
      <Shell isGate={isGate}>
        <form className="card p-6 space-y-4 max-w-md w-full" onSubmit={submitUnlock}>
          <div>
            <h1 className="text-xl font-semibold">{t("secrets.unlockTitle")}</h1>
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              {t("secrets.unlockBody")}
            </p>
          </div>
          <input
            className="input"
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("secrets.masterPassword")}
          />
          {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
          <button className="btn btn-primary w-full" disabled={saving || !password}>
            {saving ? t("secrets.unlocking") : t("secrets.unlock")}
          </button>
        </form>
      </Shell>
    );
  }

  if (needsSetup) {
    return (
      <Shell isGate={isGate}>
        <form className="card p-6 space-y-4 max-w-2xl w-full" onSubmit={submitCreate}>
          <div>
            <h1 className="text-xl font-semibold">{t("secrets.setupTitle")}</h1>
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              {t("secrets.setupBody")}
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t("secrets.masterPassword")} />
            <input className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder={t("secrets.confirmPassword")} />
          </div>
          <ProviderInputs keys={keys} setKeys={setKeys} providers={providers} t={t} />
          {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
          <button className="btn btn-primary" disabled={saving}>
            {saving ? t("secrets.creating") : t("secrets.create")}
          </button>
        </form>
      </Shell>
    );
  }

  return (
    <Shell isGate={isGate}>
      <section className="card p-6 space-y-5 max-w-3xl w-full">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">{t("secrets.pageTitle")}</h1>
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              {t("secrets.pageBody")}
            </p>
          </div>
          {status.vault_exists && (
            <button className="btn btn-secondary text-sm" onClick={async () => setStatus(await api.lockSecretsVault())}>
              {t("secrets.lock")}
            </button>
          )}
        </div>
        <div className="space-y-4">
          {PROVIDERS.map((provider) => {
            const info = providers[provider.id] || {};
            return (
              <div key={provider.id} className="border border-[var(--color-line)] rounded-lg p-4">
                <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                  <div>
                    <h2 className="font-medium">{provider.label}</h2>
                    <p className="text-xs text-[var(--color-mute)]">{provider.secret}</p>
                  </div>
                  <span className={info.configured ? "chip chip-mint" : "chip chip-peach"}>
                    {info.configured
                      ? t("secrets.configured", { source: info.source })
                      : t("secrets.absent")}
                  </span>
                </div>
                <ProviderLinks provider={provider} className="mb-3" t={t} />
                <div className="flex gap-2">
                  <input
                    className="input"
                    type="password"
                    value={keys[provider.secret] || ""}
                    onChange={(e) => setKeys((prev) => ({ ...prev, [provider.secret]: e.target.value }))}
                    placeholder={t("secrets.newKey", { provider: provider.label })}
                  />
                  <button className="btn btn-primary" disabled={saving || !keys[provider.secret]?.trim()} onClick={() => updateProvider(provider.id)}>
                    {t("secrets.save")}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
      </section>
    </Shell>
  );
}

function ProviderInputs({ keys, setKeys, providers, t }) {
  return (
    <div className="space-y-3">
      {PROVIDERS.map((provider) => (
        <label key={provider.id} className="block">
          <span className="flex flex-wrap items-center justify-between gap-2 mb-1">
            <span className="label mb-0">
              {provider.label}
              {provider.required ? ` ${t("secrets.required")}` : ` ${t("secrets.optional")}`}
            </span>
            <ProviderLinks provider={provider} compact t={t} />
          </span>
          <input
            className="input"
            type="password"
            value={keys[provider.secret] || ""}
            onChange={(e) => setKeys((prev) => ({ ...prev, [provider.secret]: e.target.value }))}
            placeholder={providers[provider.id]?.configured ? t("secrets.alreadyConfigured") : provider.secret}
          />
        </label>
      ))}
    </div>
  );
}

function ProviderLinks({ provider, compact = false, className = "", t }) {
  const linkClass = compact
    ? "text-xs inline-flex items-center gap-1 text-[var(--color-primary-700)] hover:text-[var(--color-primary-500)]"
    : "text-xs inline-flex items-center gap-1 px-2 py-1 rounded-md border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:bg-[var(--color-paper-soft)] hover:text-[var(--color-ink)]";

  function openLink(e, url) {
    if (!window.bdgenDesktop?.openExternal) return;
    e.preventDefault();
    window.bdgenDesktop.openExternal(url);
  }

  return (
    <div className={`flex flex-wrap gap-2 ${className}`}>
      <a
        href={provider.docsUrl}
        target="_blank"
        rel="noreferrer"
        className={linkClass}
        onClick={(e) => openLink(e, provider.docsUrl)}
      >
        <FaBookOpen aria-hidden />
        {t("secrets.documentation")}
        {!compact && <FaArrowUpRightFromSquare aria-hidden className="text-[0.65rem]" />}
      </a>
      <a
        href={provider.tokenUrl}
        target="_blank"
        rel="noreferrer"
        className={linkClass}
        onClick={(e) => openLink(e, provider.tokenUrl)}
      >
        <FaKey aria-hidden />
        {t("secrets.createToken")}
        {!compact && <FaArrowUpRightFromSquare aria-hidden className="text-[0.65rem]" />}
      </a>
    </div>
  );
}

function Shell({ isGate, children }) {
  return (
    <div className={isGate ? "h-full min-h-0 flex items-center justify-center overflow-auto p-6" : "max-w-4xl mx-auto px-6 py-8"}>
      {children}
    </div>
  );
}
