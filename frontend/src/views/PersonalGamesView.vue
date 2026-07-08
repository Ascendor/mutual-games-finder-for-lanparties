<template>
  <div class="page personal-games-page">
    <div class="d-flex align-center justify-space-between ga-3 flex-wrap mb-4">
      <div>
        <h1 class="text-h4">Meine Spiele</h1>
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

    <div class="personal-games-filters mb-4">
      <v-text-field
        v-model="search"
        label="Spiel suchen"
        prepend-inner-icon="mdi-magnify"
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
        <div class="text-caption text-medium-emphasis">
          {{ gameMeta(item.game) }}
        </div>
      </template>
      <template #item.platform="{ item }">
        <div class="platform-list">
          <div v-for="entry in item.platforms" :key="`${item.game.id}:${entry.platform}`" class="platform-entry">
            <v-chip size="small" color="primary" variant="tonal">
              {{ platformTitle(entry.platform) }}
            </v-chip>
            <span v-if="entry.account_display_name" class="text-caption text-medium-emphasis">
              {{ entry.account_display_name }}
            </span>
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
import { clearParticipant, currentParticipantId, currentParticipantName } from '../playerIdentity'
import { useLanStore } from '../store'
import type { Game, PersonalGame, Platform } from '../types'

const router = useRouter()
const store = useLanStore()
const games = ref<PersonalGame[]>([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const search = ref('')
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

const headers = [
  { title: 'Spiel', key: 'title' },
  { title: 'Plattformen', key: 'platform' },
  { title: 'Spielzeit', key: 'playtime_minutes' }
]

watch(search, () => {
  window.clearTimeout(filterTimer)
  filterTimer = window.setTimeout(() => {
    if (page.value === 1) {
      void loadPage()
    } else {
      page.value = 1
    }
  }, 250)
})

onMounted(async () => {
  if (!store.participants.length) await store.refreshParticipants()
  if (!currentParticipantId.value || !currentParticipant.value) {
    clearParticipant()
    await router.replace({ path: '/player', query: { redirect: '/my-games' } })
    return
  }
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
      sortBy: sort?.key,
      sortDesc: sort?.order === 'desc'
    })
    if (request !== pageRequest) return
    games.value = result.items
    total.value = result.total
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

function platformTitle(platform: Platform) {
  const titles: Record<string, string> = {
    steam: 'Steam',
    epic: 'Epic Games',
    gog: 'GOG',
    ubisoft: 'Ubisoft Connect',
    xbox: 'Xbox Live',
    amazon: 'Amazon Games',
    battle_net: 'Battle.net',
    humble: 'Humble',
    humble_key: 'Humble Key',
    meta: 'Meta / Oculus',
    rockstar: 'Rockstar',
    local: 'Lokal'
  }
  return titles[platform] || platform
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
.personal-games-page {
  max-width: 1180px;
}

.personal-games-filters {
  max-width: 440px;
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
</style>
