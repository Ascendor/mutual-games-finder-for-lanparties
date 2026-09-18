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
  is_game: boolean
  non_game_reason?: string | null
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

export interface GameListItem extends Game {
  owner_count: number
}

export interface GamePage {
  items: GameListItem[]
  total: number
  page: number
  per_page: number
  genres: string[]
}

export interface GameOption {
  id: number
  title: string
}

export interface ManualOwnershipConfirmation {
  id: number
  platform: Platform
}

export interface ManualOwnershipGameOption {
  id: number
  title: string
  release_date?: string | null
  owner_count: number
  platforms: Platform[]
  owned: boolean
  manual_confirmations: ManualOwnershipConfirmation[]
}

export interface ManualOwnership {
  id: number
  participant_id: number
  game_id: number
  platform: Platform
  created_at: string
}

export interface Ownership {
  id: number
  participant_id: number
  account_id?: number | null
  game_id: number
  platform: Platform
  playtime_minutes: number
  owned_since?: string | null
  last_seen: string
}

export interface PersonalGamePlatform {
  platform: Platform
  playtime_minutes: number
  account_id?: string | null
  account_display_name?: string | null
}

export interface PersonalGame {
  game: Game
  platforms: PersonalGamePlatform[]
  total_playtime_minutes: number
}

export interface PersonalGamePage {
  items: PersonalGame[]
  total: number
  page: number
  per_page: number
  platforms: Platform[]
  genres: string[]
}

export interface RecentAcquisition {
  participant: Participant
  game: Game
  owned_since: string
  platforms: Platform[]
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


export interface MetadataSyncResult {
  scanned_games: number
  updated_games: number
  failed_games: number
  message: string
}
export interface SyncRun {
  id: number
  account_id?: number | null
  participant_id?: number | null
  kind: 'account' | 'metadata' | string
  started_at: string
  finished_at?: string | null
  success: boolean
  message: string
  imported_games: number
  stage: string
  progress_current: number
  progress_total: number
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
  capture_url?: string
  code_label: string
  message: string
  verification_uri?: string
  user_code?: string
  expires_in?: number
  interval?: number
}

export interface SteamProfile {
  steam_id: string
  display_name: string
  profile_url: string
  avatar_url?: string | null
  library_accessible: boolean
  game_count?: number | null
}

export interface SteamConnection extends SteamProfile {
  account: Account
}

export interface SteamLoginStart {
  login_url: string
  state: string
  expires_in: number
}

export type UsageEventType =
  | 'page_view'
  | 'find_players_search'
  | 'group_games_search'

export type AnalyticsPeriod = 'custom' | 'before_party' | 'party' | 'all'

export interface AnalyticsConfiguration {
  party_start_at?: string | null
  party_end_at?: string | null
}

export interface UsageEvent {
  id: number
  participant_id?: number | null
  participant_name: string
  event_type: UsageEventType
  occurred_at: string
  details: Record<string, unknown>
}

export interface AnalyticsDaily {
  date: string
  total_events: number
  page_views: number
  find_players_searches: number
  group_games_searches: number
}

export interface AnalyticsCount {
  key: UsageEventType
  count: number
}

export interface AnalyticsTopGame {
  game_id?: number | null
  title: string
  searches: number
  unique_users: number
}

export interface AnalyticsSelectedPlayer {
  participant_id?: number | null
  nickname: string
  selections: number
  unique_searchers: number
}

export interface AnalyticsParticipant {
  participant_id: number
  nickname: string
  total_events: number
  page_views: number
  find_players_searches: number
  group_games_searches: number
  last_active_at: string
}

export interface AnalyticsSummary {
  period: AnalyticsPeriod
  date_from: string
  date_to: string
  total_events: number
  active_users: number
  page_views: number
  find_players_searches: number
  group_games_searches: number
  daily: AnalyticsDaily[]
  event_counts: AnalyticsCount[]
  top_games: AnalyticsTopGame[]
  selected_players: AnalyticsSelectedPlayer[]
  participants: AnalyticsParticipant[]
}

export interface AnalyticsParticipantDetail {
  participant_id: number
  nickname: string
  date_from: string
  date_to: string
  total_events: number
  event_counts: AnalyticsCount[]
  daily: AnalyticsDaily[]
  top_games: AnalyticsTopGame[]
  recent_events: UsageEvent[]
}

export interface PrivacyInfo {
  controller_name: string
  controller_contact: string
  hosting_provider: string
  analytics_retention_days: number
  access_log_retention_days: number
  backup_retention_days: number
  supervisory_authority: string
  supervisory_authority_url: string
}
