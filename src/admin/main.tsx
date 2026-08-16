import { StrictMode, useEffect, useMemo, useState } from "react";
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
  Moon,
  RefreshCw,
  SlidersHorizontal,
  Sun,
  TriangleAlert,
  Wrench,
} from "lucide-react";
import {
  adminOperations,
  type AdminOperationId,
  type AdminTarget,
} from "./operations";
import { formatElapsedTime } from "./elapsed";
import { LlmSettingsPanel } from "./LlmSettingsPanel";
import { ManagementPanel } from "./ManagementPanel";
import {
  normalizeWatchlistStatuses,
  sortWatchlistStatuses,
  type WatchlistSortDirection,
  type WatchlistSortKey,
  type WatchlistStatus,
  type WatchlistTicker,
} from "./watchlist";
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

type WatchlistResult = {
  ok?: boolean;
  error?: string;
  tickers?: WatchlistTicker[];
  statuses?: unknown;
};

const stageLabel = {
  report: "AI report",
  thesis: "Investment thesis",
  notes: "AI notes",
};

const watchlistColumns: Array<{ key: WatchlistSortKey; label: string }> = [
  { key: "ticker", label: "Ticker" },
  { key: "listName", label: "Watchlist" },
  { key: "marketDataAt", label: "Market data sync" },
  { key: "financialsAt", label: "Financials" },
  { key: "aiReportAt", label: "AI report" },
  { key: "thesisAt", label: "Thesis" },
  { key: "aiNotesAt", label: "AI notes" },
  { key: "signalsAt", label: "Signals" },
];

export function AdminApp() {
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    const saved = window.localStorage.getItem("stockinvesting-admin-theme");
    if (saved === "light" || saved === "dark") return saved;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  });
  const [activeSection, setActiveSection] = useState<"jobs" | "manage" | "settings">("jobs");
  const [operationId, setOperationId] = useState<AdminOperationId>("syncTicker");
  const [target, setTarget] = useState<AdminTarget>("development");
  const [ticker, setTicker] = useState("NVDA");
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<AdminResult | null>(null);
  const [watchlistTickers, setWatchlistTickers] = useState<WatchlistTicker[]>([]);
  const [watchlistStatusRows, setWatchlistStatusRows] = useState<WatchlistStatus[]>([]);
  const [tickerStatus, setTickerStatus] = useState<"loading" | "ready" | "error">("loading");
  const [tickerError, setTickerError] = useState("");
  const [watchlistStatus, setWatchlistStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [watchlistError, setWatchlistError] = useState("");
  const [watchlistReload, setWatchlistReload] = useState(0);
  const [watchlistSort, setWatchlistSort] = useState<{
    key: WatchlistSortKey;
    direction: WatchlistSortDirection;
  }>({ key: "ticker", direction: "ascending" });
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const operation = useMemo(
    () => adminOperations.find((item) => item.id === operationId) ?? adminOperations[0],
    [operationId],
  );
  const watchlistGroups = useMemo(() => {
    const groups = new Map<string, WatchlistTicker[]>();
    for (const item of watchlistTickers) {
      const group = groups.get(item.listName) ?? [];
      group.push(item);
      groups.set(item.listName, group);
    }
    return [...groups.entries()];
  }, [watchlistTickers]);
  const sortedWatchlistStatusRows = useMemo(
    () => sortWatchlistStatuses(watchlistStatusRows, watchlistSort.key, watchlistSort.direction),
    [watchlistSort, watchlistStatusRows],
  );

  const changeWatchlistSort = (key: WatchlistSortKey) => {
    setWatchlistSort((current) => ({
      key,
      direction:
        current.key === key && current.direction === "ascending" ? "descending" : "ascending",
    }));
  };

  useEffect(() => {
    document.documentElement.dataset.adminTheme = theme;
    window.localStorage.setItem("stockinvesting-admin-theme", theme);
  }, [theme]);

  useEffect(() => {
    const controller = new AbortController();

    const loadWatchlist = async () => {
      setTickerStatus("loading");
      setTickerError("");
      setWatchlistStatus("idle");
      setWatchlistStatusRows([]);
      try {
        const token = document
          .querySelector<HTMLMetaElement>('meta[name="local-admin-token"]')
          ?.getAttribute("content");
        if (!token) {
          throw new Error("The local admin session token is missing. Reload this page.");
        }

        const response = await fetch("/__local_admin/watchlist", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Local-Admin-Token": token,
          },
          body: JSON.stringify({ target }),
          signal: controller.signal,
        });
        const payload = (await response.json()) as WatchlistResult;
        if (!response.ok || !payload.ok || !payload.tickers) {
          throw new Error(payload.error || "Unable to load the watchlist.");
        }

        setWatchlistTickers(payload.tickers);
        setTicker((current) =>
          payload.tickers?.some((item) => item.ticker === current)
            ? current
            : (payload.tickers?.[0]?.ticker ?? ""),
        );
        setTickerStatus("ready");
      } catch (error) {
        if (controller.signal.aborted) return;
        setWatchlistTickers([]);
        setTicker("");
        setTickerStatus("error");
        setTickerError(
          error instanceof Error ? error.message : "Unable to load the watchlist.",
        );
      }
    };

    void loadWatchlist();
    return () => controller.abort();
  }, [target, watchlistReload]);

  const loadWatchlistStatus = async () => {
    setWatchlistStatus("loading");
    setWatchlistError("");
    try {
      const token = document
        .querySelector<HTMLMetaElement>('meta[name="local-admin-token"]')
        ?.getAttribute("content");
      if (!token) {
        throw new Error("The local admin session token is missing. Reload this page.");
      }

      const response = await fetch("/__local_admin/watchlist-status", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Local-Admin-Token": token,
        },
        body: JSON.stringify({ target }),
      });
      const payload = (await response.json()) as WatchlistResult;
      if (!response.ok || !payload.ok || payload.statuses === undefined) {
        throw new Error(payload.error || "Unable to load saved refresh history.");
      }

      setWatchlistStatusRows(normalizeWatchlistStatuses(payload.statuses));
      setWatchlistStatus("ready");
    } catch (error) {
      setWatchlistStatusRows([]);
      setWatchlistStatus("error");
      setWatchlistError(
        error instanceof Error ? error.message : "Unable to load saved refresh history.",
      );
    }
  };

  useEffect(() => {
    if (runStartedAt === null) return;

    const updateElapsed = () => {
      setElapsedSeconds(Math.floor((Date.now() - runStartedAt) / 1000));
    };
    updateElapsed();
    const interval = window.setInterval(updateElapsed, 1000);
    return () => window.clearInterval(interval);
  }, [runStartedAt]);

  const runOperation = async () => {
    setRunning(true);
    setRunStartedAt(Date.now());
    setElapsedSeconds(0);
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
        }),
      });
      const payload = (await response.json()) as AdminResult;
      setResult(payload);
    } catch (error) {
      setResult({ error: error instanceof Error ? error.message : "The operation failed." });
    } finally {
      setRunning(false);
      setRunStartedAt(null);
      setWatchlistStatusRows([]);
      setWatchlistStatus("idle");
      setWatchlistReload((value) => value + 1);
    }
  };

  const tickerReady =
    !operation.requiresTicker ||
    (tickerStatus === "ready" &&
      watchlistTickers.some((item) => item.ticker === ticker));

  const formatAdminTimestamp = (timestamp: number | null) =>
    timestamp === null
      ? "Not available"
      : new Date(timestamp).toLocaleString(undefined, {
          dateStyle: "medium",
          timeStyle: "short",
        });

  return (
    <main className="admin-shell">
      <header className="admin-header">
        <div>
          <div className="eyebrow"><LockKeyhole size={14} /> Localhost only</div>
          <h1>StockInvesting Admin</h1>
          <p>Run private refresh jobs, then review the saved results in the read-only app.</p>
        </div>
        <div className="header-actions">
          <button
            className="theme-toggle"
            type="button"
            onClick={() => setTheme((current) => (current === "dark" ? "light" : "dark"))}
            aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
          >
            {theme === "dark" ? <Sun size={16} /> : <Moon size={16} />}
            {theme === "dark" ? "Light mode" : "Dark mode"}
          </button>
          <a className="public-link" href="/">
            Open read-only app <ExternalLink size={15} />
          </a>
        </div>
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
        <button
          type="button"
          className={activeSection === "manage" ? "active" : ""}
          onClick={() => setActiveSection("manage")}
        >
          <BriefcaseBusiness size={17} /> Manage data
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
              <select
                value={ticker}
                disabled={tickerStatus !== "ready" || watchlistTickers.length === 0}
                onChange={(event) => {
                  setTicker(event.target.value);
                  setResult(null);
                }}
                aria-describedby="ticker-watchlist-status"
              >
                {tickerStatus === "loading" && <option value="">Loading watchlist…</option>}
                {tickerStatus === "error" && <option value="">Watchlist unavailable</option>}
                {tickerStatus === "ready" && watchlistTickers.length === 0 && (
                  <option value="">No saved tickers</option>
                )}
                {watchlistGroups.map(([listName, items]) => (
                  <optgroup label={listName} key={listName}>
                    {items.map((item) => (
                      <option value={item.ticker} key={item.ticker}>
                        {item.ticker}{item.companyName ? ` — ${item.companyName}` : ""}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              <span
                className={`field-help${tickerStatus === "error" ? " error" : ""}`}
                id="ticker-watchlist-status"
              >
                {tickerStatus === "loading" && `Loading ${target} watchlist…`}
                {tickerStatus === "ready" && watchlistTickers.length > 0 &&
                  `${watchlistTickers.length} saved ${watchlistTickers.length === 1 ? "ticker" : "tickers"} from ${watchlistGroups.length} ${watchlistGroups.length === 1 ? "watchlist" : "watchlists"}.`}
                {tickerStatus === "ready" && watchlistTickers.length === 0 &&
                  `No tickers are saved in the ${target} watchlist.`}
                {tickerStatus === "error" && (
                  <>
                    {tickerError}{" "}
                    <button type="button" onClick={() => setWatchlistReload((value) => value + 1)}>
                      Try again
                    </button>
                  </>
                )}
              </span>
            </label>
          )}
        </div>

        {target === "production" && (
          <div className="production-guard">
            <TriangleAlert size={20} />
            <div>
              <strong>This changes the data shown on the public website.</strong>
              <span>Review the selected job and ticker before running it.</span>
            </div>
          </div>
        )}

        <button
          className="run-button"
          type="button"
          disabled={running || !tickerReady}
          onClick={runOperation}
        >
          {running ? <LoaderCircle className="spin" size={18} /> : <RefreshCw size={18} />}
          {running
            ? `Running private job… ${formatElapsedTime(elapsedSeconds)}`
            : `Run ${operation.label.toLowerCase()}`}
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

      <section
        className="watchlist-status-panel"
        aria-labelledby="watchlist-status-title"
        aria-busy={watchlistStatus === "loading"}
      >
        <div className="watchlist-status-heading">
          <div>
            <span className="section-label">Watchlist status</span>
            <h2 id="watchlist-status-title">Saved stock refresh history</h2>
            <p>Latest persisted timestamps for the selected {target} data target.</p>
          </div>
          <div className="watchlist-status-actions">
            <span className={`target-chip ${target}`}>
              {watchlistStatus === "ready" ? `${watchlistStatusRows.length} stocks` : "On demand"}
            </span>
            <button
              className="watchlist-sync-button"
              type="button"
              onClick={() => void loadWatchlistStatus()}
              disabled={watchlistStatus === "loading"}
            >
              <RefreshCw className={watchlistStatus === "loading" ? "spin" : ""} size={15} />
              {watchlistStatus === "loading" ? "Syncing history…" : "Sync history"}
            </button>
          </div>
        </div>

        {watchlistStatus === "idle" && (
          <div className="watchlist-status-message">
            <RefreshCw size={17} /> Sync saved refresh history when you need it.
          </div>
        )}
        {watchlistStatus === "loading" && (
          <div className="watchlist-status-message">
            <LoaderCircle className="spin" size={17} /> Loading saved refresh history…
          </div>
        )}
        {watchlistStatus === "error" && (
          <div className="watchlist-status-message error">
            {watchlistError || "Unable to load saved refresh history."}
          </div>
        )}
        {watchlistStatus === "ready" && watchlistStatusRows.length === 0 && (
          <div className="watchlist-status-message">No saved stocks are available for this target.</div>
        )}
        {watchlistStatus === "ready" && watchlistStatusRows.length > 0 && (
          <div className="watchlist-table-wrap">
            <table className="watchlist-status-table">
              <caption className="sr-only">Watchlist stock refresh history</caption>
              <thead>
                <tr>
                  {watchlistColumns.map((column) => {
                    const isSorted = watchlistSort.key === column.key;
                    const ariaSort = isSorted ? watchlistSort.direction : "none";
                    return (
                      <th scope="col" aria-sort={ariaSort} key={column.key}>
                        <button
                          className="watchlist-sort-button"
                          type="button"
                          onClick={() => changeWatchlistSort(column.key)}
                          aria-label={`Sort by ${column.label}${isSorted ? `, currently ${watchlistSort.direction}` : ""}`}
                        >
                          <span>{column.label}</span>
                          <span className={`sort-indicator${isSorted ? " active" : ""}`} aria-hidden="true">
                            {isSorted ? (watchlistSort.direction === "ascending" ? "↑" : "↓") : "↕"}
                          </span>
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody>
                {sortedWatchlistStatusRows.map((row) => (
                  <tr key={row.ticker}>
                    <th scope="row">
                      <strong>{row.ticker}</strong>
                      {row.companyName && <span title={row.companyName}>{row.companyName}</span>}
                    </th>
                    <td>{row.listName}</td>
                    <td className={row.marketDataAt === null ? "not-available" : ""}>{formatAdminTimestamp(row.marketDataAt)}</td>
                    <td className={row.financialsAt === null ? "not-available" : ""}>{formatAdminTimestamp(row.financialsAt)}</td>
                    <td className={row.aiReportAt === null ? "not-available" : ""}>{formatAdminTimestamp(row.aiReportAt)}</td>
                    <td className={row.thesisAt === null ? "not-available" : ""}>{formatAdminTimestamp(row.thesisAt)}</td>
                    <td className={row.aiNotesAt === null ? "not-available" : ""}>{formatAdminTimestamp(row.aiNotesAt)}</td>
                    <td className={row.signalsAt === null ? "not-available" : ""}>{formatAdminTimestamp(row.signalsAt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
        </>
      ) : activeSection === "manage" ? (
        <ManagementPanel />
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
