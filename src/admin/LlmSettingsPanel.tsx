import { useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  Eye,
  EyeOff,
  FlaskConical,
  KeyRound,
  LoaderCircle,
  Save,
  TriangleAlert,
} from "lucide-react";
import {
  productionConfirmation,
  type AdminTarget,
} from "./operations";
import type { LlmSettingsStatus } from "./llmSettings";

type SettingsResponse = {
  ok?: boolean;
  error?: string;
  settings?: LlmSettingsStatus;
  output?: string;
  durationMs?: number;
};

const localAdminToken = () => {
  const token = document
    .querySelector<HTMLMetaElement>('meta[name="local-admin-token"]')
    ?.getAttribute("content");
  if (!token) throw new Error("The local admin session is missing. Reload this page.");
  return token;
};

const postAdmin = async (path: string, body: unknown) => {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Local-Admin-Token": localAdminToken(),
    },
    body: JSON.stringify(body),
  });
  return (await response.json()) as SettingsResponse;
};

export function LlmSettingsPanel() {
  const [target, setTarget] = useState<AdminTarget>("development");
  const [status, setStatus] = useState<LlmSettingsStatus | null>(null);
  const [primaryKey, setPrimaryKey] = useState("");
  const [primaryBaseUrl, setPrimaryBaseUrl] = useState("https://api.openai.com/v1");
  const [primaryModel, setPrimaryModel] = useState("gpt-5-mini");
  const [fallbackEnabled, setFallbackEnabled] = useState(false);
  const [fallbackKey, setFallbackKey] = useState("");
  const [fallbackBaseUrl, setFallbackBaseUrl] = useState("https://openrouter.ai/api/v1");
  const [fallbackModel, setFallbackModel] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPrimaryKey, setShowPrimaryKey] = useState(false);
  const [showFallbackKey, setShowFallbackKey] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<SettingsResponse | null>(null);

  const applyStatus = useCallback((next: LlmSettingsStatus) => {
    setStatus(next);
    setPrimaryBaseUrl(next.primary.baseUrl);
    setPrimaryModel(next.primary.model);
    setFallbackEnabled(next.fallback.enabled);
    setFallbackBaseUrl(next.fallback.baseUrl);
    setFallbackModel(next.fallback.model);
    setPrimaryKey("");
    setFallbackKey("");
  }, []);

  const loadSettings = useCallback(async (nextTarget: AdminTarget) => {
    setLoading(true);
    setMessage(null);
    try {
      const response = await postAdmin("/__local_admin/llm-settings/read", {
        target: nextTarget,
      });
      if (!response.ok || !response.settings) {
        throw new Error(response.error || "Unable to load LLM settings.");
      }
      applyStatus(response.settings);
    } catch (error) {
      setMessage({ error: error instanceof Error ? error.message : "Unable to load settings." });
    } finally {
      setLoading(false);
    }
  }, [applyStatus]);

  useEffect(() => {
    void loadSettings(target);
  }, [loadSettings, target]);

  const productionReady =
    target !== "production" || confirmation === productionConfirmation;

  const saveSettings = async () => {
    setSaving(true);
    setMessage(null);
    try {
      const response = await postAdmin("/__local_admin/llm-settings/save", {
        target,
        confirmation: target === "production" ? confirmation : undefined,
        fallbackEnabled,
        primary: {
          apiKey: primaryKey,
          baseUrl: primaryBaseUrl,
          model: primaryModel,
        },
        fallback: {
          apiKey: fallbackKey,
          baseUrl: fallbackBaseUrl,
          model: fallbackModel,
        },
      });
      if (!response.ok || !response.settings) {
        throw new Error(response.error || "Unable to save LLM settings.");
      }
      applyStatus(response.settings);
      setMessage({ ok: true, output: "Settings saved. API keys remain write-only." });
    } catch (error) {
      setMessage({ error: error instanceof Error ? error.message : "Unable to save settings." });
    } finally {
      setSaving(false);
    }
  };

  const testSettings = async () => {
    setTesting(true);
    setMessage(null);
    try {
      const response = await postAdmin("/__local_admin/run", {
        operation: "testLlmProviders",
        target,
        confirmation: target === "production" ? confirmation : undefined,
      });
      if (!response.ok) throw new Error(response.error || "Provider test failed.");
      setMessage(response);
    } catch (error) {
      setMessage({ error: error instanceof Error ? error.message : "Provider test failed." });
    } finally {
      setTesting(false);
    }
  };

  return (
    <section className="settings-panel">
      <div className="settings-heading">
        <div>
          <span className="section-label">Deployment environment</span>
          <h2>LLM provider settings</h2>
          <p>Keys are sent directly to Convex and are never returned to this page.</p>
        </div>
        <label className="target-selector">
          <span>Convex target</span>
          <select
            value={target}
            onChange={(event) => {
              setTarget(event.target.value as AdminTarget);
              setConfirmation("");
            }}
          >
            <option value="development">Development data</option>
            <option value="production">Production — public site data</option>
          </select>
        </label>
      </div>

      {loading ? (
        <div className="settings-loading"><LoaderCircle className="spin" /> Loading deployment settings…</div>
      ) : (
        <>
          <div className="provider-settings-grid">
            <ProviderCard
              title="Primary provider"
              description="Used first for every AI report. OpenAI-compatible /responses endpoint required."
              keyConfigured={status?.primary.keyConfigured ?? false}
              apiKey={primaryKey}
              baseUrl={primaryBaseUrl}
              model={primaryModel}
              showKey={showPrimaryKey}
              onApiKeyChange={setPrimaryKey}
              onBaseUrlChange={setPrimaryBaseUrl}
              onModelChange={setPrimaryModel}
              onToggleKey={() => setShowPrimaryKey((value) => !value)}
            />

            <div className={`provider-card fallback-card${fallbackEnabled ? " enabled" : ""}`}>
              <div className="provider-card-header">
                <div>
                  <span className="provider-kicker">Automatic fallback</span>
                  <h3>Fallback provider</h3>
                </div>
                <label className="switch-control">
                  <input
                    type="checkbox"
                    checked={fallbackEnabled}
                    onChange={(event) => setFallbackEnabled(event.target.checked)}
                  />
                  <span>{fallbackEnabled ? "Enabled" : "Disabled"}</span>
                </label>
              </div>
              <p>Used if the primary key is missing, unreachable, rejected, or returns invalid output.</p>
              <ProviderFields
                disabled={!fallbackEnabled}
                keyConfigured={status?.fallback.keyConfigured ?? false}
                apiKey={fallbackKey}
                baseUrl={fallbackBaseUrl}
                model={fallbackModel}
                showKey={showFallbackKey}
                onApiKeyChange={setFallbackKey}
                onBaseUrlChange={setFallbackBaseUrl}
                onModelChange={setFallbackModel}
                onToggleKey={() => setShowFallbackKey((value) => !value)}
              />
            </div>
          </div>

          {target === "production" && (
            <div className="production-guard settings-production-guard">
              <TriangleAlert size={20} />
              <label>
                <strong>This changes private settings for the public production data.</strong>
                <span>Type {productionConfirmation} to save or test production providers.</span>
                <input
                  value={confirmation}
                  autoComplete="off"
                  onChange={(event) => setConfirmation(event.target.value)}
                  placeholder={productionConfirmation}
                />
              </label>
            </div>
          )}

          <div className="settings-actions">
            <button
              className="secondary-button"
              type="button"
              disabled={saving || testing || !productionReady}
              onClick={testSettings}
            >
              {testing ? <LoaderCircle className="spin" size={18} /> : <FlaskConical size={18} />}
              {testing ? "Testing…" : "Test saved providers"}
            </button>
            <button
              className="run-button settings-save"
              type="button"
              disabled={saving || testing || !productionReady}
              onClick={saveSettings}
            >
              {saving ? <LoaderCircle className="spin" size={18} /> : <Save size={18} />}
              {saving ? "Saving securely…" : "Save settings"}
            </button>
          </div>
          <p className="settings-test-note">
            Testing sends one minimal Responses API request to each configured provider and may incur a small provider charge.
          </p>
        </>
      )}

      {message && (
        <div className={`result-panel ${message.ok ? "success" : "error"}`} aria-live="polite">
          <div className="result-title">
            {message.ok ? <CheckCircle2 size={18} /> : <TriangleAlert size={18} />}
            <strong>{message.ok ? "Settings operation completed" : "Settings operation failed"}</strong>
          </div>
          <pre>{message.output || message.error || "No output returned."}</pre>
        </div>
      )}
    </section>
  );
}

type ProviderCardProps = {
  title: string;
  description: string;
  keyConfigured: boolean;
  apiKey: string;
  baseUrl: string;
  model: string;
  showKey: boolean;
  onApiKeyChange: (value: string) => void;
  onBaseUrlChange: (value: string) => void;
  onModelChange: (value: string) => void;
  onToggleKey: () => void;
};

function ProviderCard({ title, description, ...fields }: ProviderCardProps) {
  return (
    <div className="provider-card primary-card">
      <div className="provider-card-header">
        <div>
          <span className="provider-kicker">Default route</span>
          <h3>{title}</h3>
        </div>
        <StatusBadge configured={fields.keyConfigured} />
      </div>
      <p>{description}</p>
      <ProviderFields {...fields} />
    </div>
  );
}

type ProviderFieldsProps = Omit<ProviderCardProps, "title" | "description"> & {
  disabled?: boolean;
};

function ProviderFields({
  disabled = false,
  keyConfigured,
  apiKey,
  baseUrl,
  model,
  showKey,
  onApiKeyChange,
  onBaseUrlChange,
  onModelChange,
  onToggleKey,
}: ProviderFieldsProps) {
  return (
    <div className="provider-fields">
      <label>
        <span>API key <StatusBadge configured={keyConfigured} compact /></span>
        <div className="secret-input">
          <KeyRound size={17} />
          <input
            type={showKey ? "text" : "password"}
            value={apiKey}
            disabled={disabled}
            autoComplete="new-password"
            onChange={(event) => onApiKeyChange(event.target.value)}
            placeholder={keyConfigured ? "Saved — enter a new key to replace" : "Enter API key"}
          />
          <button type="button" disabled={disabled} onClick={onToggleKey} aria-label={showKey ? "Hide key" : "Show key"}>
            {showKey ? <EyeOff size={17} /> : <Eye size={17} />}
          </button>
        </div>
      </label>
      <label>
        <span>Server base URL</span>
        <input
          value={baseUrl}
          disabled={disabled}
          spellCheck={false}
          onChange={(event) => onBaseUrlChange(event.target.value)}
          placeholder="https://openrouter.ai/api/v1"
        />
      </label>
      <label>
        <span>Model</span>
        <input
          value={model}
          disabled={disabled}
          spellCheck={false}
          onChange={(event) => onModelChange(event.target.value)}
          placeholder="provider/model"
        />
      </label>
    </div>
  );
}

function StatusBadge({ configured, compact = false }: { configured: boolean; compact?: boolean }) {
  return (
    <span className={`config-status ${configured ? "configured" : "missing"}${compact ? " compact" : ""}`}>
      {configured ? "Key configured" : "Key missing"}
    </span>
  );
}
