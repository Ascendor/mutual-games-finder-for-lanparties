<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4">Mitspieler finden</h1>
      <v-switch v-model="presentOnly" color="primary" label="Nur Anwesende" hide-details @update:model-value="loadOwners" />
    </div>

    <v-row class="mb-4" align="center">
      <v-col cols="12" md="8">
        <v-autocomplete
          v-model="selectedGameId"
          v-model:search="search"
          :items="games"
          item-title="title"
          item-value="id"
          label="Spiel"
          prepend-inner-icon="mdi-gamepad-variant-outline"
          density="compact"
          clearable
          hide-details
          no-filter
          :loading="gamesLoading"
          @update:search="loadGames"
          @update:model-value="loadOwners"
        />
      </v-col>
      <v-col cols="12" md="4" class="d-flex align-center ga-2">
        <v-btn color="primary" prepend-icon="mdi-account-search-outline" :disabled="!selectedGameId" :loading="loading" @click="loadOwners">Suchen</v-btn>
      </v-col>
    </v-row>

    <v-data-table class="compact-table" density="compact" :headers="headers" :items="rows" :loading="loading" loading-text="Besitzer werden geladen..." :items-per-page="-1" hide-default-footer>
      <template #item.participant_name="{ item }">
            <div class="d-flex align-center ga-2">
              <v-icon :color="item.present ? 'success' : 'medium-emphasis'" size="small">mdi-circle</v-icon>
              <strong>{{ item.participant_name }}</strong>
            </div>
            <div v-if="item.real_name" class="text-caption text-medium-emphasis">{{ item.real_name }}</div>
      </template>
      <template #item.platforms="{ item }">
        <v-chip v-for="platform in item.platform_values" :key="platform" size="small" color="primary" class="mr-1">{{ platformLabel(platform) }}</v-chip>
      </template>
      <template #item.playtime_hours="{ item }">{{ item.playtime_hours }} h</template>
    </v-data-table>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { api } from '../api'
import { useRoute } from 'vue-router'
import type { GameOption, GameOwner, Platform } from '../types'

const route = useRoute()
const games = ref<GameOption[]>([])
const owners = ref<GameOwner[]>([])
const selectedGameId = ref<number | null>(null)
const search = ref('')
const presentOnly = ref(true)
const loading = ref(false)
const gamesLoading = ref(false)
const headers = [
  { title: 'Teilnehmer', key: 'participant_name' },
  { title: 'Plattformen', key: 'platforms' },
  { title: 'Accounts', key: 'accounts' },
  { title: 'Spielzeit', key: 'playtime_hours' }
]
const rows = computed(() =>
  owners.value.map((owner) => ({
    id: owner.participant.id,
    participant_name: owner.participant.nickname,
    real_name: owner.participant.real_name,
    present: owner.participant.present,
    platform_values: owner.platforms,
    platforms: owner.platforms.map(platformLabel).join(', '),
    accounts: owner.account_names.join(', '),
    playtime_hours: hours(owner.total_playtime_minutes)
  }))
)
let searchTimer: number | undefined

onMounted(async () => {
  const initialGame = typeof route.query.game === 'string' ? route.query.game : ''
  search.value = initialGame
  gamesLoading.value = true
  try {
    games.value = await api.gameOptions(initialGame, 100)
  } finally {
    gamesLoading.value = false
  }
  if (initialGame) {
    const normalized = initialGame.trim().toLocaleLowerCase()
    const match = games.value.find((game) => game.title.toLocaleLowerCase() === normalized) ?? games.value[0]
    if (match) {
      selectedGameId.value = match.id
      await loadOwners()
    }
  }
})

watch(selectedGameId, () => {
  if (!selectedGameId.value) {
    owners.value = []
  }
})

function loadGames(value: string) {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(async () => {
    gamesLoading.value = true
    try {
      games.value = await api.gameOptions(value || '', value ? 100 : 500)
    } finally {
      gamesLoading.value = false
    }
  }, 180)
}

async function loadOwners() {
  if (!selectedGameId.value) {
    owners.value = []
    return
  }
  loading.value = true
  try {
    owners.value = await api.gameOwners(selectedGameId.value, presentOnly.value)
  } finally {
    loading.value = false
  }
}

function hours(minutes: number) {
  return Math.round(minutes / 60)
}

function platformLabel(platform: Platform) {
  const labels: Record<string, string> = {
    steam: 'Steam',
    epic: 'Epic',
    gog: 'GOG',
    xbox: 'Xbox',
    ubisoft: 'Ubisoft',
    ea: 'EA',
    amazon: 'Amazon',
    battle_net: 'Battle.net',
    bethesda: 'Bethesda',
    gamejolt: 'Game Jolt',
    humble: 'Humble',
    itch: 'itch.io',
    legacy: 'Legacy',
    nintendo: 'Nintendo',
    playstation: 'PlayStation',
    riot: 'Riot',
    rockstar: 'Rockstar',
    local: 'Lokal'
  }
  return labels[platform] ?? platform
}
</script>
