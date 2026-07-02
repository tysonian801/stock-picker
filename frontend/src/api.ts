import type { MockTrade, Portfolio, Recommendation, ScanRun, Stock, StockPerformance } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

export async function login(email: string, password: string): Promise<string> {
  const session = await request<{ csrf_token: string }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  return session.csrf_token;
}

export async function getSession(): Promise<string> {
  const session = await request<{ csrf_token: string }>("/auth/session");
  return session.csrf_token;
}

export function getStocks(): Promise<Stock[]> {
  return request<Stock[]>("/stocks");
}

export function getRecommendations(): Promise<Recommendation[]> {
  return request<Recommendation[]>("/recommendations");
}

export function runScan(csrfToken: string): Promise<ScanRun> {
  return request<ScanRun>("/scan-runs", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
  });
}

export function getScans(): Promise<ScanRun[]> {
  return request<ScanRun[]>("/scan-runs");
}

export function getPortfolio(): Promise<Portfolio> {
  return request<Portfolio>("/portfolio");
}

export function getStockPerformance(ticker: string): Promise<StockPerformance> {
  return request<StockPerformance>(`/stocks/${encodeURIComponent(ticker)}/performance`);
}

export function getTrades(): Promise<MockTrade[]> {
  return request<MockTrade[]>("/mock-trades");
}

export function addTrade(
  csrfToken: string,
  payload: { ticker: string; side: "buy" | "sell"; quantity: number; price?: number; note?: string },
): Promise<MockTrade> {
  return request<MockTrade>("/mock-trades", {
    method: "POST",
    headers: { "X-CSRF-Token": csrfToken },
    body: JSON.stringify(payload),
  });
}
