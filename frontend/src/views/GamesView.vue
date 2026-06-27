<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4">Spiele</h1>
      <v-text-field v-model="search" prepend-inner-icon="mdi-magnify" label="Suche" density="compact" hide-details style="max-width: 340px" @keyup.enter="load" />
    </div>
    <v-row>
      <v-col cols="12" md="4">
        <v-card variant="flat">
          <v-card-title>Spiel anlegen</v-card-title>
          <v-card-text>
            <v-text-field v-model="form.title" label="Titel" density="compact" />
            <v-textarea v-model="form.description" label="Beschreibung" density="compact" rows="3" />
            <v-combobox v-model="form.genres" label="Genres" multiple chips density="compact" />
            <v-row>
              <v-col><v-text-field v-model.number="form.min_players" label="Min" type="number" density="compact" /></v-col>
              <v-col><v-text-field v-model.number="form.max_players" label="Max" type="number" density="compact" /></v-col>
            </v-row>
            <v-checkbox v-model="form.multiplayer" label="Multiplayer" density="compact" />
            <v-checkbox v-model="form.lan" label="LAN" density="compact" />
            <v-checkbox v-model="form.local_coop" label="Local Coop" density="compact" />
            <v-checkbox v-model="form.online_coop" label="Online Coop" density="compact" />
            <v-btn color="primary" prepend-icon="mdi-plus" @click="create">Anlegen</v-btn>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="8">
        <v-data-table class="compact-table" :headers="headers" :items="rows" :loading="loading || store.loading" loading-text="Spiele werden geladen..." :items-per-page="-1" density="compact" hide-default-footer>
          <template #item.title="{ item }">
            <strong>{{ item.title }}</strong>
            <div class="text-caption text-medium-emphasis">{{ item.description }}</div>
          </template>
          <template #item.features="{ item }">
            <v-chip v-if="item.lan" size="small" color="primary" class="mr-1">LAN</v-chip>
            <v-chip v-if="item.coop" size="small" color="secondary" class="mr-1">Coop</v-chip>
            <v-chip v-if="item.multiplayer" size="small" color="accent" class="mr-1">MP</v-chip>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { useLanStore } from '../store'
import type { Game } from '../types'

const store = useLanStore()
const search = ref('')
const games = ref<Game[]>([])
const loading = ref(false)
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
const headers = [
  { title: 'Spiel', key: 'title' },
  { title: 'Genres', key: 'genres' },
  { title: 'Spieler', key: 'players' },
  { title: 'Features', key: 'featureText' },
  { title: 'Besitzer', key: 'owner_count' }
]

const rows = computed(() =>
  games.value.map((game) => ({
    id: game.id,
    title: game.title,
    description: game.description,
    genres: game.genres.join(', '),
    players: playerLabel(game),
    featureText: featureText(game),
    lan: game.lan,
    coop: game.local_coop || game.online_coop,
    multiplayer: game.multiplayer,
    owner_count: owners(game.id)
  }))
)

onMounted(async () => {
  await store.refresh()
  await load()
})

async function load() {
  loading.value = true
  try {
    games.value = await api.games(search.value)
  } finally {
    loading.value = false
  }
}

async function create() {
  await api.createGame(form)
  Object.assign(form, { title: '', description: '', genres: [], min_players: 1, max_players: 4, multiplayer: true, lan: false, local_coop: false, online_coop: false })
  await store.refresh()
  await load()
}


function hasKnownPlayerMetadata(game: Game) {
  return Boolean(
    game.singleplayer ||
      game.multiplayer ||
      game.lan ||
      game.local_coop ||
      game.online_coop ||
      game.hotseat ||
      game.split_screen ||
      game.shared_screen ||
      game.description ||
      game.genres.length > 0
  )
}

function playerLabel(game: Game) {
  if (game.min_players === 1 && game.max_players === 1 && !hasKnownPlayerMetadata(game)) {
    return '?'
  }
  if (game.min_players === 1 && game.max_players === 1 && game.multiplayer) {
    return 'MP'
  }
  if (game.min_players === 1 && game.max_players === 1) {
    return 'Solo'
  }
  return `${game.min_players}-${game.max_players}`
}
function featureText(game: Game) {
  return [game.lan ? 'LAN' : '', game.local_coop || game.online_coop ? 'Coop' : '', game.multiplayer ? 'MP' : ''].filter(Boolean).join(', ')
}
const owners = (gameId: number) => new Set(store.ownerships.filter((own) => own.game_id === gameId).map((own) => own.participant_id)).size
</script>



