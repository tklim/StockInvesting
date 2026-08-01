import {
  Archive,
  BarChart3,
  BriefcaseBusiness,
  Copy,
  Edit3,
  LineChart,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Settings,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useAction, useMutation, useQuery } from "convex/react";
import type { FunctionReturnType } from "convex/server";
import { api } from "../convex/_generated/api";
import type { Id } from "../convex/_generated/dataModel";

type MultiPortfolioViewProps = {
  onOpenResearch: (ticker: string) => void;
};

type PortfolioListItem = FunctionReturnType<typeof api.portfolios.list>[number];

type PortfolioFormState = {
  name: string;
  type: "actual" | "model";
  description: string;
  startingValue: string;
  cashBalance: string;
  benchmarkTicker: string;
};

type HoldingDraft = {
  ticker: string;
  shares: string;
  averageCost: string;
  targetAllocation: string;
  notes: string;
};

const emptyPortfolioForm: PortfolioFormState = {
  name: "",
  type: "actual",
  description: "",
  startingValue: "100000",
  cashBalance: "0",
  benchmarkTicker: "SPY",
};

const emptyHolding: HoldingDraft = {
  ticker: "",
  shares: "0",
  averageCost: "0",
  targetAllocation: "0",
  notes: "",
};

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 2,
});

const formatPercent = (value: number) =>
  `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;

const formatDateTime = (value?: number) =>
  value
    ? new Intl.DateTimeFormat("en-US", {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      }).format(value)
    : "Not valued yet";

const errorMessage = (error: unknown) =>
  error instanceof Error ? error.message : "Something went wrong.";

export function MultiPortfolioView({
  onOpenResearch,
}: MultiPortfolioViewProps) {
  const portfolios = useQuery(api.portfolios.list, { includeArchived: true });
  const ensureMainPortfolio = useMutation(api.portfolios.ensureMainPortfolio);
  const createPortfolio = useMutation(api.portfolios.create);
  const updatePortfolio = useMutation(api.portfolios.update);
  const duplicatePortfolio = useMutation(api.portfolios.duplicate);
  const archivePortfolio = useMutation(api.portfolios.archive);
  const upsertHolding = useMutation(api.portfolios.upsertHolding);
  const removeHolding = useMutation(api.portfolios.removeHolding);
  const initializeModel = useMutation(api.portfolios.initializeModel);
  const applyModelRebalance = useMutation(api.portfolios.applyModelRebalance);
  const refreshValue = useAction(api.portfolios.refreshValue);

  const [selectedId, setSelectedId] = useState<string>(() =>
    window.localStorage.getItem("selectedPortfolioId") ?? "all"
  );
  const portfolioId =
    selectedId === "all" ? null : (selectedId as Id<"portfolios">);
  const dashboard = useQuery(
    api.portfolios.getDashboard,
    portfolioId ? { portfolioId } : "skip"
  );
  const history = useQuery(
    api.portfolios.history,
    portfolioId ? { portfolioId, limit: 1300 } : "skip"
  );
  const rebalance = useQuery(
    api.portfolios.rebalancePreview,
    portfolioId ? { portfolioId } : "skip"
  );
  const activities = useQuery(
    api.portfolios.activities,
    portfolioId ? { portfolioId, limit: 8 } : "skip"
  );

  const [showCreate, setShowCreate] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showHolding, setShowHolding] = useState(false);
  const [showRebalance, setShowRebalance] = useState(false);
  const [portfolioForm, setPortfolioForm] =
    useState<PortfolioFormState>(emptyPortfolioForm);
  const [holdingDraft, setHoldingDraft] =
    useState<HoldingDraft>(emptyHolding);
  const [portfolioSearch, setPortfolioSearch] = useState("");
  const [chartRange, setChartRange] = useState<
    "1M" | "3M" | "6M" | "1Y" | "All"
  >("6M");
  const [chartMode, setChartMode] = useState<"value" | "return">("value");
  const [showBenchmark, setShowBenchmark] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const stockSearch = useQuery(
    api.stocks.search,
    portfolioSearch.trim()
      ? { query: portfolioSearch.trim() }
      : "skip"
  );

  const activePortfolios = useMemo(
    () => portfolios?.filter((portfolio) => portfolio.status === "active") ?? [],
    [portfolios]
  );
  const archivedPortfolios = useMemo(
    () =>
      portfolios?.filter((portfolio) => portfolio.status === "archived") ?? [],
    [portfolios]
  );

  useEffect(() => {
    if (portfolios?.length === 0) {
      void ensureMainPortfolio();
    }
  }, [ensureMainPortfolio, portfolios]);

  useEffect(() => {
    if (
      selectedId !== "all" &&
      portfolios &&
      !portfolios.some((portfolio) => portfolio._id === selectedId)
    ) {
      setSelectedId("all");
    }
  }, [portfolios, selectedId]);

  useEffect(() => {
    window.localStorage.setItem("selectedPortfolioId", selectedId);
  }, [selectedId]);

  const handleCreate = async (event: FormEvent) => {
    event.preventDefault();
    setBusy("create");
    setMessage("");
    try {
      const nextId = await createPortfolio({
        name: portfolioForm.name,
        type: portfolioForm.type,
        description: portfolioForm.description,
        startingValue:
          portfolioForm.type === "model"
            ? Number(portfolioForm.startingValue)
            : undefined,
        cashBalance:
          portfolioForm.type === "actual"
            ? Number(portfolioForm.cashBalance)
            : undefined,
        benchmarkTicker: portfolioForm.benchmarkTicker,
      });
      setSelectedId(nextId);
      setShowCreate(false);
      setPortfolioForm(emptyPortfolioForm);
      setMessage("Portfolio created.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const handleSettings = async (event: FormEvent) => {
    event.preventDefault();
    if (!portfolioId) return;
    setBusy("settings");
    setMessage("");
    try {
      await updatePortfolio({
        portfolioId,
        name: portfolioForm.name,
        description: portfolioForm.description,
        cashBalance: Number(portfolioForm.cashBalance),
        benchmarkTicker: portfolioForm.benchmarkTicker,
      });
      setShowSettings(false);
      setMessage("Portfolio settings updated.");
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const openSettings = () => {
    if (!dashboard) return;
    setPortfolioForm({
      name: dashboard.portfolio.name,
      type: dashboard.portfolio.type,
      description: dashboard.portfolio.description,
      startingValue: String(dashboard.portfolio.startingValue ?? ""),
      cashBalance: String(dashboard.portfolio.cashBalance),
      benchmarkTicker: dashboard.portfolio.benchmarkTicker,
    });
    setShowSettings(true);
  };

  const openHolding = (
    holding?: NonNullable<typeof dashboard>["holdings"][number]
  ) => {
    setPortfolioSearch("");
    setHoldingDraft(
      holding
        ? {
            ticker: holding.ticker,
            shares: String(holding.shares),
            averageCost: String(holding.averageCost),
            targetAllocation: String(holding.targetAllocation),
            notes: holding.notes,
          }
        : emptyHolding
    );
    setShowHolding(true);
  };

  const handleHolding = async (event: FormEvent) => {
    event.preventDefault();
    if (!portfolioId) return;
    setBusy("holding");
    setMessage("");
    try {
      await upsertHolding({
        portfolioId,
        ticker: holdingDraft.ticker,
        shares: Number(holdingDraft.shares),
        averageCost: Number(holdingDraft.averageCost),
        targetAllocation: Number(holdingDraft.targetAllocation),
        notes: holdingDraft.notes,
      });
      setShowHolding(false);
      setHoldingDraft(emptyHolding);
      setMessage(`${holdingDraft.ticker.toUpperCase()} saved.`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const handleRefresh = async () => {
    if (!portfolioId) return;
    setBusy("refresh");
    setMessage("Refreshing quotes and calculating portfolio value…");
    try {
      const result = await refreshValue({ portfolioId });
      setMessage(
        `Value refreshed for ${result.marketDate}. ${result.refreshedCount} fresh, ${result.staleTickerCount} stale.`
      );
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const duplicateCurrent = async () => {
    if (!portfolioId || !dashboard) return;
    const name = `${dashboard.portfolio.name} Copy`;
    setBusy("duplicate");
    try {
      const nextId = await duplicatePortfolio({ portfolioId, name });
      setSelectedId(nextId);
      setMessage(`Created ${name}.`);
    } catch (error) {
      setMessage(errorMessage(error));
    } finally {
      setBusy(null);
    }
  };

  const archiveCurrent = async () => {
    if (!portfolioId || !dashboard) return;
    if (
      !window.confirm(
        `Archive ${dashboard.portfolio.name}? Its history will be preserved.`
      )
    ) {
      return;
    }
    await archivePortfolio({ portfolioId });
    setSelectedId("all");
    setMessage("Portfolio archived.");
  };

  if (!portfolios) {
    return <PortfolioLoading />;
  }

  return (
    <section className="multi-portfolio-page">
      <div className="multi-portfolio-toolbar">
        <div>
          <span className="ticker-badge">Portfolio</span>
          <h1>
            {dashboard?.portfolio.name ??
              (selectedId === "all" ? "All Portfolios" : "Portfolio")}
          </h1>
          <p>
            {dashboard?.portfolio.description ||
              "Manage strategies, allocations, values, and performance history."}
          </p>
        </div>
        <div className="portfolio-toolbar-actions">
          <label className="portfolio-selector">
            <span>Portfolio</span>
            <select
              value={selectedId}
              onChange={(event) => setSelectedId(event.target.value)}
            >
              <option value="all">All Portfolios</option>
              {activePortfolios.map((portfolio) => (
                <option value={portfolio._id} key={portfolio._id}>
                  {portfolio.name}
                </option>
              ))}
              {archivedPortfolios.length > 0 && (
                <optgroup label="Archived">
                  {archivedPortfolios.map((portfolio) => (
                    <option value={portfolio._id} key={portfolio._id}>
                      {portfolio.name}
                    </option>
                  ))}
                </optgroup>
              )}
            </select>
          </label>
          <button
            className="primary-button"
            type="button"
            onClick={() => {
              setPortfolioForm(emptyPortfolioForm);
              setShowCreate(true);
            }}
          >
            <Plus size={16} />
            New portfolio
          </button>
        </div>
      </div>

      {message && (
        <div
          className={`portfolio-message${message.toLowerCase().includes("error") ? " error" : ""}`}
          role="status"
        >
          {message}
        </div>
      )}

      {selectedId === "all" ? (
        <PortfolioOverview
          portfolios={activePortfolios}
          archivedCount={archivedPortfolios.length}
          onOpen={(id) => setSelectedId(id)}
          onCreate={() => {
            setPortfolioForm(emptyPortfolioForm);
            setShowCreate(true);
          }}
        />
      ) : dashboard ? (
        <>
          <div className="portfolio-detail-actions">
            <span
              className={`portfolio-status-pill ${dashboard.portfolio.lastValuationStatus ?? "stale"}`}
            >
              {dashboard.portfolio.type} ·{" "}
              {dashboard.portfolio.lastValuationStatus ?? "not valued"}
            </span>
            <span>
              Last refresh {formatDateTime(dashboard.portfolio.lastValuedAt)}
            </span>
            <div>
              <button
                className="primary-button"
                disabled={busy === "refresh"}
                onClick={() => void handleRefresh()}
                type="button"
              >
                <RefreshCw
                  className={busy === "refresh" ? "spin" : ""}
                  size={16}
                />
                Refresh value
              </button>
              <button
                className="secondary-button"
                disabled={!dashboard.holdings.length}
                onClick={() => setShowRebalance(true)}
                type="button"
              >
                <Scale size={16} />
                Rebalance
              </button>
              <button
                aria-label="Portfolio settings"
                className="icon-button"
                onClick={openSettings}
                type="button"
              >
                <Settings size={17} />
              </button>
            </div>
          </div>

          <div className="portfolio-kpi-grid">
            <PortfolioKpi
              label="Portfolio value"
              value={currency.format(dashboard.totalValue)}
              note={`${dashboard.holdings.length} holdings`}
            />
            <PortfolioKpi
              label="Daily change"
              value={`${dashboard.dayChange >= 0 ? "+" : ""}${currency.format(dashboard.dayChange)}`}
              note={formatPercent(dashboard.dayChangePercent)}
              tone={dashboard.dayChange >= 0 ? "up" : "down"}
            />
            <PortfolioKpi
              label="Total return"
              value={`${dashboard.totalPnl >= 0 ? "+" : ""}${currency.format(dashboard.totalPnl)}`}
              note={formatPercent(dashboard.totalReturnPercent)}
              tone={dashboard.totalPnl >= 0 ? "up" : "down"}
            />
            <PortfolioKpi
              label="Cash"
              value={currency.format(dashboard.portfolio.cashBalance)}
              note={`${dashboard.targetCashAllocation.toFixed(1)}% target`}
            />
          </div>

          <div className="portfolio-analytics-grid">
            <section className="panel portfolio-history-panel">
              <div className="panel-header portfolio-chart-header">
                <div>
                  <h2>Performance history</h2>
                  <span>
                    Value and return against{" "}
                    {dashboard.portfolio.benchmarkTicker}
                  </span>
                </div>
                <div className="portfolio-chart-controls">
                  <button
                    className={chartMode === "value" ? "selected" : ""}
                    onClick={() => setChartMode("value")}
                    type="button"
                  >
                    Value
                  </button>
                  <button
                    className={chartMode === "return" ? "selected" : ""}
                    onClick={() => setChartMode("return")}
                    type="button"
                  >
                    Return
                  </button>
                </div>
              </div>
              <PortfolioHistoryChart
                history={history ?? []}
                mode={chartMode}
                range={chartRange}
                showBenchmark={showBenchmark}
              />
              <div className="portfolio-chart-footer">
                <div>
                  {(["1M", "3M", "6M", "1Y", "All"] as const).map((range) => (
                    <button
                      className={chartRange === range ? "selected" : ""}
                      key={range}
                      onClick={() => setChartRange(range)}
                      type="button"
                    >
                      {range}
                    </button>
                  ))}
                </div>
                <label>
                  <input
                    checked={showBenchmark}
                    onChange={(event) =>
                      setShowBenchmark(event.target.checked)
                    }
                    type="checkbox"
                  />
                  {dashboard.portfolio.benchmarkTicker}
                </label>
              </div>
            </section>

            <section className="panel portfolio-allocation-panel">
              <div className="panel-header">
                <div>
                  <h2>Allocation</h2>
                  <span>
                    {dashboard.totalTargetAllocation.toFixed(1)}% assigned
                  </span>
                </div>
              </div>
              <div className="portfolio-allocation-list">
                {dashboard.holdings.length ? (
                  dashboard.holdings
                    .slice()
                    .sort(
                      (left, right) =>
                        right.marketValue - left.marketValue
                    )
                    .map((holding) => (
                      <div
                        className="portfolio-allocation-row"
                        key={holding._id}
                      >
                        <div>
                          <strong>{holding.ticker}</strong>
                          <span>
                            {holding.actualAllocation.toFixed(1)}% actual ·{" "}
                            {holding.targetAllocation.toFixed(1)}% target
                          </span>
                        </div>
                        <em
                          className={
                            Math.abs(holding.allocationDrift) >= 5
                              ? "warning"
                              : ""
                          }
                        >
                          {formatPercent(holding.allocationDrift)}
                        </em>
                        <div className="portfolio-allocation-track">
                          <span
                            style={{
                              width: `${Math.min(holding.actualAllocation, 100)}%`,
                            }}
                          />
                          <i
                            style={{
                              left: `${Math.min(holding.targetAllocation, 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    ))
                ) : (
                  <PortfolioEmptyCopy>
                    Add holdings to see actual and target allocations.
                  </PortfolioEmptyCopy>
                )}
              </div>
            </section>
          </div>

          <div className="portfolio-health-grid">
            <PortfolioHealthCard
              icon={<BriefcaseBusiness size={17} />}
              label="Largest position"
              value={
                dashboard.health.largestHolding?.ticker ?? "No holdings"
              }
              note={
                dashboard.health.largestHolding
                  ? `${dashboard.health.largestHolding.actualAllocation.toFixed(1)}% of portfolio`
                  : "Add a stock"
              }
            />
            <PortfolioHealthCard
              icon={<Scale size={17} />}
              label="Largest drift"
              value={dashboard.health.largestDrift?.ticker ?? "Balanced"}
              note={
                dashboard.health.largestDrift
                  ? formatPercent(
                      dashboard.health.largestDrift.allocationDrift
                    )
                  : "No drift"
              }
              warning={
                Math.abs(
                  dashboard.health.largestDrift?.allocationDrift ?? 0
                ) >= 5
              }
            />
            <PortfolioHealthCard
              icon={<BarChart3 size={17} />}
              label="Top sector"
              value={dashboard.sectorBreakdown[0]?.sector ?? "No exposure"}
              note={
                dashboard.sectorBreakdown[0]
                  ? `${dashboard.sectorBreakdown[0].allocation.toFixed(1)}% allocation`
                  : "Add holdings"
              }
            />
            <PortfolioHealthCard
              icon={<TriangleAlert size={17} />}
              label="Price health"
              value={
                dashboard.health.stalePriceCount
                  ? `${dashboard.health.stalePriceCount} stale`
                  : "Current"
              }
              note={
                dashboard.portfolio.lastValuationStatus ?? "Not refreshed"
              }
              warning={dashboard.health.stalePriceCount > 0}
            />
          </div>

          <section className="panel portfolio-holdings-panel">
            <div className="panel-header">
              <div>
                <h2>Holdings</h2>
                <span>
                  Actual allocation, target weight, and position performance
                </span>
              </div>
              <button
                className="primary-button compact"
                onClick={() => openHolding()}
                type="button"
              >
                <Plus size={15} />
                Add holding
              </button>
            </div>
            {dashboard.holdings.length ? (
              <div className="multi-portfolio-table">
                <div className="multi-portfolio-table-head">
                  <span>Company</span>
                  <span>Price</span>
                  <span>Shares</span>
                  <span>Value</span>
                  <span>P/L</span>
                  <span>Actual / Target</span>
                  <span />
                </div>
                {dashboard.holdings.map((holding) => (
                  <article
                    className="multi-portfolio-table-row"
                    key={holding._id}
                  >
                    <button
                      className="portfolio-company-button"
                      onClick={() => onOpenResearch(holding.ticker)}
                      type="button"
                    >
                      <span>{holding.ticker.slice(0, 1)}</span>
                      <div>
                        <strong>
                          {holding.stock?.companyName ?? holding.ticker}
                        </strong>
                        <small>
                          {holding.ticker} ·{" "}
                          {holding.stock?.sector ?? "Unknown sector"}
                        </small>
                      </div>
                    </button>
                    <div>
                      <strong>
                        {holding.stock
                          ? currency.format(holding.stock.price)
                          : "Unavailable"}
                      </strong>
                      <small
                        className={
                          holding.priceIsStale ? "portfolio-stale" : ""
                        }
                      >
                        {holding.priceIsStale ? "Stale" : "Current"}
                      </small>
                    </div>
                    <div>
                      <strong>{holding.shares.toFixed(4)}</strong>
                      <small>
                        Avg {currency.format(holding.averageCost)}
                      </small>
                    </div>
                    <strong>{currency.format(holding.marketValue)}</strong>
                    <div
                      className={holding.gainLoss >= 0 ? "up" : "down"}
                    >
                      <strong>
                        {holding.gainLoss >= 0 ? "+" : ""}
                        {currency.format(holding.gainLoss)}
                      </strong>
                      <small>{formatPercent(holding.gainLossPercent)}</small>
                    </div>
                    <div>
                      <strong>
                        {holding.actualAllocation.toFixed(1)}% /{" "}
                        {holding.targetAllocation.toFixed(1)}%
                      </strong>
                      <small>
                        Drift {formatPercent(holding.allocationDrift)}
                      </small>
                    </div>
                    <div className="portfolio-row-menu">
                      <button
                        aria-label={`Edit ${holding.ticker}`}
                        onClick={() => openHolding(holding)}
                        type="button"
                      >
                        <Edit3 size={15} />
                      </button>
                      <button
                        aria-label={`Remove ${holding.ticker}`}
                        onClick={() => {
                          if (
                            portfolioId &&
                            window.confirm(
                              `Remove ${holding.ticker} from this portfolio?`
                            )
                          ) {
                            void removeHolding({
                              portfolioId,
                              ticker: holding.ticker,
                            });
                          }
                        }}
                        type="button"
                      >
                        <X size={15} />
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            ) : (
              <div className="portfolio-empty-state">
                <BriefcaseBusiness size={30} />
                <h2>No holdings yet</h2>
                <p>
                  Add 5–10 stocks, enter target allocations, then refresh the
                  portfolio to begin its history.
                </p>
                <button
                  className="primary-button"
                  onClick={() => openHolding()}
                  type="button"
                >
                  <Plus size={16} />
                  Add first holding
                </button>
              </div>
            )}
          </section>

          <section className="panel portfolio-activity-panel-v2">
            <div className="panel-header">
              <div>
                <h2>Recent activity</h2>
                <span>Portfolio changes and valuation updates</span>
              </div>
            </div>
            <div className="portfolio-activity-list">
              {activities?.length ? (
                activities.map((activity) => (
                  <div key={activity._id}>
                    <span />
                    <div>
                      <strong>{activity.summary}</strong>
                      <small>{formatDateTime(activity.occurredAt)}</small>
                    </div>
                  </div>
                ))
              ) : (
                <PortfolioEmptyCopy>
                  Portfolio activity will appear here.
                </PortfolioEmptyCopy>
              )}
            </div>
          </section>
        </>
      ) : (
        <PortfolioLoading />
      )}

      {showCreate && (
        <PortfolioDialog
          title="Create portfolio"
          subtitle="Choose how this portfolio should be valued."
          onClose={() => setShowCreate(false)}
        >
          <PortfolioForm
            form={portfolioForm}
            busy={busy === "create"}
            submitLabel="Create portfolio"
            onChange={setPortfolioForm}
            onSubmit={handleCreate}
          />
        </PortfolioDialog>
      )}

      {showSettings && dashboard && (
        <PortfolioDialog
          title="Portfolio settings"
          subtitle="Update the name, benchmark, cash, and description."
          onClose={() => setShowSettings(false)}
        >
          <PortfolioForm
            form={portfolioForm}
            busy={busy === "settings"}
            editing
            submitLabel="Save changes"
            onChange={setPortfolioForm}
            onSubmit={handleSettings}
          />
          <div className="portfolio-danger-actions">
            <button onClick={() => void duplicateCurrent()} type="button">
              <Copy size={15} />
              Duplicate
            </button>
            <button onClick={() => void archiveCurrent()} type="button">
              <Archive size={15} />
              Archive
            </button>
          </div>
        </PortfolioDialog>
      )}

      {showHolding && portfolioId && (
        <PortfolioDialog
          title={dashboard?.holdings.some(
            (holding) => holding.ticker === holdingDraft.ticker
          )
            ? `Edit ${holdingDraft.ticker}`
            : "Add holding"}
          subtitle="Set current position details and the target portfolio weight."
          onClose={() => setShowHolding(false)}
        >
          <form className="portfolio-form" onSubmit={handleHolding}>
            <label>
              <span>Find a stock</span>
              <div className="portfolio-stock-search">
                <Search size={15} />
                <input
                  value={portfolioSearch}
                  placeholder="Search company or ticker"
                  onChange={(event) => setPortfolioSearch(event.target.value)}
                />
              </div>
            </label>
            {portfolioSearch && (
              <div className="portfolio-search-results">
                {(stockSearch ?? []).slice(0, 6).map((stock) => (
                  <button
                    key={stock.ticker}
                    onClick={() => {
                      setHoldingDraft((current) => ({
                        ...current,
                        ticker: stock.ticker,
                        averageCost:
                          Number(current.averageCost) > 0
                            ? current.averageCost
                            : String(stock.price),
                      }));
                      setPortfolioSearch("");
                    }}
                    type="button"
                  >
                    <strong>{stock.ticker}</strong>
                    <span>{stock.companyName}</span>
                    <em>{currency.format(stock.price)}</em>
                  </button>
                ))}
              </div>
            )}
            <div className="portfolio-form-grid">
              <label>
                <span>Ticker</span>
                <input
                  required
                  value={holdingDraft.ticker}
                  onChange={(event) =>
                    setHoldingDraft((current) => ({
                      ...current,
                      ticker: event.target.value.toUpperCase(),
                    }))
                  }
                />
              </label>
              <label>
                <span>Shares / units</span>
                <input
                  min="0"
                  step="any"
                  type="number"
                  value={holdingDraft.shares}
                  onChange={(event) =>
                    setHoldingDraft((current) => ({
                      ...current,
                      shares: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>Average cost</span>
                <input
                  min="0"
                  step="0.01"
                  type="number"
                  value={holdingDraft.averageCost}
                  onChange={(event) =>
                    setHoldingDraft((current) => ({
                      ...current,
                      averageCost: event.target.value,
                    }))
                  }
                />
              </label>
              <label>
                <span>Target allocation %</span>
                <input
                  max="100"
                  min="0"
                  step="0.01"
                  type="number"
                  value={holdingDraft.targetAllocation}
                  onChange={(event) =>
                    setHoldingDraft((current) => ({
                      ...current,
                      targetAllocation: event.target.value,
                    }))
                  }
                />
              </label>
            </div>
            <label>
              <span>Position note</span>
              <textarea
                rows={3}
                value={holdingDraft.notes}
                onChange={(event) =>
                  setHoldingDraft((current) => ({
                    ...current,
                    notes: event.target.value,
                  }))
                }
              />
            </label>
            <button
              className="primary-button portfolio-form-submit"
              disabled={busy === "holding"}
              type="submit"
            >
              {busy === "holding" ? "Saving…" : "Save holding"}
            </button>
          </form>
        </PortfolioDialog>
      )}

      {showRebalance && rebalance && dashboard && portfolioId && (
        <PortfolioDialog
          wide
          title="Rebalance proposal"
          subtitle={`Preview only for ${dashboard.portfolio.type === "actual" ? "actual holdings" : "this model portfolio"}.`}
          onClose={() => setShowRebalance(false)}
        >
          <div className="portfolio-rebalance-summary">
            <PortfolioKpi
              label="Investable value"
              value={currency.format(rebalance.totalValue)}
            />
            <PortfolioKpi
              label="Target cash"
              value={currency.format(rebalance.targetCashValue)}
            />
          </div>
          <div className="portfolio-rebalance-table">
            <div>
              <span>Stock</span>
              <span>Current</span>
              <span>Target</span>
              <span>Difference</span>
              <span>Est. shares</span>
            </div>
            {rebalance.rows.map((row) => (
              <div key={row.ticker}>
                <strong>{row.ticker}</strong>
                <span>{currency.format(row.currentValue)}</span>
                <span>{currency.format(row.targetValue)}</span>
                <span className={row.difference >= 0 ? "up" : "down"}>
                  {row.difference >= 0 ? "Buy " : "Sell "}
                  {currency.format(Math.abs(row.difference))}
                </span>
                <span>{Math.abs(row.estimatedShares).toFixed(4)}</span>
              </div>
            ))}
          </div>
          {dashboard.portfolio.type === "model" ? (
            <button
              className="primary-button portfolio-form-submit"
              onClick={async () => {
                setBusy("rebalance");
                try {
                  await applyModelRebalance({ portfolioId });
                  setShowRebalance(false);
                  setMessage("Simulated rebalance applied.");
                } catch (error) {
                  setMessage(errorMessage(error));
                } finally {
                  setBusy(null);
                }
              }}
              type="button"
            >
              Apply simulated rebalance
            </button>
          ) : (
            <p className="portfolio-rebalance-note">
              This proposal does not execute trades or change actual holdings.
            </p>
          )}
        </PortfolioDialog>
      )}

      {dashboard?.portfolio.type === "model" &&
        !dashboard.portfolio.initializedAt &&
        dashboard.holdings.length > 0 && (
          <div className="portfolio-model-banner">
            <div>
              <strong>Model allocation is ready to initialize</strong>
              <span>
                Convert target weights into fractional units using current
                stored prices.
              </span>
            </div>
            <button
              className="primary-button"
              onClick={async () => {
                if (!portfolioId) return;
                try {
                  await initializeModel({ portfolioId });
                  setMessage("Model portfolio initialized.");
                } catch (error) {
                  setMessage(errorMessage(error));
                }
              }}
              type="button"
            >
              Initialize model
            </button>
          </div>
        )}
    </section>
  );
}

function PortfolioOverview({
  portfolios,
  archivedCount,
  onOpen,
  onCreate,
}: {
  portfolios: PortfolioListItem[];
  archivedCount: number;
  onOpen: (id: string) => void;
  onCreate: () => void;
}) {
  const totalValue = portfolios.reduce(
    (sum, portfolio) => sum + portfolio.totalValue,
    0
  );
  const totalDayChange = portfolios.reduce(
    (sum, portfolio) => sum + portfolio.dayChange,
    0
  );
  const totalHoldings = portfolios.reduce(
    (sum, portfolio) => sum + portfolio.holdingCount,
    0
  );
  return (
    <>
      <div className="portfolio-kpi-grid all-portfolios-kpis">
        <PortfolioKpi
          label="Combined value"
          value={currency.format(totalValue)}
          note={`${portfolios.length} active portfolios`}
        />
        <PortfolioKpi
          label="Today"
          value={`${totalDayChange >= 0 ? "+" : ""}${currency.format(totalDayChange)}`}
          tone={totalDayChange >= 0 ? "up" : "down"}
        />
        <PortfolioKpi
          label="Holdings"
          value={String(totalHoldings)}
          note="Across portfolios"
        />
        <PortfolioKpi
          label="Archived"
          value={String(archivedCount)}
          note="History preserved"
        />
      </div>
      <div className="portfolio-card-grid">
        {portfolios.map((portfolio) => (
          <button
            className="portfolio-overview-card"
            key={portfolio._id}
            onClick={() => onOpen(portfolio._id)}
            type="button"
          >
            <div className="portfolio-card-heading">
              <span>
                <BriefcaseBusiness size={17} />
              </span>
              <div>
                <strong>{portfolio.name}</strong>
                <small>
                  {portfolio.type} · {portfolio.baseCurrency}
                </small>
              </div>
              <em className={portfolio.lastValuationStatus ?? "stale"}>
                {portfolio.lastValuationStatus ?? "new"}
              </em>
            </div>
            <strong className="portfolio-card-value">
              {currency.format(portfolio.totalValue)}
            </strong>
            <div className="portfolio-card-metrics">
              <span>
                Today
                <strong
                  className={
                    portfolio.snapshotChangePercent >= 0 ? "up" : "down"
                  }
                >
                  {formatPercent(portfolio.snapshotChangePercent)}
                </strong>
              </span>
              <span>
                Return
                <strong
                  className={portfolio.totalPnl >= 0 ? "up" : "down"}
                >
                  {formatPercent(portfolio.totalReturnPercent)}
                </strong>
              </span>
              <span>
                Holdings
                <strong>{portfolio.holdingCount}</strong>
              </span>
            </div>
            <div className="portfolio-card-footer">
              <span>
                {portfolio.totalTargetAllocation.toFixed(1)}% target assigned
              </span>
              <span>{formatDateTime(portfolio.lastValuedAt)}</span>
            </div>
          </button>
        ))}
        <button
          className="portfolio-overview-card create-card"
          onClick={onCreate}
          type="button"
        >
          <Plus size={24} />
          <strong>Create another portfolio</strong>
          <span>Actual holdings or a model strategy</span>
        </button>
      </div>
    </>
  );
}

function PortfolioKpi({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: "up" | "down";
}) {
  return (
    <article className="portfolio-kpi-card">
      <span>{label}</span>
      <strong className={tone}>{value}</strong>
      {note && <small className={tone}>{note}</small>}
    </article>
  );
}

function PortfolioHealthCard({
  icon,
  label,
  value,
  note,
  warning,
}: {
  icon: ReactNode;
  label: string;
  value: string;
  note: string;
  warning?: boolean;
}) {
  return (
    <article className={`portfolio-health-card${warning ? " warning" : ""}`}>
      <span>{icon}</span>
      <div>
        <small>{label}</small>
        <strong>{value}</strong>
        <em>{note}</em>
      </div>
    </article>
  );
}

function PortfolioHistoryChart({
  history,
  mode,
  range,
  showBenchmark,
}: {
  history: Array<{
    marketDate: string;
    totalValue: number;
    benchmarkValue?: number;
  }>;
  mode: "value" | "return";
  range: "1M" | "3M" | "6M" | "1Y" | "All";
  showBenchmark: boolean;
}) {
  const days = { "1M": 31, "3M": 93, "6M": 186, "1Y": 366, All: Infinity }[
    range
  ];
  const lastDate = history.length
    ? new Date(history[history.length - 1].marketDate).getTime()
    : 0;
  const points = history.filter(
    (point) =>
      days === Infinity ||
      new Date(point.marketDate).getTime() >=
        lastDate - days * 24 * 60 * 60 * 1000
  );
  if (points.length < 2) {
    return (
      <div className="portfolio-chart-empty">
        <LineChart size={26} />
        <strong>History begins with the first refresh</strong>
        <span>Refresh on two market dates to generate a performance line.</span>
      </div>
    );
  }
  const width = 760;
  const height = 280;
  const padding = 24;
  const firstValue = points[0].totalValue || 1;
  const firstBenchmark = points[0].benchmarkValue || 1;
  const portfolioValues = points.map((point) =>
    mode === "value"
      ? point.totalValue
      : ((point.totalValue / firstValue) - 1) * 100
  );
  const benchmarkValues = points.map((point) =>
    mode === "value"
      ? (point.benchmarkValue ?? point.totalValue)
      : (((point.benchmarkValue ?? firstBenchmark) / firstBenchmark) - 1) * 100
  );
  const values = showBenchmark
    ? [...portfolioValues, ...benchmarkValues]
    : portfolioValues;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const toLine = (series: number[]) =>
    series
      .map((value, index) => {
        const x =
          padding +
          (index / Math.max(series.length - 1, 1)) * (width - padding * 2);
        const y =
          height -
          padding -
          ((value - min) / span) * (height - padding * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  const lastValue = portfolioValues[portfolioValues.length - 1];
  return (
    <div className="portfolio-history-chart">
      <div className="portfolio-chart-value">
        <strong>
          {mode === "value"
            ? currency.format(points[points.length - 1].totalValue)
            : formatPercent(lastValue)}
        </strong>
        <span>
          {points[0].marketDate} — {points[points.length - 1].marketDate}
        </span>
      </div>
      <svg
        aria-label="Portfolio performance chart"
        role="img"
        viewBox={`0 0 ${width} ${height}`}
      >
        <defs>
          <linearGradient id="portfolioArea" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="#2563eb" stopOpacity="0.24" />
            <stop offset="100%" stopColor="#2563eb" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0.25, 0.5, 0.75].map((ratio) => (
          <line
            className="portfolio-chart-grid-line"
            key={ratio}
            x1={padding}
            x2={width - padding}
            y1={height * ratio}
            y2={height * ratio}
          />
        ))}
        <polygon
          fill="url(#portfolioArea)"
          points={`${toLine(portfolioValues)} ${width - padding},${height - padding} ${padding},${height - padding}`}
        />
        {showBenchmark && (
          <polyline
            className="portfolio-benchmark-line"
            fill="none"
            points={toLine(benchmarkValues)}
          />
        )}
        <polyline
          className="portfolio-value-line"
          fill="none"
          points={toLine(portfolioValues)}
        />
      </svg>
    </div>
  );
}

function PortfolioDialog({
  title,
  subtitle,
  onClose,
  children,
  wide,
}: {
  title: string;
  subtitle: string;
  onClose: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  return (
    <div className="portfolio-dialog-backdrop" role="presentation">
      <section
        aria-labelledby="portfolio-dialog-title"
        aria-modal="true"
        className={`portfolio-dialog${wide ? " wide" : ""}`}
        role="dialog"
      >
        <div className="portfolio-dialog-header">
          <div>
            <h2 id="portfolio-dialog-title">{title}</h2>
            <p>{subtitle}</p>
          </div>
          <button aria-label="Close" onClick={onClose} type="button">
            <X size={18} />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}

function PortfolioForm({
  form,
  busy,
  submitLabel,
  editing,
  onChange,
  onSubmit,
}: {
  form: PortfolioFormState;
  busy: boolean;
  submitLabel: string;
  editing?: boolean;
  onChange: (form: PortfolioFormState) => void;
  onSubmit: (event: FormEvent) => void;
}) {
  return (
    <form className="portfolio-form" onSubmit={onSubmit}>
      <div className="portfolio-form-grid">
        <label>
          <span>Name</span>
          <input
            required
            value={form.name}
            onChange={(event) =>
              onChange({ ...form, name: event.target.value })
            }
          />
        </label>
        <label>
          <span>Portfolio type</span>
          <select
            disabled={editing}
            value={form.type}
            onChange={(event) =>
              onChange({
                ...form,
                type: event.target.value as "actual" | "model",
              })
            }
          >
            <option value="actual">Actual holdings</option>
            <option value="model">Model allocation</option>
          </select>
        </label>
        {form.type === "model" && (
          <label>
            <span>Starting value</span>
            <input
              disabled={editing}
              min="0.01"
              step="0.01"
              type="number"
              value={form.startingValue}
              onChange={(event) =>
                onChange({ ...form, startingValue: event.target.value })
              }
            />
          </label>
        )}
        {form.type === "actual" && (
          <label>
            <span>Cash balance</span>
            <input
              min="0"
              step="0.01"
              type="number"
              value={form.cashBalance}
              onChange={(event) =>
                onChange({ ...form, cashBalance: event.target.value })
              }
            />
          </label>
        )}
        <label>
          <span>Benchmark</span>
          <input
            value={form.benchmarkTicker}
            onChange={(event) =>
              onChange({
                ...form,
                benchmarkTicker: event.target.value.toUpperCase(),
              })
            }
          />
        </label>
      </div>
      <label>
        <span>Description</span>
        <textarea
          rows={3}
          value={form.description}
          onChange={(event) =>
            onChange({ ...form, description: event.target.value })
          }
        />
      </label>
      <button
        className="primary-button portfolio-form-submit"
        disabled={busy}
        type="submit"
      >
        {busy ? "Saving…" : submitLabel}
      </button>
    </form>
  );
}

function PortfolioLoading() {
  return (
    <div className="portfolio-loading">
      <RefreshCw className="spin" size={22} />
      <span>Loading portfolios…</span>
    </div>
  );
}

function PortfolioEmptyCopy({ children }: { children: ReactNode }) {
  return <p className="portfolio-empty-copy">{children}</p>;
}
