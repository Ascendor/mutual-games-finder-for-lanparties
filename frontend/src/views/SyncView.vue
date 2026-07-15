<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4">Synchronisation</h1>
      <div class="d-flex ga-2 flex-wrap">
        <v-btn
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-database-sync-outline"
          :loading="metadataLoading"
          :disabled="metadataRunning"
          @click="syncMetadata"
        >
          Alle Metadaten aktualisieren
        </v-btn>
        <v-btn
          color="secondary"
          variant="tonal"
          prepend-icon="mdi-wrench-outline"
          :loading="repairLoading"
          :disabled="metadataRunning"
          @click="repairMetadata"
        >
          Unbekannte Metadaten prüfen
        </v-btn>
        <v-btn to="/accounts" color="primary" variant="tonal" prepend-icon="mdi-account-key">Accounts</v-btn>
      </div>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="metadataMessage" type="success" variant="tonal" class="mb-4">{{ metadataMessage }}</v-alert>

    <v-row>
      <v-col cols="12" md="5">
        <v-card variant="flat">
          <v-card-title>Accounts synchronisieren</v-card-title>
          <v-list>
            <v-list-item v-for="account in store.accounts" :key="account.id" :title="accountLabel(account.id)" :subtitle="account.last_error || account.last_successful_sync || 'Noch nie synchronisiert'">
              <template v-if="canSyncAccount(account.platform)" #append>
                <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="loading === account.id" @click="sync(account.id)">Sync</v-btn>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
      <v-col cols="12" md="7">
        <v-data-table class="compact-table" :headers="headers" :items="rows" :loading="store.loading" loading-text="Synchronisationsprotokoll wird geladen..." :items-per-page="-1" density="compact" hide-default-footer>
          <template #item.status="{ item }">
            <v-chip :color="item.statusColor" size="small">{{ item.status }}</v-chip>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api } from '../api'
import { useLanStore } from '../store'

const store = useLanStore()
const loading = ref<number | null>(null)
const metadataLoading = ref(false)
const repairLoading = ref(false)
const error = ref('')
const metadataMessage = ref('')
const headers = [
  { title: 'Zeit', key: 'started_at' },
  { title: 'Account', key: 'account' },
  { title: 'Status', key: 'status' },
  { title: 'Importiert', key: 'imported_games' },
  { title: 'Meldung', key: 'message' }
]
const rows = computed(() =>
  store.syncRuns.map((run) => ({
    ...run,
    account: syncRunLabel(run),
    status: !run.finished_at
      ? run.progress_total > 0
        ? `${run.progress_current}/${run.progress_total}`
        : 'Läuft'
      : run.success ? 'OK' : 'Fehler',
    imported_games: run.kind === 'playnite'
      && !run.finished_at
      && ['queued', 'reading'].includes(run.stage)
      ? '–'
      : run.imported_games,
    statusColor: !run.finished_at ? 'primary' : run.success ? 'secondary' : 'error'
  }))
)
const metadataRunning = computed(() =>
  store.syncRuns.some((run) => isMetadataRun(run.kind) && !run.finished_at)
)
let pollTimer: number | undefined

onMounted(async () => {
  await store.refresh()
  schedulePoll()
})

onBeforeUnmount(() => window.clearTimeout(pollTimer))

async function sync(id: number) {
  loading.value = id
  error.value = ''
  try {
    await api.syncAccount(id)
    await store.refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    await store.refresh()
  } finally {
    loading.value = null
  }
}


async function syncMetadata() {
  metadataLoading.value = true
  error.value = ''
  metadataMessage.value = ''
  try {
    const result = await api.syncMetadata()
    metadataMessage.value = `Alle-Metadaten-Lauf #${result.id} wurde gestartet.`
    await refreshRuns()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    metadataLoading.value = false
  }
}

async function repairMetadata() {
  repairLoading.value = true
  error.value = ''
  metadataMessage.value = ''
  try {
    const result = await api.repairMetadata()
    metadataMessage.value = `Prüfung unbekannter Metadaten #${result.id} wurde gestartet.`
    await refreshRuns()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    repairLoading.value = false
  }
}
function accountLabel(id?: number | null) {
  if (!id) return '-'
  const account = store.accounts.find((item) => item.id === id)
  if (!account) return id
  const participant = participantLabel(account.participant_id)
  const providerName = meaningfulAccountName(account.platform, account.display_name)
  return providerName
    ? `${participant} · ${platformLabel(account.platform)}: ${providerName}`
    : `${participant} · ${platformLabel(account.platform)}`
}

function participantLabel(id?: number | null) {
  if (!id) return 'Unbekannt'
  return store.participants.find((participant) => participant.id === id)?.nickname || 'Unbekannt'
}

function syncRunLabel(run: { kind: string; account_id?: number | null; participant_id?: number | null }) {
  if (run.kind === 'metadata') return 'Alle Metadaten'
  if (run.kind === 'metadata_repair') return 'Unbekannte/verdächtige Metadaten'
  if (run.kind === 'game_metadata') return 'Metadaten eines Spiels'
  if (run.kind === 'steam_metadata') return 'Steam-Metadaten vollständig'
  if (run.kind === 'playnite') return `Playnite: ${participantLabel(run.participant_id)}`
  return accountLabel(run.account_id)
}

function isMetadataRun(kind: string) {
  return ['metadata', 'metadata_repair', 'game_metadata', 'steam_metadata'].includes(kind)
}

function platformLabel(platform: string) {
  const labels: Record<string, string> = {
    amazon: 'Amazon Games',
    battle_net: 'Battle.net',
    humble: 'Humble',
    humble_key: 'Humble Key',
    meta: 'Meta / Oculus',
    ubisoft: 'Ubisoft Connect',
    xbox: 'Xbox Live'
  }
  return labels[platform] || platform
}

function meaningfulAccountName(platform: string, displayName: string) {
  const value = (displayName || '').trim()
  if (!value) return ''
  const normalized = value.toLocaleLowerCase('de-DE').replace(/_/g, ' ')
  if (normalized === platform.replace(/_/g, ' ').toLocaleLowerCase('de-DE')) return ''
  if (normalized === platformLabel(platform).toLocaleLowerCase('de-DE')) return ''
  if (normalized.startsWith('playnite ')) return ''
  if (normalized.endsWith(' (teilnehmer)')) return ''
  return value
}

function canSyncAccount(platform: string) {
  return ['steam', 'epic', 'gog', 'xbox', 'ubisoft', 'ea', 'amazon', 'battle_net', 'humble', 'meta'].includes(platform)
}

async function refreshRuns() {
  store.syncRuns = await api.syncRuns()
  schedulePoll()
}

function schedulePoll() {
  window.clearTimeout(pollTimer)
  if (store.syncRuns.some((run) => !run.finished_at)) {
    pollTimer = window.setTimeout(refreshRuns, 2000)
  }
}
</script>



