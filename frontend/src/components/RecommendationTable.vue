<template>
  <v-data-table
    class="compact-table"
    density="compact"
    :headers="headers"
    :items="rows"
    :items-per-page="-1"
    hide-default-footer
  >
    <template #item.title="{ item }">
      <strong>{{ item.title }}</strong>
      <div class="text-caption text-medium-emphasis">{{ item.players }}</div>
    </template>
    <template #item.total_hours="{ item }">{{ item.total_hours }} h</template>
    <template #item.median_hours="{ item }">{{ item.median_hours }} h</template>
    <template #item.average_hours="{ item }">{{ item.average_hours }} h</template>
    <template #item.features="{ item }">
      <v-chip v-if="item.lan" size="small" color="primary" class="mr-1">LAN</v-chip>
      <v-chip v-if="item.coop" size="small" color="secondary" class="mr-1">Coop</v-chip>
      <v-chip v-if="item.split" size="small" color="accent" class="mr-1">Split</v-chip>
      <span v-if="!item.features" class="text-medium-emphasis">-</span>
    </template>
  </v-data-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { Game, Recommendation } from '../types'

const props = defineProps<{ items: Recommendation[] }>()

const headers = [
  { title: 'Spiel', key: 'title' },
  { title: 'Besitzer', key: 'owner_count' },
  { title: 'Gesamt', key: 'total_hours' },
  { title: 'Median', key: 'median_hours' },
  { title: 'Durchschnitt', key: 'average_hours' },
  { title: 'Features', key: 'features' },
  { title: 'Plattformen', key: 'platforms' }
]

const rows = computed(() =>
  props.items.map((rec) => ({
    id: rec.game.id,
    title: rec.game.title,
    players: playerLabel(rec.game),
    owner_count: rec.owner_count,
    total_hours: hours(rec.total_playtime_minutes),
    median_hours: hours(rec.median_playtime_minutes),
    average_hours: hours(rec.average_playtime_minutes),
    lan: rec.game.lan,
    coop: rec.game.local_coop || rec.game.online_coop,
    split: rec.game.split_screen,
    features: featureText(rec.game),
    platforms: rec.platforms.join(', ')
  }))
)

const hours = (minutes: number) => Math.round(minutes / 60)

function featureText(game: Game) {
  return [
    game.lan ? 'LAN' : '',
    game.local_coop || game.online_coop ? 'Coop' : '',
    game.split_screen ? 'Split' : ''
  ]
    .filter(Boolean)
    .join(', ')
}

function playerLabel(game: Game) {
  if (game.min_players === 1 && game.max_players === 1 && game.multiplayer) {
    return 'MP'
  }
  if (game.min_players === 1 && game.max_players === 1) {
    return 'Solo'
  }
  return `${game.min_players}-${game.max_players} Spieler`
}
</script>
