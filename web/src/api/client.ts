import type {
  LeagueSettings,
  LeagueResponse,
  NextPickRequest,
  NextPickResponse,
  SimulateRequest,
  SimulateResponse,
} from './types';

const BASE_URL = import.meta.env.VITE_API_URL ?? '';

async function post<TResponse>(path: string, body: unknown): Promise<TResponse> {
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<TResponse>;
}

export function fetchLeague(settings: LeagueSettings): Promise<LeagueResponse> {
  return post<LeagueResponse>('/api/league', settings);
}

export function runSimulation(req: SimulateRequest): Promise<SimulateResponse> {
  return post<SimulateResponse>('/api/simulate', req);
}

export function fetchNextPick(req: NextPickRequest): Promise<NextPickResponse> {
  return post<NextPickResponse>('/api/next-pick', req);
}
