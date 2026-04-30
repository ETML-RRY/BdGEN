import { useEffect, useMemo, useState } from "react";
import { api } from "../api.js";

const PROVIDERS = [
  { id: "openai", label: "OpenAI", secret: "OPENAI_API_KEY", required: true },
  { id: "anthropic", label: "Anthropic", secret: "ANTHROPIC_API_KEY" },
  { id: "replicate", label: "Replicate", secret: "REPLICATE_API_TOKEN" },
];

const EMPTY_KEYS = Object.fromEntries(PROVIDERS.map((p) => [p.secret, ""]));

export default function SecretsPage({ mode = "page", onReady }) {
  const [status, setStatus] = useState(null);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [keys, setKeys] = useState(EMPTY_KEYS);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const providers = status?.providers || {};
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
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function submitCreate(e) {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError("Choisissez un mot de passe maitre d'au moins 8 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("Les deux mots de passe ne correspondent pas.");
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
      setError(err.message);
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
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  if (!status) {
    return <Shell isGate={isGate}><p className="text-sm text-[var(--color-mute)]">Chargement...</p></Shell>;
  }

  if (needsUnlock) {
    return (
      <Shell isGate={isGate}>
        <form className="card p-6 space-y-4 max-w-md w-full" onSubmit={submitUnlock}>
          <div>
            <h1 className="text-xl font-semibold">Deverrouiller BdGEN</h1>
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              Entrez le mot de passe maitre pour dechiffrer les cles API locales.
            </p>
          </div>
          <input
            className="input"
            type="password"
            autoFocus
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Mot de passe maitre"
          />
          {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
          <button className="btn btn-primary w-full" disabled={saving || !password}>
            {saving ? "Ouverture..." : "Deverrouiller"}
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
            <h1 className="text-xl font-semibold">Configurer le coffre BdGEN</h1>
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              Les cles API seront chiffrees sur disque. Le mot de passe maitre
              ne sera pas stocke.
            </p>
          </div>
          <div className="grid md:grid-cols-2 gap-3">
            <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Mot de passe maitre" />
            <input className="input" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirmer le mot de passe" />
          </div>
          <ProviderInputs keys={keys} setKeys={setKeys} providers={providers} />
          {error && <p className="text-sm text-[var(--color-rose-500)]">{error}</p>}
          <button className="btn btn-primary" disabled={saving}>
            {saving ? "Creation..." : "Creer le coffre"}
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
            <h1 className="text-xl font-semibold">Cles API</h1>
            <p className="text-sm text-[var(--color-ink-soft)] mt-1">
              Les valeurs completes ne sont jamais affichees. Remplacez une cle
              en saisissant une nouvelle valeur.
            </p>
          </div>
          {status.vault_exists && (
            <button className="btn btn-secondary text-sm" onClick={async () => setStatus(await api.lockSecretsVault())}>
              Verrouiller
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
                    {info.configured ? `Configuree (${info.source})` : "Absente"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <input
                    className="input"
                    type="password"
                    value={keys[provider.secret] || ""}
                    onChange={(e) => setKeys((prev) => ({ ...prev, [provider.secret]: e.target.value }))}
                    placeholder={`Nouvelle cle ${provider.label}`}
                  />
                  <button className="btn btn-primary" disabled={saving || !keys[provider.secret]?.trim()} onClick={() => updateProvider(provider.id)}>
                    Enregistrer
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

function ProviderInputs({ keys, setKeys, providers }) {
  return (
    <div className="space-y-3">
      {PROVIDERS.map((provider) => (
        <label key={provider.id} className="block">
          <span className="label">
            {provider.label}{provider.required ? " (requis)" : " (optionnel)"}
          </span>
          <input
            className="input"
            type="password"
            value={keys[provider.secret] || ""}
            onChange={(e) => setKeys((prev) => ({ ...prev, [provider.secret]: e.target.value }))}
            placeholder={providers[provider.id]?.configured ? "Deja configuree" : provider.secret}
          />
        </label>
      ))}
    </div>
  );
}

function Shell({ isGate, children }) {
  return (
    <div className={isGate ? "min-h-screen flex items-center justify-center p-6" : "max-w-4xl mx-auto px-6 py-8"}>
      {children}
    </div>
  );
}
