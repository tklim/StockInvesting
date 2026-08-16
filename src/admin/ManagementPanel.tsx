import { useEffect, useMemo, useState } from "react";
import { LoaderCircle, Plus, Save, Trash2 } from "lucide-react";
import type { AdminTarget } from "./operations";
import type { ManagementAction } from "./management";

type RecordValue = Record<string, unknown>;
const record = (value: unknown): RecordValue | undefined =>
  value && typeof value === "object" && !Array.isArray(value) ? (value as RecordValue) : undefined;
const text = (value: unknown) => typeof value === "string" ? value : "";
const number = (value: unknown) => typeof value === "number" ? value : 0;
type SymbolResult = { symbol: string; displaySymbol: string; description: string; type: string };

const adminToken = () => {
  const token = document.querySelector<HTMLMetaElement>('meta[name="local-admin-token"]')?.content;
  if (!token) throw new Error("The local admin session token is missing. Reload this page.");
  return token;
};

export function ManagementPanel() {
  const [target, setTarget] = useState<AdminTarget>("development");
  const [data, setData] = useState<RecordValue | null>(null);
  const [selectedPortfolioId, setSelectedPortfolioId] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [watchlistName, setWatchlistName] = useState("");
  const [ticker, setTicker] = useState("");
  const [symbolResults, setSymbolResults] = useState<SymbolResult[]>([]);
  const [selectedSymbol, setSelectedSymbol] = useState<SymbolResult | null>(null);
  const [searchingSymbols, setSearchingSymbols] = useState(false);
  const [listName, setListName] = useState("");
  const [portfolioName, setPortfolioName] = useState("");
  const [portfolioType, setPortfolioType] = useState<"actual" | "model">("actual");
  const [holdingTicker, setHoldingTicker] = useState("");
  const [shares, setShares] = useState("0");
  const [averageCost, setAverageCost] = useState("0");
  const [allocation, setAllocation] = useState("0");

  const load = async (portfolioId = selectedPortfolioId) => {
    setLoading(true);
    try {
      const response = await fetch("/__local_admin/manage/read", { method: "POST", headers: { "Content-Type": "application/json", "X-Local-Admin-Token": adminToken() }, body: JSON.stringify({ target, portfolioId }) });
      const payload = await response.json() as RecordValue;
      if (!response.ok || !payload.ok) throw new Error(text(payload.error) || "Unable to load management data.");
      setData(payload);
      const lists = Array.isArray(payload.watchlists) ? payload.watchlists.map(record).filter(Boolean) : [];
      setListName((current) => current || text(lists[0]?.name));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to load management data.");
    } finally { setLoading(false); }
  };
  useEffect(() => { void load(""); }, [target]);
  useEffect(() => { if (selectedPortfolioId) void load(selectedPortfolioId); }, [selectedPortfolioId]);

  const write = async (action: ManagementAction, args: RecordValue, destructive = false) => {
    if (destructive && !window.confirm("This action changes saved data. Continue?")) return;
    setSaving(true); setMessage(null);
    try {
      const response = await fetch("/__local_admin/manage/write", { method: "POST", headers: { "Content-Type": "application/json", "X-Local-Admin-Token": adminToken() }, body: JSON.stringify({ target, action, args }) });
      const payload = await response.json() as RecordValue;
      if (!response.ok || !payload.ok) throw new Error(text(payload.error) || "Unable to save changes.");
      setMessage("Saved.");
      await load(selectedPortfolioId);
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save changes."); }
    finally { setSaving(false); }
  };

  const searchSymbols = async () => {
    setSearchingSymbols(true); setSelectedSymbol(null); setSymbolResults([]); setMessage(null);
    try {
      const response = await fetch("/__local_admin/manage/search-symbols", { method: "POST", headers: { "Content-Type": "application/json", "X-Local-Admin-Token": adminToken() }, body: JSON.stringify({ target, query: ticker }) });
      const payload = await response.json() as RecordValue;
      if (!response.ok || !payload.ok || !Array.isArray(payload.results)) throw new Error(text(payload.error) || "Unable to search symbols.");
      setSymbolResults(payload.results.flatMap((item) => { const result = record(item); const symbol = text(result?.symbol); const description = text(result?.description); return symbol && description ? [{ symbol, displaySymbol: text(result?.displaySymbol) || symbol, description, type: text(result?.type) || "Instrument" }] : []; }));
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to search symbols."); }
    finally { setSearchingSymbols(false); }
  };

  const watchlists = useMemo(() => Array.isArray(data?.watchlists) ? data.watchlists.map(record).filter(Boolean) : [], [data]);
  const tickers = useMemo(() => Array.isArray(data?.tickers) ? data.tickers.map(record).filter(Boolean) : [], [data]);
  const portfolios = useMemo(() => Array.isArray(data?.portfolios) ? data.portfolios.map(record).filter(Boolean) : [], [data]);
  const selectedPortfolio = portfolios.find((portfolio) => text(portfolio?._id) === selectedPortfolioId);
  const dashboard = record(data?.dashboard);
  const holdings = Array.isArray(dashboard?.holdings) ? dashboard.holdings.map(record).filter(Boolean) : [];

  return <section className="management-panel" aria-busy={loading || saving}>
    <div className="settings-heading"><div><span className="section-label">Local write access</span><h2>Manage watchlists & portfolios</h2><p>Changes apply only to the selected Convex target.</p></div><label className="target-selector"><span>Convex target</span><select value={target} onChange={(event) => { setTarget(event.target.value as AdminTarget); setSelectedPortfolioId(""); }}><option value="development">Development data</option><option value="production">Production — public site data</option></select></label></div>
    {target === "production" && <div className="production-guard"><strong>Production writes change public-site data.</strong><span>Review each change before saving it.</span></div>}
    {message && <p className="management-message" role="status">{message}</p>}
    {loading ? <div className="watchlist-status-message"><LoaderCircle className="spin" size={17} /> Loading management data…</div> : <div className="management-grid">
      <section className="management-card"><h3>Watchlists</h3><form onSubmit={(event) => { event.preventDefault(); void write("createWatchlist", { name: watchlistName }).then(() => setWatchlistName("")); }}><input value={watchlistName} onChange={(event) => setWatchlistName(event.target.value)} placeholder="New watchlist name" /><button disabled={saving}><Plus size={16} /> Add</button></form><div className="management-list">{watchlists.map((item) => <div key={text(item?._id)}><strong>{text(item?.name)}</strong><button type="button" onClick={() => { const nextName = window.prompt("New watchlist name", text(item?.name)); if (nextName) void write("renameWatchlist", { currentName: text(item?.name), nextName }); }}>Rename</button><button type="button" className="danger-button" onClick={() => { const fallback = watchlists.find((other) => text(other?.name) !== text(item?.name)); void write("deleteWatchlist", { name: text(item?.name), ...(fallback ? { fallbackListName: text(fallback.name) } : {}) }, true); }}>Delete</button></div>)}</div>
      <form className="compact-form" onSubmit={(event) => { event.preventDefault(); void searchSymbols(); }}><input value={ticker} onChange={(event) => { setTicker(event.target.value); setSelectedSymbol(null); }} placeholder="Search ticker or company" /><button disabled={searchingSymbols || ticker.trim().length < 2}>{searchingSymbols ? <LoaderCircle className="spin" size={16} /> : "Search"}</button></form>{symbolResults.length > 0 && <div className="symbol-results" role="listbox" aria-label="Symbol search results">{symbolResults.map((result) => <button type="button" role="option" aria-selected={selectedSymbol?.symbol === result.symbol} key={`${result.symbol}-${result.description}`} onClick={() => { setSelectedSymbol(result); setTicker(result.symbol); }}><strong>{result.displaySymbol}</strong><span>{result.description} · {result.type}</span></button>)}</div>}<form className="compact-form save-ticker-form" onSubmit={(event) => { event.preventDefault(); if (selectedSymbol) void write("saveTicker", { ticker: selectedSymbol.symbol, listName }).then(() => { setTicker(""); setSelectedSymbol(null); setSymbolResults([]); }); }}><span className="selected-symbol">{selectedSymbol ? `${selectedSymbol.symbol} — ${selectedSymbol.description}` : "Select a verified symbol first"}</span><select value={listName} onChange={(event) => setListName(event.target.value)}>{watchlists.map((item) => <option key={text(item?._id)} value={text(item?.name)}>{text(item?.name)}</option>)}</select><button disabled={saving || !selectedSymbol}>Save ticker</button></form><div className="management-list ticker-list">{tickers.map((item) => <div key={text(item?.ticker)}><span><strong>{text(item?.ticker)}</strong> · {text(item?.listName)}</span><button type="button" className="danger-button" onClick={() => void write("removeTicker", { ticker: text(item?.ticker) }, true)}><Trash2 size={15} /> Remove</button></div>)}</div></section>
      <section className="management-card"><h3>Portfolios</h3><form className="portfolio-create" onSubmit={(event) => { event.preventDefault(); void write("createPortfolio", { name: portfolioName, type: portfolioType, benchmarkTicker: "SPY", ...(portfolioType === "model" ? { startingValue: 10000 } : { cashBalance: 0 }) }).then(() => setPortfolioName("")); }}><input value={portfolioName} onChange={(event) => setPortfolioName(event.target.value)} placeholder="New portfolio name" /><select value={portfolioType} onChange={(event) => setPortfolioType(event.target.value as "actual" | "model")}><option value="actual">Actual</option><option value="model">Model</option></select><button disabled={saving}><Plus size={16} /> Create</button></form><select className="portfolio-picker" value={selectedPortfolioId} onChange={(event) => setSelectedPortfolioId(event.target.value)}><option value="">Select a portfolio</option>{portfolios.map((item) => <option value={text(item?._id)} key={text(item?._id)}>{text(item?.name)} ({text(item?.status)})</option>)}</select>{selectedPortfolioId && <><div className="management-actions"><button type="button" onClick={() => { const name = window.prompt("Portfolio name", text(selectedPortfolio?.name)); if (!name) return; const benchmarkTicker = window.prompt("Benchmark ticker", text(selectedPortfolio?.benchmarkTicker) || "SPY"); if (!benchmarkTicker) return; const cashBalance = window.prompt("Cash balance", String(number(selectedPortfolio?.cashBalance))); if (cashBalance === null) return; void write("updatePortfolio", { portfolioId: selectedPortfolioId, name, description: text(selectedPortfolio?.description), benchmarkTicker, cashBalance: Number(cashBalance) }); }}>Edit settings</button><button type="button" onClick={() => { const name = window.prompt("Name for the copy"); if (name) void write("duplicatePortfolio", { portfolioId: selectedPortfolioId, name }); }}>Duplicate</button><button type="button" className="danger-button" onClick={() => void write("archivePortfolio", { portfolioId: selectedPortfolioId }, true)}>Archive</button></div><h4>Holdings</h4><form className="holding-form" onSubmit={(event) => { event.preventDefault(); void write("upsertHolding", { portfolioId: selectedPortfolioId, ticker: holdingTicker, shares: Number(shares), averageCost: Number(averageCost), targetAllocation: Number(allocation), notes: "" }).then(() => setHoldingTicker("")); }}><input value={holdingTicker} onChange={(event) => setHoldingTicker(event.target.value)} placeholder="Ticker" /><input value={shares} onChange={(event) => setShares(event.target.value)} type="number" min="0" step="any" placeholder="Shares" /><input value={averageCost} onChange={(event) => setAverageCost(event.target.value)} type="number" min="0" step="any" placeholder="Cost" /><input value={allocation} onChange={(event) => setAllocation(event.target.value)} type="number" min="0" max="100" step="any" placeholder="Target %" /><button disabled={saving}><Save size={16} /> Save holding</button></form><div className="management-list">{holdings.map((holding) => <div key={text(holding?._id)}><span><strong>{text(holding?.ticker)}</strong> · {number(holding?.shares)} shares · {number(holding?.targetAllocation)}%</span><button type="button" className="danger-button" onClick={() => void write("removeHolding", { portfolioId: selectedPortfolioId, ticker: text(holding?.ticker) }, true)}><Trash2 size={15} /> Remove</button></div>)}</div></>}</section>
    </div>}
  </section>;
}
