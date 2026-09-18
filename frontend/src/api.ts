import { ref } from 'vue'
import type { Account, AnalyticsConfiguration, AnalyticsParticipantDetail, AnalyticsPeriod, AnalyticsSummary, Game, GameOption, GameOwner, GamePage, ManualOwnership, ManualOwnershipGameOption, Ownership, Participant, PersonalGamePage, Platform, PrivacyInfo, ProviderAuthStatus, ProviderLoginStart, RecentAcquisition, Recommendation, SteamConnection, SteamLoginStart, SteamProfile, SyncRun } from './types'

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
  adminUnlock: (password: string) =>
    request<{ unlocked: boolean }>('/admin/unlock', {
      method: 'POST',
      body: JSON.stringify({ password })
    }),
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
  gamesPage: (params: {
    page: number
    perPage: number
    search?: string
    genres?: string[]
    features?: string[]
    includePureSingleplayer?: boolean
    includeNonGames?: boolean
    sortBy?: string
    sortDesc?: boolean
  }) => {
    const query = new URLSearchParams({
      page: String(params.page),
      per_page: String(params.perPage),
      include_pure_singleplayer: String(Boolean(params.includePureSingleplayer)),
      include_non_games: String(Boolean(params.includeNonGames)),
      sort_by: params.sortBy || 'title',
      sort_desc: String(Boolean(params.sortDesc))
    })
    if (params.search?.trim()) query.set('search', params.search.trim())
    params.genres?.forEach((genre) => query.append('genres', genre))
    params.features?.forEach((feature) => query.append('features', feature))
    return request<GamePage>(`/games/page?${query}`)
  },
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
  recentAcquisitions: (days = 90, limit = 100) =>
    request<RecentAcquisition[]>(`/ownerships/recent-acquisitions?days=${days}&limit=${limit}`),
  personalGames: (params: {
    participantId: number
    page: number
    perPage: number
    search?: string
    platforms?: Platform[]
    genres?: string[]
    modes?: string[]
    playerCount?: number | null
    sortBy?: string
    sortDesc?: boolean
  }) => {
    const query = new URLSearchParams({
      page: String(params.page),
      per_page: String(params.perPage),
      sort_by: params.sortBy || 'title',
      sort_desc: String(Boolean(params.sortDesc))
    })
    if (params.search?.trim()) query.set('search', params.search.trim())
    params.platforms?.forEach((platform) => query.append('platforms', platform))
    params.genres?.forEach((genre) => query.append('genres', genre))
    params.modes?.forEach((mode) => query.append('modes', mode))
    if (params.playerCount) query.set('player_count', String(params.playerCount))
    return request<PersonalGamePage>(`/ownerships/participants/${params.participantId}/games?${query}`)
  },
  manualOwnershipOptions: (participantId: number, search: string, limit = 25) => {
    const params = new URLSearchParams({
      participant_id: String(participantId),
      search,
      limit: String(limit)
    })
    return request<ManualOwnershipGameOption[]>(`/ownerships/manual/options?${params}`)
  },
  createManualOwnership: (payload: { participant_id: number; game_id: number; platform: Platform }) =>
    request<ManualOwnership>('/ownerships/manual', {
      method: 'POST',
      body: JSON.stringify(payload)
    }),
  deleteManualOwnership: (id: number) =>
    request<void>(`/ownerships/manual/${id}`, { method: 'DELETE' }),
  recommendations: (kind: 'popular' | 'lan' | 'present' | 'new', limit?: number) =>
    request<Recommendation[]>(`/recommendations/${kind}${limit ? `?limit=${limit}` : ''}`),
  newForGroup: (players: number[]) => request<Recommendation[]>(`/recommendations/new${players.length ? `?${players.map((id) => `players=${id}`).join('&')}` : ''}`),
  common: (players: number[], minimumCoverage = 75, freeGamesAsOwned = true) => {
    const params = new URLSearchParams()
    players.forEach((id) => params.append('players', String(id)))
    params.set('minimum_coverage', String(minimumCoverage))
    params.set('free_games_as_owned', String(freeGamesAsOwned))
    return request<Recommendation[]>(`/recommendations/common?${params}`)
  },
  coop: (players: number[]) => request<Recommendation[]>(`/recommendations/coop?${players.map((id) => `players=${id}`).join('&')}`),
  lanForGroup: (players: number[]) => request<Recommendation[]>(`/recommendations/lan?${players.map((id) => `players=${id}`).join('&')}`),
  syncAccount: (id: number) => request<SyncRun>(`/sync/accounts/${id}`, { method: 'POST' }),
  syncMetadata: () => request<SyncRun>('/sync/metadata', { method: 'POST' }),
  repairMetadata: () => request<SyncRun>('/sync/metadata/repair', { method: 'POST' }),
  syncGameMetadata: (gameId: number) =>
    request<SyncRun>(`/sync/games/${gameId}/metadata`, { method: 'POST' }),
  syncRuns: () => request<SyncRun[]>('/sync/runs'),
  syncRun: (runId: number) => request<SyncRun>(`/sync/runs/${runId}`),
  importPlaynite: (participantId: number, file: File, onUploadProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('participant_id', String(participantId))
    form.append('file', file)
    pendingRequests.value += 1
    return new Promise<SyncRun>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      let completed = false
      const finish = () => {
        if (completed) return
        completed = true
        pendingRequests.value -= 1
      }
      xhr.open('POST', `${base}/imports/playnite`)
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          onUploadProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      }
      xhr.onload = () => {
        finish()
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(xhr.responseText))
          return
        }
        try {
          resolve(JSON.parse(xhr.responseText) as SyncRun)
        } catch {
          reject(new Error('Der Server hat keine gültige Importantwort geliefert.'))
        }
      }
      xhr.onerror = () => {
        finish()
        reject(new Error('Der Upload wurde durch ein Netzwerkproblem unterbrochen.'))
      }
      xhr.onabort = () => {
        finish()
        reject(new Error('Der Upload wurde abgebrochen.'))
      }
      xhr.send(form)
    })
  },
  playniteImportStatus: (runId: number) => request<SyncRun>(`/imports/playnite/${runId}`),
  importGogGalaxy: (participantId: number, file: File, onUploadProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('participant_id', String(participantId))
    form.append('file', file)
    pendingRequests.value += 1
    return new Promise<SyncRun>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      let completed = false
      const finish = () => {
        if (completed) return
        completed = true
        pendingRequests.value -= 1
      }
      xhr.open('POST', `${base}/imports/gog-galaxy`)
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && event.total > 0) {
          onUploadProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)))
        }
      }
      xhr.onload = () => {
        finish()
        if (xhr.status < 200 || xhr.status >= 300) {
          reject(new Error(xhr.responseText))
          return
        }
        try {
          resolve(JSON.parse(xhr.responseText) as SyncRun)
        } catch {
          reject(new Error('Der Server hat keine gueltige Importantwort geliefert.'))
        }
      }
      xhr.onerror = () => {
        finish()
        reject(new Error('Der Upload wurde durch ein Netzwerkproblem unterbrochen.'))
      }
      xhr.onabort = () => {
        finish()
        reject(new Error('Der Upload wurde abgebrochen.'))
      }
      xhr.send(form)
    })
  },
  gogGalaxyImportStatus: (runId: number) => request<SyncRun>(`/imports/gog-galaxy/${runId}`),
  providerAuthStatus: () => request<ProviderAuthStatus[]>('/provider-auth/status'),
  resolveSteamProfile: (profile: string) =>
    request<SteamProfile>('/provider-auth/steam/resolve', {
      method: 'POST',
      body: JSON.stringify({ profile })
    }),
  connectSteam: (participantId: number, profile: string) =>
    request<SteamConnection>('/provider-auth/steam/connect', {
      method: 'POST',
      body: JSON.stringify({ participant_id: participantId, profile })
    }),
  startSteamLogin: (participantId: number, origin: string) =>
    request<SteamLoginStart>('/provider-auth/steam/start', {
      method: 'POST',
      body: JSON.stringify({ participant_id: participantId, origin })
    }),
  startProviderLogin: (accountId: number) => request<ProviderLoginStart>(`/provider-auth/accounts/${accountId}/start`),
  pollProviderLogin: (accountId: number) =>
    request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/poll`, { method: 'POST' }),
  completeProviderLogin: (accountId: number, payload: { code?: string; email?: string; password?: string; two_factor_code?: string }) =>
    request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/complete`, { method: 'POST', body: JSON.stringify(payload) }),
  logoutProvider: (accountId: number) => request<ProviderAuthStatus>(`/provider-auth/accounts/${accountId}/logout`, { method: 'POST' }),
  usageConfiguration: () =>
    request<AnalyticsConfiguration>('/app-log/configuration'),
  updateUsageConfiguration: (payload: AnalyticsConfiguration) =>
    request<AnalyticsConfiguration>('/app-log/configuration', {
      method: 'PUT',
      body: JSON.stringify(payload)
    }),
  usageSummary: (period: AnalyticsPeriod, dateFrom: string, dateTo: string) => {
    const params = new URLSearchParams({ period })
    if (period === 'custom') {
      params.set('date_from', dateFrom)
      params.set('date_to', dateTo)
    }
    return request<AnalyticsSummary>(`/app-log/summary?${params}`)
  },
  usageParticipant: (participantId: number, period: AnalyticsPeriod, dateFrom: string, dateTo: string) => {
    const params = new URLSearchParams({ period })
    if (period === 'custom') {
      params.set('date_from', dateFrom)
      params.set('date_to', dateTo)
    }
    return request<AnalyticsParticipantDetail>(`/app-log/participants/${participantId}?${params}`)
  },
  deleteParticipantUsage: (participantId: number) =>
    request<void>(`/app-log/participants/${participantId}/entries`, { method: 'DELETE' }),
  privacyInfo: () => request<PrivacyInfo>('/privacy')
}
