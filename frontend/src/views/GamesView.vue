<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4">Spiele</h1>
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
        <GameFilterBar v-model="filters" :games="games" />
        <v-data-table class="compact-table" :headers="headers" :items="rows" :loading="loading || store.loading" loading-text="Spiele werden geladen..." no-data-text="Keine Spiele entsprechen den Filtern." :items-per-page="-1" density="compact" hide-default-footer>
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
import GameFilterBar from '../components/GameFilterBar.vue'
import { createGameFilterState, matchesGameFilters } from '../gameFilters'
import { useLanStore } from '../store'
import type { Game } from '../types'

const store = useLanStore()
const games = ref<Game[]>([])
const loading = ref(false)
const filters = ref(createGameFilterState())
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
  { title: 'Quelle', key: 'metadata_source' },
  { title: 'Besitzer', key: 'owner_count' }
]

const rows = computed(() =>
  games.value.filter((game) => matchesGameFilters(game, filters.value)).map((game) => ({
    id: game.id,
    title: game.title,
    description: game.description,
    genres: game.genres.join(', '),
    players: playerLabel(game),
    featureText: featureText(game),
    lan: game.lan,
    coop: game.local_coop || game.online_coop,
    multiplayer: game.multiplayer,
    metadata_source: game.metadata_source || '-',
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
    games.value = await api.games()
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


function playerLabel(game: Game) {
  if (!game.player_count_known || (game.multiplayer && game.max_players <= 1)) {
    return game.multiplayer ? 'MP (?)' : '?'
  }
  if (game.min_players === 1 && game.max_players === 1) {
    return 'Solo'
  }
  return `${game.min_players}-${game.max_players}`
}
function featureText(game: Game) {
  return [
    game.singleplayer ? 'SP' : '',
    game.multiplayer ? 'MP' : '',
    game.lan ? 'LAN' : '',
    game.local_coop ? 'Local Coop' : '',
    game.online_coop ? 'Online Coop' : '',
    game.campaign_coop ? 'Campaign Coop' : '',
    game.split_screen ? 'Split' : '',
    game.hotseat ? 'Hotseat' : '',
    game.versus ? 'VS' : ''
  ].filter(Boolean).join(', ')
}
const owners = (gameId: number) => new Set(store.ownerships.filter((own) => own.game_id === gameId).map((own) => own.participant_id)).size
</script>



