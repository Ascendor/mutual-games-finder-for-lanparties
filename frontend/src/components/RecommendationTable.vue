<template>
  <div>
    <GameFilterBar v-model="filters" :games="games" />
    <v-data-table
      class="compact-table"
      density="compact"
      :headers="headers"
      :items="rows"
      v-model:sort-by="sortBy"
      :loading="loading"
      loading-text="Spiele werden geladen..."
      :items-per-page="-1"
      hide-default-footer
      no-data-text="Keine Spiele entsprechen den Filtern."
    >
    <template #item.title="{ item }">
      <strong>{{ item.title }}</strong>
      <div class="text-caption text-medium-emphasis">{{ item.players }}</div>
    </template>
    <template #item.owner_count="{ item }">{{ item.owner_display }}</template>
    <template #item.availability_rank="{ item }">
      <strong>{{ item.availability_display }}</strong>
      <div v-if="item.library_display" class="text-caption text-medium-emphasis">
        {{ item.library_display }}
      </div>
      <div v-if="item.unknown_display" class="text-caption text-medium-emphasis">
        {{ item.unknown_display }}
      </div>
    </template>
    <template #item.total_minutes="{ item }">{{ item.total_hours }} h</template>
    <template #item.median_minutes="{ item }">{{ item.median_hours }} h</template>
    <template #item.average_minutes="{ item }">{{ item.average_hours }} h</template>
    <template #item.features="{ item }">
      <v-chip v-if="item.lan" size="small" color="primary" class="mr-1">LAN</v-chip>
      <v-chip v-if="item.coop" size="small" color="secondary" class="mr-1">Coop</v-chip>
      <v-chip v-if="item.split" size="small" color="accent" class="mr-1">Split</v-chip>
      <v-chip v-if="item.versus" size="small" variant="tonal" class="mr-1">VS</v-chip>
      <v-chip v-if="item.is_free" size="small" color="success" variant="tonal" class="mr-1">Free</v-chip>
      <span v-if="!item.features" class="text-medium-emphasis">-</span>
    </template>
    </v-data-table>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import GameFilterBar from './GameFilterBar.vue'
import { createGameFilterState, matchesGameFilters } from '../gameFilters'
import type { Game, Recommendation } from '../types'

const props = withDefaults(defineProps<{
  items: Recommendation[]
  loading?: boolean
  limit?: number
  showAvailability?: boolean
  freeGamesAsOwned?: boolean
  preserveOrder?: boolean
  defaultSort?: 'owner' | 'availability' | 'new' | 'none'
}>(), {
  loading: false,
  limit: 0,
  showAvailability: false,
  freeGamesAsOwned: true,
  preserveOrder: false,
  defaultSort: 'owner'
})
const filters = ref(createGameFilterState())
const sortBy = ref<{ key: string; order: 'asc' | 'desc' }[]>(initialSortBy())
const games = computed(() => props.items.map((item) => item.game))
const filteredItems = computed(() => {
  const filtered = props.items.filter((item) => matchesGameFilters(item.game, filters.value))
  return props.limit > 0 ? filtered.slice(0, props.limit) : filtered
})

const headers = computed(() => [
  { title: 'Spiel', key: 'title' },
  props.showAvailability
    ? { title: 'Verfügbarkeit', key: 'availability_rank' }
    : { title: 'Besitzer', key: 'owner_count' },
  { title: 'Gesamt', key: 'total_minutes' },
  { title: 'Median', key: 'median_minutes' },
  { title: 'Durchschnitt', key: 'average_minutes' },
  { title: 'Features', key: 'features' },
  { title: 'Plattformen', key: 'platforms' }
])

const rows = computed(() =>
  filteredItems.value.map((rec) => {
    const fullyOwned = rec.owner_count === rec.selected_player_count
    const freeForGroup = rec.game.is_free && props.freeGamesAsOwned && !fullyOwned
    const availabilityGroup = fullyOwned ? 3 : freeForGroup ? 2 : 1
    return {
      id: rec.game.id,
      title: rec.game.title,
      players: playerLabel(rec.game),
      owner_count: rec.owner_count,
      owner_display: rec.game.is_free ? `Alle (${rec.owner_count} importiert)` : String(rec.owner_count),
      coverage_percent: rec.coverage_percent,
      availability_rank:
        availabilityGroup * 1_000_000_000 +
        rec.owner_count * 1_000_000 +
        rec.coverage_percent * 1000,
      availability_display: fullyOwned
        ? `${rec.owner_count} von ${rec.selected_player_count} in der Bibliothek`
        : freeForGroup
          ? 'Für alle kostenlos'
          : `${rec.owner_count} von ${rec.selected_player_count} in der Bibliothek`,
      library_display: freeForGroup
        ? `${rec.owner_count} von ${rec.selected_player_count} haben es in der Bibliothek`
        : '',
      unknown_display: unknownPlayerLabel(rec),
      total_minutes: rec.total_playtime_minutes,
      median_minutes: rec.median_playtime_minutes,
      average_minutes: rec.average_playtime_minutes,
      total_hours: hours(rec.total_playtime_minutes),
      median_hours: hours(rec.median_playtime_minutes),
      average_hours: hours(rec.average_playtime_minutes),
      lan: rec.game.lan,
      coop: rec.game.local_coop || rec.game.online_coop,
      split: rec.game.split_screen,
      versus: rec.game.versus,
      is_free: rec.game.is_free,
      features: featureText(rec.game),
      platforms: rec.platforms.map(platformLabel).join(', ')
    }
  })
)

function initialSortBy() {
  if (props.preserveOrder || props.defaultSort === 'none') return []
  if (props.defaultSort === 'new') {
    return [
      { key: 'median_minutes', order: 'asc' as const },
      { key: 'average_minutes', order: 'asc' as const },
      { key: 'owner_count', order: 'desc' as const },
      { key: 'coverage_percent', order: 'desc' as const }
    ]
  }
  if (props.defaultSort === 'availability' || props.showAvailability) {
    return [{ key: 'availability_rank', order: 'desc' as const }]
  }
  return [{ key: 'owner_count', order: 'desc' as const }]
}

const hours = (minutes: number) => Math.round(minutes / 60)

function platformLabel(platform: string) {
  return platform === 'humble_key' ? 'Humble Key' : platform
}

function unknownPlayerLabel(rec: Recommendation) {
  const names = rec.unknown_players.map((participant) => participant.nickname)
  if (!names.length) return ''
  return `Bei ${names.join(', ')} unbekannt`
}

function featureText(game: Game) {
  return [
    game.lan ? 'LAN' : '',
    game.local_coop || game.online_coop ? 'Coop' : '',
    game.split_screen ? 'Split' : '',
    game.is_free ? 'Free' : ''
  ]
    .filter(Boolean)
    .join(', ')
}

function playerLabel(game: Game) {
  if (!game.player_count_known || (game.multiplayer && game.max_players <= 1)) {
    return game.multiplayer ? 'MP, Spielerzahl unbekannt' : 'Spielerzahl unbekannt'
  }
  if (game.min_players === 1 && game.max_players === 1) {
    return 'Solo'
  }
  return `${game.min_players}-${game.max_players} Spieler`
}
</script>
