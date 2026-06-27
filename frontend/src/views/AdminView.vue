<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4">Administration</h1>
        <p class="text-medium-emphasis">Datenpflege fuer Teilnehmer, Accounts und Spiele.</p>
      </div>
      <v-btn v-if="unlocked" color="primary" prepend-icon="mdi-refresh" :loading="store.loading || loading" @click="load">Aktualisieren</v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="message" type="success" variant="tonal" class="mb-4">{{ message }}</v-alert>

    <v-card v-if="!unlocked" variant="flat" class="admin-login">
      <v-card-title>Passwort</v-card-title>
      <v-card-text>
        <v-text-field v-model="password" label="Admin-Passwort" type="password" density="compact" hide-details="auto" @keyup.enter="unlock" />
        <v-btn class="mt-4" color="primary" prepend-icon="mdi-lock-open-outline" @click="unlock">Entsperren</v-btn>
      </v-card-text>
    </v-card>

    <template v-else>
      <v-row>
        <v-col cols="12" lg="6">
          <v-card variant="flat">
            <v-card-title>Spieler</v-card-title>
            <v-card-text>
              <v-data-table class="compact-table" :headers="participantHeaders" :items="participantRows" :items-per-page="-1" density="compact" hide-default-footer>
                <template #item.actions="{ item }">
                  <div class="text-right">
                    <v-btn size="small" color="error" variant="text" prepend-icon="mdi-delete-outline" :loading="busy === `participant:${item.id}`" @click="deleteParticipant(item.id)">Löschen</v-btn>
                  </div>
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12" lg="6">
          <v-card variant="flat">
            <v-card-title>Accounts</v-card-title>
            <v-card-text>
              <v-data-table class="compact-table" :headers="accountHeaders" :items="accountRows" :items-per-page="-1" density="compact" hide-default-footer>
                <template #item.actions="{ item }">
                  <div class="text-right">
                    <v-btn size="small" color="error" variant="text" prepend-icon="mdi-delete-outline" :loading="busy === `account:${item.id}`" @click="deleteAccount(item.id)">Löschen</v-btn>
                  </div>
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12">
          <v-card variant="flat">
            <v-card-title class="d-flex align-center justify-space-between">
              <span>Spiele</span>
              <v-text-field v-model="gameSearch" label="Suchen" density="compact" hide-details="auto" prepend-inner-icon="mdi-magnify" class="game-search" />
            </v-card-title>
            <v-card-text>
              <v-data-table class="compact-table" :headers="gameHeaders" :items="gameRows" :items-per-page="-1" density="compact" hide-default-footer>
                <template #item.actions="{ item }">
                  <div class="text-right">
                    <v-btn size="small" color="error" variant="text" prepend-icon="mdi-delete-outline" :loading="busy === `game:${item.id}`" @click="deleteGame(item.id)">Löschen</v-btn>
                  </div>
                </template>
              </v-data-table>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useLanStore } from '../store'
import type { Platform } from '../types'

const ADMIN_PASSWORD = 'QC4lF93bYgwTHRT4xRynsAIz3San1lDW'
const store = useLanStore()
const password = ref('')
const unlocked = ref(sessionStorage.getItem('lan-admin-unlocked') === 'true')
const loading = ref(false)
const busy = ref('')
const error = ref('')
const message = ref('')
const gameSearch = ref('')
const participantHeaders = [
  { title: 'Nickname', key: 'nickname' },
  { title: 'Status', key: 'status' },
  { title: 'Accounts', key: 'account_count' },
  { title: '', key: 'actions', sortable: false }
]
const accountHeaders = [
  { title: 'Spieler', key: 'participant' },
  { title: 'Provider', key: 'provider' },
  { title: 'Account', key: 'account' },
  { title: '', key: 'actions', sortable: false }
]
const gameHeaders = [
  { title: 'Titel', key: 'title' },
  { title: 'Besitzer', key: 'owner_count' },
  { title: '', key: 'actions', sortable: false }
]

const participantRows = computed(() =>
  store.participants.map((participant) => ({
    id: participant.id,
    nickname: participant.nickname,
    status: participant.present ? 'anwesend' : 'abwesend',
    account_count: accountsFor(participant.id).length
  }))
)

const accountRows = computed(() =>
  store.accounts.map((account) => ({
    id: account.id,
    participant: participantName(account.participant_id),
    provider: platformTitle(account.platform),
    account: account.display_name || account.account_id
  }))
)

const filteredGames = computed(() => {
  const search = gameSearch.value.trim().toLocaleLowerCase()
  const games = search ? store.games.filter((game) => game.title.toLocaleLowerCase().includes(search)) : store.games
  return games.slice(0, 100)
})

const gameRows = computed(() =>
  filteredGames.value.map((game) => ({
    id: game.id,
    title: game.title,
    owner_count: ownerCount(game.id)
  }))
)

onMounted(() => {
  if (unlocked.value) load()
})

function unlock() {
  error.value = ''
  if (password.value !== ADMIN_PASSWORD) {
    error.value = 'Falsches Passwort.'
    return
  }
  sessionStorage.setItem('lan-admin-unlocked', 'true')
  unlocked.value = true
  password.value = ''
  load()
}

async function load() {
  loading.value = true
  try {
    await store.refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function accountsFor(participantId: number) {
  return store.accounts.filter((account) => account.participant_id === participantId)
}

function participantName(participantId: number) {
  return store.participants.find((participant) => participant.id === participantId)?.nickname ?? `Teilnehmer ${participantId}`
}

function ownerCount(gameId: number) {
  return store.ownerships.filter((ownership) => ownership.game_id === gameId).length
}

function platformTitle(platform: Platform) {
  const titles: Record<string, string> = { steam: 'Steam', epic: 'Epic Games', gog: 'GOG', xbox: 'Xbox Live', ubisoft: 'Ubisoft Connect', ea: 'EA App', amazon: 'Amazon Games', battle_net: 'Battle.net', bethesda: 'Bethesda', gamejolt: 'Game Jolt', humble: 'Humble', itch: 'itch.io', legacy: 'Legacy Games', nintendo: 'Nintendo', playstation: 'PlayStation', riot: 'Riot', rockstar: 'Rockstar', local: 'Lokal' }
  return titles[platform] ?? platform
}

async function deleteParticipant(id: number) {
  const name = participantName(id)
  if (!window.confirm(`${name} wirklich löschen? Accounts und Besitzdaten dieses Spielers werden ebenfalls entfernt.`)) return
  await runDelete(`participant:${id}`, () => api.deleteParticipant(id), `${name} gelöscht.`)
}

async function deleteAccount(id: number) {
  const account = store.accounts.find((item) => item.id === id)
  const label = account ? `${platformTitle(account.platform)} / ${participantName(account.participant_id)}` : `Account ${id}`
  if (!window.confirm(`${label} wirklich löschen? Besitzdaten dieses Accounts werden entfernt.`)) return
  await runDelete(`account:${id}`, () => api.deleteAccount(id), `${label} gelöscht.`)
}

async function deleteGame(id: number) {
  const game = store.games.find((item) => item.id === id)
  const label = game?.title ?? `Spiel ${id}`
  if (!window.confirm(`${label} wirklich löschen? Alle Ownerships zu diesem Spiel werden ebenfalls entfernt.`)) return
  await runDelete(`game:${id}`, () => api.deleteGame(id), `${label} gelöscht.`)
}

async function runDelete(key: string, action: () => Promise<void>, success: string) {
  busy.value = key
  error.value = ''
  message.value = ''
  try {
    await action()
    message.value = success
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = ''
  }
}
</script>

<style scoped>
.admin-login {
  max-width: 420px;
}

.game-search {
  max-width: 320px;
}
</style>
