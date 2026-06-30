export type Platform = string

export interface Participant {
  id: number
  nickname: string
  real_name?: string | null
  present: boolean
  notes: string
}

export interface Account {
  id: number
  participant_id: number
  platform: Platform
  account_id: string
  display_name: string
  last_successful_sync?: string | null
  last_error?: string | null
}

export interface Game {
  id: number
  title: string
  normalized_title: string
  description: string
  cover_url?: string | null
  release_date?: string | null
  genres: string[]
  singleplayer: boolean
  multiplayer: boolean
  lan: boolean
  local_coop: boolean
  online_coop: boolean
  hotseat: boolean
  split_screen: boolean
  shared_screen: boolean
  campaign_coop: boolean
  drop_in: boolean
  versus: boolean
  min_players: number
  max_players: number
  offline_max_players?: number | null
  online_max_players?: number | null
  offline_coop_max_players?: number | null
  online_coop_max_players?: number | null
  multiplayer_metadata_known: boolean
  player_count_known: boolean
  metadata_source?: string | null
  metadata_external_id?: string | null
  metadata_sources: Record<string, string>
  metadata_updated_at?: string | null
  is_free: boolean
}

export interface GameOption {
  id: number
  title: string
}

export interface Ownership {
  id: number
  participant_id: number
  account_id: number
  game_id: number
  platform: Platform
  playtime_minutes: number
  owned_since?: string | null
  last_seen: string
}


export interface GameOwner {
  participant: Participant
  platforms: Platform[]
  account_names: string[]
  total_playtime_minutes: number
  last_seen?: string | null
}
export interface Recommendation {
  game: Game
  owner_count: number
  available_player_count: number
  known_player_count: number
  selected_player_count: number
  coverage_percent: number
  total_playtime_minutes: number
  average_playtime_minutes: number
  median_playtime_minutes: number
  score: number
  platforms: Platform[]
  owners: Participant[]
  unknown_players: Participant[]
}


export interface PlayniteImportResult {
  imported_games: number
  skipped_games: number
  created_accounts: number
  updated_ownerships: number
  platforms: string[]
  message: string
}

export interface MetadataSyncResult {
  scanned_games: number
  updated_games: number
  failed_games: number
  message: string
}
export interface SyncRun {
  id: number
  account_id?: number | null
  kind: 'account' | 'metadata' | string
  started_at: string
  finished_at?: string | null
  success: boolean
  message: string
  imported_games: number
}


export interface ProviderAuthStatus {
  account_id: number
  participant_id: number
  platform: Platform
  authenticated: boolean
  needs_2fa?: boolean
  pending?: boolean
  interval?: number
  message: string
}

export interface ProviderLoginStart {
  account_id: number
  participant_id: number
  platform: Platform
  login_url: string
  code_label: string
  message: string
  verification_uri?: string
  user_code?: string
  expires_in?: number
  interval?: number
}





