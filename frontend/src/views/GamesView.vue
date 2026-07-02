<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between ga-3 flex-wrap mb-4">
      <div>
        <h1 class="text-h4">Spieleverwaltung</h1>
        <p class="text-medium-emphasis mb-0">{{ total }} Spiele entsprechen der Auswahl.</p>
      </div>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-steam"
          :loading="steamSyncRunning"
          :disabled="Boolean(activeRun)"
          @click="startSteamSync"
        >
          Steam-Metadaten vollständig laden
        </v-btn>
        <v-btn
          icon="mdi-refresh"
          variant="text"
          :loading="loading"
          aria-label="Liste aktualisieren"
          @click="loadPage"
        >
          <v-icon>mdi-refresh</v-icon>
          <v-tooltip activator="parent" location="bottom">Liste aktualisieren</v-tooltip>
        </v-btn>
      </div>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="message" type="success" variant="tonal" class="mb-4">{{ message }}</v-alert>
    <v-alert v-if="activeRun" type="info" variant="tonal" class="mb-4">
      <div class="d-flex align-center justify-space-between ga-3 mb-2">
        <strong>{{ activeRun.message }}</strong>
        <span v-if="activeRun.progress_total">
          {{ activeRun.progress_current }} / {{ activeRun.progress_total }}
        </span>
      </div>
      <v-progress-linear
        :model-value="runProgress"
        :indeterminate="!activeRun.progress_total"
        height="8"
        color="primary"
      />
    </v-alert>

    <v-expansion-panels class="mb-4">
      <v-expansion-panel>
        <v-expansion-panel-title>Spiel manuell anlegen</v-expansion-panel-title>
        <v-expansion-panel-text>
          <div class="manual-game-form">
            <v-text-field v-model="form.title" label="Titel" density="compact" hide-details />
            <v-combobox v-model="form.genres" label="Genres" multiple chips density="compact" hide-details />
            <v-text-field v-model.number="form.min_players" label="Min. Spieler" type="number" density="compact" hide-details />
            <v-text-field v-model.number="form.max_players" label="Max. Spieler" type="number" density="compact" hide-details />
            <v-checkbox v-model="form.multiplayer" label="Multiplayer" density="compact" hide-details />
            <v-checkbox v-model="form.lan" label="LAN" density="compact" hide-details />
            <v-btn color="primary" prepend-icon="mdi-plus" :disabled="!form.title.trim()" @click="create">
              Anlegen
            </v-btn>
          </div>
        </v-expansion-panel-text>
      </v-expansion-panel>
    </v-expansion-panels>

    <div class="game-page-filters mb-4">
      <v-text-field
        v-model="search"
        label="Spiel suchen"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        clearable
        hide-details
      />
      <v-autocomplete
        v-model="selectedGenres"
        :items="availableGenres"
        label="Genres"
        prepend-inner-icon="mdi-tag-multiple-outline"
        multiple
        chips
        closable-chips
        clearable
        density="compact"
        hide-details
      />
      <v-select
        v-model="selectedFeatures"
        :items="featureOptions"
        item-title="title"
        item-value="value"
        label="Features"
        prepend-inner-icon="mdi-controller-classic-outline"
        multiple
        chips
        closable-chips
        clearable
        density="compact"
        hide-details
      />
      <v-switch
        v-model="includePureSingleplayer"
        label="Reine Singleplayer"
        color="primary"
        density="compact"
        hide-details
      />
      <v-switch
        v-model="includeNonGames"
        label="Ausgeblendete Software"
        color="primary"
        density="compact"
        hide-details
      />
    </div>

    <v-data-table-server
      v-model:page="page"
      v-model:items-per-page="itemsPerPage"
      v-model:sort-by="sortBy"
      class="compact-table"
      :headers="headers"
      :items="games"
      :items-length="total"
      :loading="loading"
      :items-per-page-options="[25, 50, 100, 200]"
      loading-text="Spiele werden geladen..."
      no-data-text="Keine Spiele entsprechen den Filtern."
      density="compact"
      @update:options="loadPage"
    >
      <template #item.title="{ item }">
        <strong>{{ item.title }}</strong>
        <div class="text-caption text-medium-emphasis game-description">{{ item.description }}</div>
        <div v-if="!item.is_game" class="text-caption text-error">
          Ausgeblendet: {{ item.non_game_reason || 'als Software erkannt' }}
        </div>
      </template>
      <template #item.genres="{ item }">{{ item.genres.join(', ') || '-' }}</template>
      <template #item.players="{ item }">{{ playerLabel(item) }}</template>
      <template #item.features="{ item }">
        <v-chip v-if="item.multiplayer" size="small" color="accent" class="mr-1">MP</v-chip>
        <v-chip v-if="item.lan" size="small" color="primary" class="mr-1">LAN</v-chip>
        <v-chip v-if="item.local_coop || item.online_coop" size="small" color="secondary" class="mr-1">Coop</v-chip>
        <v-chip v-if="item.is_free" size="small" color="success" variant="tonal">Free</v-chip>
      </template>
      <template #item.metadata_updated_at="{ item }">
        <div>{{ item.metadata_source || '-' }}</div>
        <div class="text-caption text-medium-emphasis">{{ formatDate(item.metadata_updated_at) }}</div>
      </template>
      <template #item.actions="{ item }">
        <div class="d-flex justify-end ga-1">
          <v-btn
            icon="mdi-database-refresh-outline"
            size="small"
            variant="text"
            color="primary"
            :loading="singleSyncGameId === item.id"
            :disabled="Boolean(activeRun)"
            :aria-label="`Metadaten für ${item.title} neu laden`"
            @click="resyncGame(item)"
          >
            <v-icon>mdi-database-refresh-outline</v-icon>
            <v-tooltip activator="parent" location="bottom">Metadaten neu laden</v-tooltip>
          </v-btn>
          <v-btn
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            color="error"
            :aria-label="`${item.title} löschen`"
            @click="deleteGame(item)"
          >
            <v-icon>mdi-delete-outline</v-icon>
            <v-tooltip activator="parent" location="bottom">Spiel löschen</v-tooltip>
          </v-btn>
        </div>
      </template>
    </v-data-table-server>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { api } from '../api'
import type { Game, GameListItem, SyncRun } from '../types'

const games = ref<GameListItem[]>([])
const total = ref(0)
const availableGenres = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const message = ref('')
const page = ref(1)
const itemsPerPage = ref(50)
const sortBy = ref<{ key: string; order: 'asc' | 'desc' }[]>([
  { key: 'title', order: 'asc' }
])
const search = ref('')
const selectedGenres = ref<string[]>([])
const selectedFeatures = ref<string[]>([])
const includePureSingleplayer = ref(false)
const includeNonGames = ref(false)
const activeRun = ref<SyncRun>()
const singleSyncGameId = ref<number>()
let filterTimer: number | undefined
let runTimer: number | undefined
let pageRequest = 0

const form = reactive({
  title: '',
  description: '',
  genres: [] as string[],
  min_players: 1,
  max_players: 4,
  multiplayer: true,
  lan: false,
  local_coop: false,
  online_coop: false
})

const featureOptions = [
  { title: 'Singleplayer', value: 'singleplayer' },
  { title: 'Multiplayer', value: 'multiplayer' },
  { title: 'Coop', value: 'coop' },
  { title: 'Local Coop', value: 'local_coop' },
  { title: 'Online Coop', value: 'online_coop' },
  { title: 'PvP / Versus', value: 'versus' },
  { title: 'LAN', value: 'lan' },
  { title: 'Split / Shared Screen', value: 'split_screen' },
  { title: 'Hotseat', value: 'hotseat' },
  { title: 'Kostenlos', value: 'free' }
]

const headers = [
  { title: 'Spiel', key: 'title' },
  { title: 'Genres', key: 'genres', sortable: false },
  { title: 'Spieler', key: 'players', sortable: false },
  { title: 'Features', key: 'features', sortable: false },
  { title: 'Besitzer', key: 'owner_count' },
  { title: 'Metadaten', key: 'metadata_updated_at' },
  { title: '', key: 'actions', sortable: false }
]

const steamSyncRunning = computed(() => activeRun.value?.kind === 'steam_metadata')
const runProgress = computed(() => {
  if (!activeRun.value?.progress_total) return 0
  return Math.round(activeRun.value.progress_current / activeRun.value.progress_total * 100)
})

watch(
  [search, selectedGenres, selectedFeatures, includePureSingleplayer, includeNonGames],
  () => {
    window.clearTimeout(filterTimer)
    filterTimer = window.setTimeout(() => {
      if (page.value === 1) {
        void loadPage()
      } else {
        page.value = 1
      }
    }, 300)
  },
  { deep: true }
)

onBeforeUnmount(() => {
  window.clearTimeout(filterTimer)
  window.clearTimeout(runTimer)
})

async function loadPage() {
  const request = ++pageRequest
  loading.value = true
  error.value = ''
  try {
    const sort = sortBy.value[0]
    const result = await api.gamesPage({
      page: page.value,
      perPage: itemsPerPage.value,
      search: search.value,
      genres: selectedGenres.value,
      features: selectedFeatures.value,
      includePureSingleplayer: includePureSingleplayer.value,
      includeNonGames: includeNonGames.value,
      sortBy: sort?.key,
      sortDesc: sort?.order === 'desc'
    })
    if (request !== pageRequest) return
    games.value = result.items
    total.value = result.total
    availableGenres.value = result.genres
    if (page.value > 1 && !result.items.length && result.total) {
      page.value = Math.ceil(result.total / itemsPerPage.value)
    }
  } catch (err) {
    if (request !== pageRequest) return
    error.value = readableError(err)
  } finally {
    if (request === pageRequest) loading.value = false
  }
}

async function create() {
  error.value = ''
  try {
    await api.createGame(form)
    Object.assign(form, {
      title: '',
      description: '',
      genres: [],
      min_players: 1,
      max_players: 4,
      multiplayer: true,
      lan: false,
      local_coop: false,
      online_coop: false
    })
    message.value = 'Spiel wurde angelegt.'
    await loadPage()
  } catch (err) {
    error.value = readableError(err)
  }
}

async function startSteamSync() {
  error.value = ''
  message.value = ''
  try {
    activeRun.value = await api.syncAllSteamMetadata()
    scheduleRunPoll()
  } catch (err) {
    error.value = readableError(err)
  }
}

async function resyncGame(game: Game) {
  error.value = ''
  message.value = ''
  singleSyncGameId.value = game.id
  try {
    activeRun.value = await api.syncGameMetadata(game.id)
    scheduleRunPoll()
  } catch (err) {
    singleSyncGameId.value = undefined
    error.value = readableError(err)
  }
}

function scheduleRunPoll() {
  window.clearTimeout(runTimer)
  runTimer = window.setTimeout(pollRun, 1500)
}

async function pollRun() {
  if (!activeRun.value) return
  try {
    const run = await api.syncRun(activeRun.value.id)
    activeRun.value = run
    if (!run.finished_at) {
      scheduleRunPoll()
      return
    }
    if (run.success) {
      message.value = run.message
    } else {
      error.value = run.message
    }
    activeRun.value = undefined
    singleSyncGameId.value = undefined
    await loadPage()
  } catch (err) {
    error.value = readableError(err)
    scheduleRunPoll()
  }
}

async function deleteGame(game: Game) {
  if (!window.confirm(`${game.title} wirklich löschen? Alle Ownerships werden ebenfalls entfernt.`)) return
  error.value = ''
  try {
    await api.deleteGame(game.id)
    message.value = `${game.title} wurde gelöscht.`
    await loadPage()
  } catch (err) {
    error.value = readableError(err)
  }
}

function playerLabel(game: Game) {
  if (!game.player_count_known || (game.multiplayer && game.max_players <= 1)) {
    return game.multiplayer ? 'MP (?)' : '?'
  }
  if (game.min_players === 1 && game.max_players === 1) return 'Solo'
  return `${game.min_players}-${game.max_players}`
}

function formatDate(value?: string | null) {
  if (!value) return 'Noch nicht geladen'
  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(new Date(value))
}

function readableError(value: unknown) {
  const raw = value instanceof Error ? value.message : String(value)
  try {
    const parsed = JSON.parse(raw)
    return parsed.detail || parsed.message || raw
  } catch {
    return raw.replace(/^Error:\s*/i, '')
  }
}
</script>

<style scoped>
.game-page-filters {
  display: grid;
  grid-template-columns: minmax(220px, 1.2fr) minmax(220px, 1fr) minmax(220px, 1fr) auto auto;
  gap: 12px;
  align-items: center;
}

.manual-game-form {
  display: grid;
  grid-template-columns: 2fr 2fr repeat(4, minmax(110px, 1fr)) auto;
  gap: 12px;
  align-items: center;
}

.game-description {
  max-width: 44rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1200px) {
  .game-page-filters,
  .manual-game-form {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 700px) {
  .game-page-filters,
  .manual-game-form {
    grid-template-columns: 1fr;
  }
}
</style>
