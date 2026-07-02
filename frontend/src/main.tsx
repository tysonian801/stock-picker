import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Bell, LineChart, Lock, Play, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import {
  addTrade,
  getSession,
  getPortfolio,
  getRecommendations,
  getScans,
  getStockPerformance,
  getStocks,
  getTrades,
  login,
  runScan,
} from "./api";
import type { MockTrade, Portfolio, Recommendation, ScanRun, Stock, StockPerformance } from "./types";
import "./styles.css";

function App(): JSX.Element {
  const [csrfToken, setCsrfToken] = useState("");
  const [email, setEmail] = useState("admin@example.com");
  const [password, setPassword] = useState("");
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [trades, setTrades] = useState<MockTrade[]>([]);
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [scans, setScans] = useState<ScanRun[]>([]);
  const [performance, setPerformance] = useState<StockPerformance | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [benchmark, setBenchmark] = useState("SPY");
  const [tradeTicker, setTradeTicker] = useState("");
  const [tradeSide, setTradeSide] = useState<"buy" | "sell">("buy");
  const [tradeQuantity, setTradeQuantity] = useState("1");
  const [tradePrice, setTradePrice] = useState("");
  const [tradeNote, setTradeNote] = useState("");
  const [tradeStatus, setTradeStatus] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const selected = useMemo(
    () => recommendations.find((item) => item.id === selectedId) ?? recommendations[0],
    [recommendations, selectedId],
  );

  async function refresh(): Promise<void> {
    setLoading(true);
    setError("");
    try {
      const [nextRecommendations, nextPortfolio, nextTrades, nextStocks, nextScans] = await Promise.all([
        getRecommendations(),
        getPortfolio(),
        getTrades(),
        getStocks(),
        getScans(),
      ]);
      setRecommendations(nextRecommendations);
      setPortfolio(nextPortfolio);
      setTrades(nextTrades);
      setStocks(nextStocks);
      setScans(nextScans);
      if (!selectedId && nextRecommendations.length > 0) {
        setSelectedId(nextRecommendations[0].id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (csrfToken) {
      void refresh();
    }
  }, [csrfToken]);

  useEffect(() => {
    getSession()
      .then((token) => {
        if (token) {
          setCsrfToken(token);
        }
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    if (!selected || !csrfToken) {
      return;
    }
    getStockPerformance(selected.stock.ticker)
      .then(setPerformance)
      .catch(() => setPerformance(null));
  }, [selected?.stock.ticker, csrfToken]);

  useEffect(() => {
    if (!selected) {
      return;
    }
    setTradeTicker(selected.stock.ticker);
    setTradePrice(selected.latest_price === null ? "" : selected.latest_price.toFixed(2));
  }, [selected?.id, selected?.latest_price, selected?.stock.ticker]);

  async function submitLogin(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError("");
    try {
      setCsrfToken(await login(email, password));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }

  async function submitScan(): Promise<void> {
    setLoading(true);
    try {
      await runScan(csrfToken);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
    } finally {
      setLoading(false);
    }
  }

  async function submitTrade(event: React.FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setLoading(true);
    setError("");
    setTradeStatus("");
    try {
      const trade = await addTrade(csrfToken, {
        ticker: tradeTicker.toUpperCase(),
        side: tradeSide,
        quantity: Number(tradeQuantity),
        note: tradeNote || undefined,
      });
      setTradeStatus(
        `${trade.side === "buy" ? "Bought" : "Sold"} ${trade.quantity} ${trade.ticker} at ${money(trade.price)}`,
      );
      setTradeQuantity("1");
      setTradeNote("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Trade failed");
    } finally {
      setLoading(false);
    }
  }

  function updateTradeTicker(ticker: string): void {
    setTradeTicker(ticker);
    const recommendation = recommendations.find((item) => item.stock.ticker === ticker);
    setTradePrice(recommendation?.latest_price === null ? "" : (recommendation?.latest_price.toFixed(2) ?? ""));
  }

  if (!csrfToken) {
    return (
      <main className="login-shell">
        <form className="login-panel" onSubmit={submitLogin}>
          <ShieldCheck size={32} aria-hidden="true" />
          <h1>Stock Picker</h1>
          <label>
            Email
            <input value={email} onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label>
            Password
            <input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </label>
          <button type="submit">
            <Lock size={16} /> Sign in
          </button>
          {error && <p className="error">{error}</p>}
        </form>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <h1>Stock Picker</h1>
          <p>Paper trading research signals</p>
        </div>
        <div className="actions">
          <button type="button" onClick={refresh} disabled={loading}>
            <RefreshCw size={16} /> Refresh
          </button>
          <button type="button" onClick={submitScan} disabled={loading}>
            <Play size={16} /> Run scan
          </button>
        </div>
      </header>

      {error && <div className="banner">{error}</div>}

      <section className="metrics">
        <Metric icon={<Activity />} label="Signals" value={recommendations.length.toString()} />
        <Metric icon={<LineChart />} label="Portfolio" value={money(portfolio?.total_market_value ?? 0)} />
        <Metric icon={<Bell />} label="Latest scan" value={scans[0] ? `${scans[0].recommendations_count} recs` : "None"} />
      </section>

      <section className="layout">
        <div className="panel opportunities">
          <div className="panel-heading">
            <h2>Opportunities</h2>
            <span>{new Set(recommendations.map((item) => item.stock.sector)).size} sectors</span>
          </div>
          <div className="opportunity-list">
            {recommendations.map((item) => (
              <button
                type="button"
                key={item.id}
                className={item.id === selected?.id ? "opportunity selected" : "opportunity"}
                onClick={() => setSelectedId(item.id)}
              >
                <strong>{item.stock.ticker}</strong>
                <span>{item.horizon.replace("_", " ")}</span>
                <Score value={item.opportunity_score} />
                <span>{item.latest_price === null ? "No price" : money(item.latest_price)}</span>
                <small>{item.signal.replace("_", " ")}</small>
              </button>
            ))}
          </div>
        </div>

        <article className="panel detail">
          {selected ? (
            <>
              <div className="detail-title">
                <div>
                  <h2>{selected.stock.ticker}</h2>
                  <p>
                    {selected.stock.name} ·{" "}
                    {selected.latest_price === null
                      ? "No current price"
                      : `${money(selected.latest_price)} latest`}
                  </p>
                </div>
                <div className="score-pair">
                  <Score value={selected.opportunity_score} label="Opportunity" />
                  <Score value={selected.confidence_score} label="Confidence" />
                </div>
              </div>
              <p className="thesis">{selected.thesis}</p>
              <p className="risk">{selected.risk_summary}</p>
              {performance && <PerformanceChart performance={performance} />}
              <div className="evidence-grid">
                {selected.evidence.map((item) => (
                  <div key={item.id} className="evidence">
                    <strong>{item.kind}</strong>
                    <span>{item.source}</span>
                    <p>{item.summary}</p>
                    <small>Provider timestamp: {dateOnly(item.provider_timestamp)}</small>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p>No recommendations yet. Run a scan to populate research signals.</p>
          )}
        </article>
      </section>

      <section className="layout bottom">
        <div className="panel">
          <div className="panel-heading">
            <h2>Portfolio</h2>
            <div className="segmented">
              {["SPY", "QQQ", "VTI"].map((symbol) => (
                <button
                  type="button"
                  key={symbol}
                  className={benchmark === symbol ? "active" : ""}
                  onClick={() => setBenchmark(symbol)}
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>
          <div className="portfolio-summary">
            <strong>{portfolio?.total_return_pct.toFixed(2) ?? "0.00"}%</strong>
            <span>{benchmark}: {portfolio?.benchmarks[benchmark]?.toFixed(2) ?? "0.00"}%</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Qty</th>
                <th>Value</th>
                <th>Return</th>
              </tr>
            </thead>
            <tbody>
              {portfolio?.holdings.map((holding) => (
                <tr key={holding.ticker}>
                  <td>{holding.ticker}</td>
                  <td>{holding.quantity}</td>
                  <td>{money(holding.market_value)}</td>
                  <td>{holding.unrealized_return_pct.toFixed(2)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <form className="panel trade-form" onSubmit={submitTrade}>
          <div className="panel-heading">
            <h2>Mock Trade</h2>
            <Plus size={18} aria-hidden="true" />
          </div>
          <label>
            Ticker
            <select value={tradeTicker} onChange={(event) => updateTradeTicker(event.target.value)} required>
              <option value="">Choose a stock</option>
              {stocks
                .filter((stock) => stock.sector !== "Benchmark")
                .map((stock) => (
                  <option key={stock.ticker} value={stock.ticker}>
                    {stock.ticker} - {stock.name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Action
            <select value={tradeSide} onChange={(event) => setTradeSide(event.target.value as "buy" | "sell")}>
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </label>
          <label>
            Shares
            <input
              value={tradeQuantity}
              onChange={(event) => setTradeQuantity(event.target.value)}
              type="number"
              step="1"
              min="1"
              required
            />
          </label>
          <div className="trade-estimate">
            <span>Estimated price</span>
            <strong>{tradePrice ? money(Number(tradePrice)) : "Latest available"}</strong>
          </div>
          <label>
            Note
            <input value={tradeNote} onChange={(event) => setTradeNote(event.target.value)} maxLength={500} />
          </label>
          <button type="submit" disabled={loading || !tradeTicker}>
            <Plus size={16} /> {tradeSide === "buy" ? "Buy shares" : "Sell shares"}
          </button>
          {tradeStatus && <p className="success">{tradeStatus}</p>}
          <p className="muted">{trades.length} paper trades tracked</p>
        </form>
      </section>
    </main>
  );
}

function Metric({ icon, label, value }: { icon: React.ReactNode; label: string; value: string }): JSX.Element {
  return (
    <div className="metric">
      {icon}
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Score({ value, label }: { value: number; label?: string }): JSX.Element {
  return (
    <span className="score" style={{ "--score": `${value}%` } as React.CSSProperties}>
      {label && <small>{label}</small>}
      <strong>{value}</strong>
    </span>
  );
}

function PerformanceChart({ performance }: { performance: StockPerformance }): JSX.Element {
  const width = 640;
  const height = 180;
  const padding = 24;
  const closes = performance.points.map((point) => point.close);
  const min = Math.min(...closes);
  const max = Math.max(...closes);
  const spread = max - min || 1;
  const xFor = (index: number): number =>
    padding + (index / Math.max(performance.points.length - 1, 1)) * (width - padding * 2);
  const yFor = (close: number): number => {
    const raw = height - padding - ((close - min) / spread) * (height - padding * 2);
    return Math.max(padding, Math.min(height - padding, raw));
  };
  const path = performance.points
    .map((point, index) => `${index === 0 ? "M" : "L"} ${xFor(index)} ${yFor(point.close)}`)
    .join(" ");

  return (
    <div className="chart-wrap">
      <div className="panel-heading compact">
        <h2>{performance.ticker} Performance</h2>
        <span>{performance.markers.length} trade markers</span>
      </div>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${performance.ticker} price chart`}>
        <path d={path} className="price-line" />
        {performance.markers.map((marker, index) => {
          const nearest = nearestPointIndex(performance.points, marker.executed_at);
          return (
            <circle
              key={`${marker.executed_at}-${index}`}
              cx={xFor(nearest)}
              cy={yFor(marker.price)}
              r="5"
              className={marker.side === "buy" ? "buy-marker" : "sell-marker"}
            />
          );
        })}
      </svg>
    </div>
  );
}

function nearestPointIndex(points: { as_of: string }[], target: string): number {
  const targetMs = new Date(target).getTime();
  let nearest = 0;
  let bestDistance = Number.MAX_SAFE_INTEGER;
  points.forEach((point, index) => {
    const distance = Math.abs(new Date(point.as_of).getTime() - targetMs);
    if (distance < bestDistance) {
      nearest = index;
      bestDistance = distance;
    }
  });
  return nearest;
}

function money(value: number): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(value);
}

function dateOnly(value: string): string {
  return new Date(value).toLocaleDateString();
}

createRoot(document.getElementById("root")!).render(<App />);
