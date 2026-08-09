import { StrictMode, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Bot,
  BriefcaseBusiness,
  CheckCircle2,
  DatabaseZap,
  ExternalLink,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  SlidersHorizontal,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import {
  adminOperations,
  productionConfirmation,
  type AdminOperationId,
  type AdminTarget,
} from "./operations";
import { LlmSettingsPanel } from "./LlmSettingsPanel";
import "./styles.css";

const iconByTone = {
  market: DatabaseZap,
  ai: Bot,
  signals: Activity,
  portfolio: BriefcaseBusiness,
};

type AdminResult = {
  ok?: boolean;
  error?: string;
  operation?: string;
  target?: string;
  durationMs?: number;
  output?: string;
  workflow?: {
    ticker: string;
    status: "complete" | "partial" | "failed";
    stages: Array<{
      stage: "report" | "thesis" | "notes";
      status: "completed" | "failed" | "skipped";
      provider?: string;
      model?: string;
      generatedAt?: number;
      createdNotes?: number;
      replacedNotes?: number;
      error?: string;
    }>;
  };
};

const stageLabel = {
  report: "AI report",
  thesis: "Investment thesis",
  notes: "AI notes",
};

export function AdminApp() {
  const [activeSection, setActiveSection] = useState<"jobs" | "settings">("jobs");
  const [operationId, setOperationId] = useState<AdminOperationId>("syncTicker");
  const [target, setTarget] = useState<AdminTarget>("development");
  const [ticker, setTicker] = useState("NVDA");
  const [confirmation, setConfirmation] = useState("");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AdminResult | null>(null);
  const operation = useMemo(
    () => adminOperations.find((item) => item.id === operationId) ?? adminOperations[0],
    [operationId],
  );

  const runOperation = async () => {
    setRunning(true);
    setResult(null);
    try {
      const token = document
        .querySelector<HTMLMetaElement>('meta[name="local-admin-token"]')
        ?.getAttribute("content");
      if (!token) {
        throw new Error("The local admin session token is missing. Reload this page.");
      }

      const response = await fetch("/__local_admin/run", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Local-Admin-Token": token,
        },
        body: JSON.stringify({
          operation: operation.id,
          target,
          ticker: operation.requiresTicker ? ticker : undefined,
          confirmation: target === "production" ? confirmation : undefined,
        }),
      });
      const payload = (await response.json()) as AdminResult;
      setResult(payload);
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : "The operation failed." });
    } finally {
      setRunning(false);
    }
  };

  const productionReady =
    target !== "production" || confirmation === productionConfirmation;
  const tickerReady = !operation.requiresTicker || Boolean(ticker.trim());

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <div className="eyebrow"><LockKeyhole size={14} /> Localhost only</div>
          <h1>StockInvesting Admin</h1>
          <p>Run private refresh jobs, then review the saved results in the read-only app.</p>
        </div>
        <a className="public-link" href="/">
          Open read-only app <ExternalLink size={15} />
        </a>
      </header>

      <section className="security-note">
        <LockKeyhole size={18} />
        <div>
          <strong>This page exists only in the local Vite development server.</strong>
          <span>It is excluded from production builds, accepts only loopback requests, and exposes no API keys.</span>
        </div>
      </section>

      <nav className="admin-tabs" aria-label="Admin sections">
        <button
          type="button"
          className={activeSection === "jobs" ? "active" : ""}
          onClick={() => setActiveSection("jobs")}
        >
          <Wrench size={17} /> Private jobs
        </button>
        <button
          type="button"
          className={activeSection === "settings" ? "active" : ""}
          onClick={() => setActiveSection("settings")}
        >
          <SlidersHorizontal size={17} /> LLM settings
        </button>
      </nav>

      {activeSection === "jobs" ? (
        <>
      <section className="admin-grid" aria-label="Private operations">
        {adminOperations.filter((item) => item.showInJobs !== false).map((item) => {
          const Icon = iconByTone[item.tone];
          const selected = item.id === operation.id;
          return (
            <button
              className={`operation-card tone-${item.tone}${selected ? " selected" : ""}`}
              key={item.id}
              type="button"
              aria-pressed={selected}
              onClick={() => {
                setOperationId(item.id);
                setResult(null);
              }}
            >
              <span className="operation-icon"><Icon size={20} /></span>
              <span className="operation-copy">
                <strong>{item.label}</strong>
                <span>{item.description}</span>
              </span>
              {selected && <CheckCircle2 className="selected-check" size={18} />}
            </button>
          );
        })}
      </section>

      <section className="run-panel">
        <div className="panel-heading">
          <div>
            <span className="section-label">Selected job</span>
            <h2>{operation.label}</h2>
          </div>
          <span className={`target-chip ${target}`}>{target}</span>
        </div>

        <div className="field-grid">
          <label>
            <span>Convex target</span>
            <select
              value={target}
              onChange={(event) => {
                setTarget(event.target.value as AdminTarget);
                setConfirmation("");
                setResult(null);
              }}
            >
              <option value="development">Development data</option>
              <option value="production">Production — public site data</option>
            </select>
          </label>

          {operation.requiresTicker && (
            <label>
              <span>Ticker</span>
              <input
                value={ticker}
                maxLength={15}
                spellCheck={false}
                onChange={(event) => setTicker(event.target.value.toUpperCase())}
                placeholder="NVDA"
              />
            </label>
          )}
        </div>

        {target === "production" && (
          <div className="production-guard">
            <TriangleAlert size={20} />
            <label>
              <strong>This changes the data shown on the public website.</strong>
              <span>Type {productionConfirmation} to confirm this single operation.</span>
              <input
                value={confirmation}
                autoComplete="off"
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder={productionConfirmation}
              />
            </label>
          </div>
        )}

        <button
          className="run-button"
          type="button"
          disabled={running || !productionReady || !tickerReady}
          onClick={runOperation}
        >
          {running ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}
          {running ? "Running private job…" : `Run ${operation.label.toLowerCase()}`}
        </button>

        {result && (
          <div className={`result-panel ${result.workflow?.status === "failed" || !result.ok ? "error" : result.workflow?.status === "partial" ? "partial" : "success"}`} aria-live="polite">
            <div className="result-title">
              {result.ok && result.workflow?.status !== "failed" ? <CheckCircle2 size={18} /> : <TriangleAlert size={18} />}
              <strong>{result.workflow?.status === "partial" ? "Job partially completed" : result.ok && result.workflow?.status !== "failed" ? "Job completed" : "Job failed"}</strong>
              {result.durationMs !== undefined && (
                <span>{(result.durationMs / 1000).toFixed(1)}s</span>
              )}
            </div>
            {result.workflow && (
              <div className="workflow-stages" aria-label={`AI workflow stages for ${result.workflow.ticker}`}>
                {result.workflow.stages.map((stage) => (
                  <div className={`workflow-stage ${stage.status}`} key={stage.stage}>
                    <strong>{stageLabel[stage.stage]}</strong>
                    <span>{stage.status === "completed" ? "Completed" : stage.status === "failed" ? "Failed" : "Skipped"}</span>
                    {stage.provider && <small>{stage.provider} · {stage.model}</small>}
                    {stage.createdNotes !== undefined && <small>{stage.createdNotes} created, {stage.replacedNotes ?? 0} replaced</small>}
                    {stage.error && <small>{stage.error}</small>}
                  </div>
                ))}
              </div>
            )}
            <pre>{result.output || result.error || "No output returned."}</pre>
          </div>
        )}
      </section>
        </>
      ) : (
        <LlmSettingsPanel />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AdminApp />
  </StrictMode>,
);
