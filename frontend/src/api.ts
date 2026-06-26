import type { Account, Game, GameOwner, MetadataSyncResult, Ownership, Participant, ProviderAuthStatus, ProviderLoginStart, Recommendation, SyncRun } from './types'

const base = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options
  })
  if (!response.ok) {
    throw new Error(await response.text())
  }
  if (response.status === 204) {
    return undefined as T
  }
  return response.json() as Promise<T>
}

export const api = {
  participants: () => request<Participant[]>('/participants'),
  createParticipant: (payload: Partial<Participant>) =>
    request<Participant>('/participants', { method: 'POST', body: JSON.stringify(payload) }),
  updateParticipant: (id: number, payload: Partial<Participant>) =>
    request<Participant>(`/participants/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteParticipant: (id: number) => request<void>(`/participants/${id}`, { method: 'DELETE' }),
  accounts: () => request<Account[]>('/accounts'),
  createAccount: (payload: Partial<Account>) => request<Account>('/accounts', { method: 'POST', body: JSON.stringify(payload) }),
  deleteAccount: (id: number) => request<void>(`/accounts/${id}`, { method: 'DELETE' }),
  games: (search = '') => request<Game[]>(`/games${search ? `?search=${encodeURIComponent(search)}` : ''}`),
  createGame: (payload: Partial<Game>) => request<Game>('/games', { method: 'POST', body: JSON.stringify(payload) }),
  deleteGame: (id: number) => request<void>(`/games/${id}`, { method: 'DELETE' }),
  gameOwners: (gameId: number, presentOnly = true) => request<GameOwner[]>(`/games/${gameId}/owners?present_only=${presentOnly}`),
  ownerships: () => request<Ownership[]>('/ownerships'),
  createOwnership: (payload: Partial<Ownership>) =>
    request<Ownership>('/ownerships', { method: 'POST', body: JSON.stringify(payload) }),
  deleteOwnership: (id: number) => request<void>(`/ownerships/${id}`, { method: 'DELETE' }),
  recommendations: (kind: 'popular' | 'lan' | 'present') => request<Recommendation[]>(`/recommendations/${kind}`),
  common: (players: number[]) => request<Recommendation[]>(`/recommendations/common?${players.map((id) => `players=${id}`).join('&')}`),
  coop: (players: number[]) => request<Recommendation[]>(`/recommendations/coop?${players.map((id) => `players=${id}`).join('&')}`),
  groupSize: (size: number) => request<Recommendation[]>(`/recommendations/group-size/${size}`),
  syncAccount: (id: number) => request<SyncRun>(`/sync/accounts/${id}`, { method: 'POST' }),
  syncMetadata: () => request<MetadataSyncResult>('/sync/metadata', { method: 'POST' }),
  syncRuns: () => request<SyncRun[]>('/sync/runs'),
  providerAuthStatus: () => request<ProviderAuthStatus[]>('/provider-auth/status'),
  startProviderLogin: (accountId: number) => request<ProviderLoginStart>(`/provider-auth/accounts/${accountId}/start`),
  completeProviderLogin: (accountId: number, payload: { code?: string; email?: string; password?: string; two_factor_code?: string; access_token?: string; cookie?: string; pid?: string }) =>
    request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/complete`, { method: 'POST', body: JSON.stringify(payload) }),
  logoutProvider: (accountId: number) => request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/logout`, { method: 'POST' })
}
