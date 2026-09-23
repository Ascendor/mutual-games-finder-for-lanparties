<template>
  <div class="page personal-games-page">
    <div class="d-flex align-center justify-space-between ga-3 flex-wrap mb-4">
      <div>
        <h1 class="text-headline-large">Meine Spiele</h1>
        <p class="text-medium-emphasis mb-0">
          {{ total }} Spiele für {{ participantName }}.
        </p>
      </div>
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

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <v-card v-if="currentParticipant" variant="flat" class="library-actions-card mb-4">
      <v-card-text class="library-actions">
        <div>
          <div class="text-body-large font-weight-bold">Bibliothek pflegen</div>
          <p class="text-body-medium text-medium-emphasis mb-0">
            Verbinde oder aktualisiere zuerst deine Spielekonten. Das ist der bevorzugte Weg, damit Plattformen,
            Spielzeiten und spätere Synchronisationen sauber bleiben.
          </p>
        </div>
        <v-btn to="/logins" color="primary" variant="tonal" prepend-icon="mdi-key-chain-variant">
          Meine Accounts & Logins
        </v-btn>
      </v-card-text>

      <v-divider />

      <v-expansion-panels variant="accordion" class="manual-library-expansion">
        <v-expansion-panel elevation="0">
          <v-expansion-panel-title>
            Fehlendes Spiel manuell ergänzen
          </v-expansion-panel-title>
          <v-expansion-panel-text>
            <ManualOwnershipPicker
              :participant="currentParticipant"
              :accounts="currentAccounts"
              @changed="loadPage"
            />
          </v-expansion-panel-text>
        </v-expansion-panel>
      </v-expansion-panels>
    </v-card>

    <div class="personal-games-filters mb-4">
      <v-text-field
        v-model="search"
        label="Spiel suchen"
        prepend-inner-icon="mdi-magnify"
        density="compact"
        clearable
        hide-details
      />
      <v-autocomplete
        v-model="selectedPlatforms"
        :items="platformOptions"
        item-title="title"
        item-value="value"
        label="Plattformen"
        prepend-inner-icon="mdi-controller-classic-outline"
        density="compact"
        multiple
        chips
        closable-chips
        clearable
        hide-details
      />
      <v-autocomplete
        v-model="selectedGenres"
        :items="genreOptions"
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
        v-model="selectedModes"
        :items="modeOptions"
        item-title="title"
        item-value="value"
        label="Multiplayermodi"
        prepend-inner-icon="mdi-controller-classic-outline"
        density="compact"
        multiple
        chips
        closable-chips
        clearable
        hide-details
      />
      <v-text-field
        v-model.number="playerCount"
        label="Spielbar mit"
        prepend-inner-icon="mdi-account-multiple-outline"
        suffix="Spieler:innen"
        type="number"
        min="1"
        max="128"
        density="compact"
        clearable
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
      loading-text="Deine Spiele werden geladen..."
      no-data-text="Kein Spiel gefunden."
      density="compact"
      @update:options="loadPage"
    >
      <template #item.title="{ item }">
        <strong>{{ item.game.title }}</strong>
        <div class="text-body-small text-medium-emphasis">
          {{ gameMeta(item.game) }}
        </div>
      </template>
      <template #item.platform="{ item }">
        <div class="platform-list">
          <div v-for="entry in item.platforms" :key="`${item.game.id}:${entry.platform}`" class="platform-entry">
            <v-chip
              size="small"
              color="primary"
              :variant="selectedPlatforms.includes(entry.platform) ? 'flat' : 'tonal'"
              class="platform-chip"
              role="button"
              tabindex="0"
              @click="filterByPlatform(entry.platform)"
              @keydown.enter.prevent="filterByPlatform(entry.platform)"
              @keydown.space.prevent="filterByPlatform(entry.platform)"
            >
              {{ platformTitle(entry.platform) }}
              <v-tooltip activator="parent" location="bottom">
                Nach {{ platformTitle(entry.platform) }} filtern
              </v-tooltip>
            </v-chip>
          </div>
        </div>
      </template>
      <template #item.playtime_minutes="{ item }">
        {{ formatPlaytime(item.total_playtime_minutes) }}
      </template>
    </v-data-table-server>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import ManualOwnershipPicker from '../components/ManualOwnershipPicker.vue'
import { clearParticipant, currentParticipantId, currentParticipantName } from '../playerIdentity'
import { platformTitle } from '../platforms'
import { useLanStore } from '../store'
import type { Account, Game, PersonalGame, Platform } from '../types'

const router = useRouter()
const store = useLanStore()
const games = ref<PersonalGame[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const search = ref('')
const selectedPlatforms = ref<Platform[]>([])
const selectedGenres = ref<string[]>([])
const selectedModes = ref<string[]>([])
const playerCount = ref<number | null>(null)
const availablePlatforms = ref<Platform[]>([])
const availableGenres = ref<string[]>([])
const accounts = ref<Account[]>([])
const page = ref(1)
const itemsPerPage = ref(50)
const sortBy = ref<{ key: string; order: 'asc' | 'desc' }[]>([
  { key: 'title', order: 'asc' }
])
let filterTimer: number | undefined
let pageRequest = 0

const currentParticipant = computed(() =>
  store.participants.find((participant) => participant.id === currentParticipantId.value)
)
const participantName = computed(() =>
  currentParticipant.value?.nickname || currentParticipantName.value || 'dich'
)
const currentAccounts = computed(() =>
  accounts.value.filter((account) => account.participant_id === currentParticipantId.value)
)
const platformOptions = computed(() =>
  availablePlatforms.value.map((platform) => ({
    value: platform,
    title: platformTitle(platform)
  }))
)
const genreOptions = computed(() => availableGenres.value)
const normalizedPlayerCount = computed(() => {
  const value = Number(playerCount.value)
  return Number.isInteger(value) && value >= 1 && value <= 128 ? value : null
})

const headers = [
  { title: 'Spiel', key: 'title' },
  { title: 'Plattformen', key: 'platform' },
  { title: 'Spielzeit', key: 'playtime_minutes' }
]

watch(
  [search, selectedPlatforms, selectedGenres, selectedModes, playerCount],
  () => {
    window.clearTimeout(filterTimer)
    filterTimer = window.setTimeout(() => {
      if (page.value === 1) {
        void loadPage()
      } else {
        page.value = 1
      }
    }, 250)
  },
  { deep: true }
)

onMounted(async () => {
  if (!store.participants.length) await store.refreshParticipants()
  if (!currentParticipantId.value || !currentParticipant.value) {
    clearParticipant()
    await router.replace({ path: '/player', query: { redirect: '/my-games' } })
    return
  }
  await loadAccounts()
  await loadPage()
})

onBeforeUnmount(() => {
  window.clearTimeout(filterTimer)
})

async function loadPage() {
  const participantId = currentParticipantId.value
  if (!participantId) return
  const request = ++pageRequest
  loading.value = true
  error.value = ''
  try {
    const sort = sortBy.value[0]
    const result = await api.personalGames({
      participantId,
      page: page.value,
      perPage: itemsPerPage.value,
      search: search.value,
      platforms: selectedPlatforms.value,
      genres: selectedGenres.value,
      modes: selectedModes.value,
      playerCount: normalizedPlayerCount.value,
      sortBy: sort?.key,
      sortDesc: sort?.order === 'desc'
    })
    if (request !== pageRequest) return
    games.value = result.items
    total.value = result.total
    availablePlatforms.value = result.platforms
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

async function loadAccounts() {
  try {
    accounts.value = await api.accounts()
  } catch (err) {
    error.value = readableError(err)
  }
}

function filterByPlatform(platform: Platform) {
  selectedPlatforms.value = selectedPlatforms.value.length === 1 && selectedPlatforms.value[0] === platform
    ? []
    : [platform]
}

function gameMeta(game: Game) {
  const parts = []
  if (game.player_count_known) {
    parts.push(game.min_players === game.max_players ? `${game.min_players} Spieler` : `${game.min_players}-${game.max_players} Spieler`)
  } else if (game.multiplayer) {
    parts.push('MP, Spielerzahl unbekannt')
  }
  if (game.genres.length) parts.push(game.genres.slice(0, 3).join(', '))
  return parts.join(' · ') || 'Keine Metadaten'
}

function formatPlaytime(minutes: number) {
  if (!minutes) return '0 h'
  const hours = Math.round(minutes / 60)
  return `${hours} h`
}

const modeOptions = [
  { title: 'Singleplayer', value: 'singleplayer' },
  { title: 'Multiplayer', value: 'multiplayer' },
  { title: 'LAN', value: 'lan' },
  { title: 'Coop', value: 'coop' },
  { title: 'Local Coop', value: 'local_coop' },
  { title: 'Online Coop', value: 'online_coop' },
  { title: 'Campaign Coop', value: 'campaign_coop' },
  { title: 'PvP / Versus', value: 'versus' },
  { title: 'Hotseat', value: 'hotseat' },
  { title: 'Split / Shared Screen', value: 'split_screen' },
  { title: 'Shared Screen', value: 'shared_screen' },
  { title: 'Kostenlos', value: 'free' }
]

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
.personal-games-page {
  max-width: 1180px;
}

.personal-games-filters {
  display: grid;
  grid-template-columns: repeat(5, minmax(160px, 1fr));
  gap: 12px;
}

.library-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.library-actions > div {
  min-width: 0;
}

.manual-library-expansion {
  border-radius: 0;
}

.manual-library-expansion :deep(.v-expansion-panel-title) {
  min-height: 44px;
  font-size: 0.95rem;
}

.manual-library-expansion :deep(.manual-library) {
  padding: 0;
  border-top: 0;
}

.platform-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  align-items: flex-start;
}

.platform-entry {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.platform-chip {
  cursor: pointer;
}

@media (max-width: 1100px) {
  .personal-games-filters {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 680px) {
  .personal-games-filters {
    grid-template-columns: 1fr;
  }

  .library-actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
