import type { Game } from './types'

export interface GameFilterState {
  search: string
  genres: string[]
  features: string[]
  includePureSingleplayer: boolean
}

export function createGameFilterState(): GameFilterState {
  return {
    search: '',
    genres: [],
    features: [],
    includePureSingleplayer: false
  }
}

export function isPureSingleplayer(game: Game) {
  return Boolean(
    game.singleplayer &&
      !game.multiplayer &&
      !game.lan &&
      !game.local_coop &&
      !game.online_coop &&
      !game.campaign_coop &&
      !game.hotseat &&
      !game.split_screen &&
      !game.shared_screen &&
      !game.versus
  )
}

export function matchesGameFilters(game: Game, filters: GameFilterState) {
  if (!filters.includePureSingleplayer && isPureSingleplayer(game)) return false

  const search = filters.search.trim().toLocaleLowerCase()
  if (search && !game.title.toLocaleLowerCase().includes(search)) return false

  if (filters.genres.length) {
    const genres = new Set(game.genres.map((genre) => genre.toLocaleLowerCase()))
    if (!filters.genres.some((genre) => genres.has(genre.toLocaleLowerCase()))) return false
  }

  return filters.features.every((feature) => featureMatches(game, feature))
}

function featureMatches(game: Game, feature: string) {
  const predicates: Record<string, boolean> = {
    singleplayer: game.singleplayer,
    multiplayer: game.multiplayer,
    coop: game.local_coop || game.online_coop || game.campaign_coop,
    local_coop: game.local_coop,
    online_coop: game.online_coop,
    versus: game.versus,
    lan: game.lan,
    split_screen: game.split_screen || game.shared_screen,
    hotseat: game.hotseat
  }
  return predicates[feature] ?? true
}
