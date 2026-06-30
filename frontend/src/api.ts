import { ref } from 'vue'
import type { Account, Game, GameOption, GameOwner, Ownership, Participant, PlayniteImportResult, ProviderAuthStatus, ProviderLoginStart, Recommendation, SyncRun } from './types'

const base = '/api'
export const pendingRequests = ref(0)

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  pendingRequests.value += 1
  try {
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
  } finally {
    pendingRequests.value -= 1
  }
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
  gameOptions: (search = '', limit?: number) => {
    const params = new URLSearchParams()
    if (search) params.set('search', search)
    if (limit) params.set('limit', String(limit))
    const query = params.toString()
    return request<GameOption[]>(`/games/options${query ? `?${query}` : ''}`)
  },
  createGame: (payload: Partial<Game>) => request<Game>('/games', { method: 'POST', body: JSON.stringify(payload) }),
  deleteGame: (id: number) => request<void>(`/games/${id}`, { method: 'DELETE' }),
  gameOwners: (gameId: number, presentOnly = true) => request<GameOwner[]>(`/games/${gameId}/owners?present_only=${presentOnly}`),
  ownerships: () => request<Ownership[]>('/ownerships'),
  createOwnership: (payload: Partial<Ownership>) =>
    request<Ownership>('/ownerships', { method: 'POST', body: JSON.stringify(payload) }),
  deleteOwnership: (id: number) => request<void>(`/ownerships/${id}`, { method: 'DELETE' }),
  recommendations: (kind: 'popular' | 'lan' | 'present' | 'new', limit?: number) =>
    request<Recommendation[]>(`/recommendations/${kind}${limit ? `?limit=${limit}` : ''}`),
  newForGroup: (players: number[]) => request<Recommendation[]>(`/recommendations/new${players.length ? `?${players.map((id) => `players=${id}`).join('&')}` : ''}`),
  common: (players: number[], minimumCoverage = 75) => {
    const params = new URLSearchParams()
    players.forEach((id) => params.append('players', String(id)))
    params.set('minimum_coverage', String(minimumCoverage))
    return request<Recommendation[]>(`/recommendations/common?${params}`)
  },
  coop: (players: number[]) => request<Recommendation[]>(`/recommendations/coop?${players.map((id) => `players=${id}`).join('&')}`),
  lanForGroup: (players: number[]) => request<Recommendation[]>(`/recommendations/lan?${players.map((id) => `players=${id}`).join('&')}`),
  syncAccount: (id: number) => request<SyncRun>(`/sync/accounts/${id}`, { method: 'POST' }),
  syncMetadata: () => request<SyncRun>('/sync/metadata', { method: 'POST' }),
  repairMetadata: () => request<SyncRun>('/sync/metadata/repair', { method: 'POST' }),
  syncRuns: () => request<SyncRun[]>('/sync/runs'),
  importPlaynite: async (participantId: number, file: File) => {
    const form = new FormData()
    form.append('participant_id', String(participantId))
    form.append('file', file)
    pendingRequests.value += 1
    try {
      const response = await fetch(`${base}/imports/playnite`, { method: 'POST', body: form })
      if (!response.ok) {
        throw new Error(await response.text())
      }
      return response.json() as Promise<PlayniteImportResult>
    } finally {
      pendingRequests.value -= 1
    }
  },
  providerAuthStatus: () => request<ProviderAuthStatus[]>('/provider-auth/status'),
  startProviderLogin: (accountId: number) => request<ProviderLoginStart>(`/provider-auth/accounts/${accountId}/start`),
  pollProviderLogin: (accountId: number) =>
    request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/poll`, { method: 'POST' }),
  completeProviderLogin: (accountId: number, payload: { code?: string; email?: string; password?: string; two_factor_code?: string }) =>
    request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/complete`, { method: 'POST', body: JSON.stringify(payload) }),
  logoutProvider: (accountId: number) => request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/logout`, { method: 'POST' })
}
