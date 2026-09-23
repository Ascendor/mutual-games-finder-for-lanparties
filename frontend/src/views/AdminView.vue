<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-headline-large">Administration</h1>
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
        <v-btn class="mt-4" color="primary" prepend-icon="mdi-lock-open-outline" :loading="busy === 'unlock'" @click="unlock">Entsperren</v-btn>
      </v-card-text>
    </v-card>

    <template v-else>
      <v-row>
        <v-col cols="12">
          <v-card variant="flat">
            <v-card-title>Orga-Dashboard</v-card-title>
            <v-card-text>
              <p class="text-medium-emphasis">
                Suchtrends, Datenqualität der anwesenden Gruppe und Sync-Probleme auf einen Blick.
              </p>
              <v-btn to="/admin/dashboard" color="primary" variant="tonal" prepend-icon="mdi-view-dashboard-outline">
                Dashboard öffnen
              </v-btn>
            </v-card-text>
          </v-card>
        </v-col>

        <v-col cols="12">
          <v-card variant="flat">
            <v-card-title>Nutzungsanalyse</v-card-title>
            <v-card-text>
              <p class="text-medium-emphasis">
                Suchen, Seitenaufrufe und Nutzung pro Teilnehmer für das LAN-Wochenende auswerten.
              </p>
              <v-btn to="/admin/nutzung" color="primary" variant="tonal" prepend-icon="mdi-chart-box-outline">
                Analyse öffnen
              </v-btn>
            </v-card-text>
          </v-card>
        </v-col>

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
            <v-card-title>Spiele</v-card-title>
            <v-card-text>
              <p class="text-medium-emphasis">
                Die paginierte Spieleverwaltung enthält Suche, Filter und Metadatenpflege für einzelne Spiele.
              </p>
              <v-btn to="/admin/games" color="primary" variant="tonal" prepend-icon="mdi-gamepad-variant-outline">
                Spiele verwalten
              </v-btn>
            </v-card-text>
          </v-card>
        </v-col>
      </v-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminUnlocked, tryUnlockAdmin } from '../adminAccess'
import { api } from '../api'
import { platformTitle } from '../platforms'
import { useLanStore } from '../store'

const store = useLanStore()
const route = useRoute()
const router = useRouter()
const password = ref('')
const unlocked = adminUnlocked
const loading = ref(false)
const busy = ref('')
const error = ref('')
const message = ref('')
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

onMounted(() => {
  if (unlocked.value) load()
})

async function unlock() {
  error.value = ''
  busy.value = 'unlock'
  try {
    if (!await tryUnlockAdmin(password.value)) {
      error.value = 'Falsches Passwort.'
      return
    }
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    error.value = raw.includes('401') ? 'Falsches Passwort.' : raw
    return
  } finally {
    busy.value = ''
  }
  password.value = ''
  const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : ''
  if (['/admin/dashboard', '/admin/nutzung', '/admin/logins', '/admin/participants', '/admin/games', '/admin/sync'].includes(redirect)) {
    void router.replace(redirect)
    return
  }
  load()
}

async function load() {
  loading.value = true
  try {
    const [participants, accounts] = await Promise.all([
      api.participants(),
      api.accounts()
    ])
    store.participants = participants
    store.accounts = accounts
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

</style>
