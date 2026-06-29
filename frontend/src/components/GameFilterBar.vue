<template>
  <div class="game-filters mb-3">
    <div class="d-flex align-center ga-2 flex-wrap">
      <v-btn
        size="small"
        variant="tonal"
        prepend-icon="mdi-filter-variant"
        :append-icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'"
        @click="expanded = !expanded"
      >
        Filter
      </v-btn>
      <v-chip v-if="!model.includePureSingleplayer" size="small" closable @click:close="model.includePureSingleplayer = true">
        Reine Singleplayer ausgeblendet
      </v-chip>
      <v-chip v-if="activeFilterCount" size="small" color="primary" variant="tonal">
        {{ activeFilterCount }} aktiv
      </v-chip>
      <v-btn v-if="activeFilterCount" size="small" variant="text" prepend-icon="mdi-filter-off-outline" @click="reset">
        Zurücksetzen
      </v-btn>
    </div>

      <div v-if="expanded" class="filter-grid mt-3">
        <v-text-field
          v-model="model.search"
          label="Spiel suchen"
          prepend-inner-icon="mdi-magnify"
          density="compact"
          clearable
          hide-details
        />
        <v-autocomplete
          v-model="model.genres"
          :items="availableGenres"
          label="Genres"
          prepend-inner-icon="mdi-tag-multiple-outline"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
        />
        <v-select
          v-model="model.features"
          :items="featureOptions"
          item-title="title"
          item-value="value"
          label="Spielmodi und Features"
          prepend-inner-icon="mdi-controller-classic-outline"
          density="compact"
          multiple
          chips
          closable-chips
          clearable
          hide-details
        />
        <v-switch
          v-model="model.includePureSingleplayer"
          label="Reine Singleplayer anzeigen"
          color="primary"
          density="compact"
          hide-details
        />
      </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Game } from '../types'
import { createGameFilterState, type GameFilterState } from '../gameFilters'
import { isPlausibleGenre } from '../genreUtils'

const props = defineProps<{ games: Game[] }>()
const model = defineModel<GameFilterState>({ required: true })
const expanded = ref(false)

const featureOptions = [
  { title: 'Singleplayer', value: 'singleplayer' },
  { title: 'Multiplayer', value: 'multiplayer' },
  { title: 'Coop', value: 'coop' },
  { title: 'Local Coop', value: 'local_coop' },
  { title: 'Online Coop', value: 'online_coop' },
  { title: 'PvP / Versus', value: 'versus' },
  { title: 'LAN', value: 'lan' },
  { title: 'Split / Shared Screen', value: 'split_screen' },
  { title: 'Hotseat', value: 'hotseat' }
]

const availableGenres = computed(() =>
  [...new Set(props.games.flatMap((game) => game.genres).filter(isPlausibleGenre))].sort((left, right) => left.localeCompare(right))
)

const activeFilterCount = computed(
  () =>
    Number(Boolean(model.value.search.trim())) +
    model.value.genres.length +
    model.value.features.length +
    Number(model.value.includePureSingleplayer)
)

function reset() {
  Object.assign(model.value, createGameFilterState())
}
</script>

<style scoped>
.game-filters {
  min-height: 32px;
}

.filter-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-items: center;
}

@media (max-width: 960px) {
  .filter-grid {
    grid-template-columns: 1fr;
  }
}
</style>
