<template>
  <div class="page orga-dashboard-page">
    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4">Orga-Dashboard</h1>
        <p class="text-medium-emphasis">
          Aktuelle Nutzung, Datenqualität und Synchronisationszustand für das LAN-Wochenende.
        </p>
      </div>
      <v-btn color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="load">Aktualisieren</v-btn>
    </div>

    <v-row>
      <v-col v-for="metric in metrics" :key="metric.label" cols="12" sm="6" lg="3">
        <v-card variant="flat" class="metric-card">
          <v-card-text>
            <div class="metric-value">{{ metric.value }}</div>
            <div class="metric-label">{{ metric.label }}</div>
            <div class="metric-hint">{{ metric.hint }}</div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-row class="mt-2">
      <v-col cols="12" lg="7">
        <v-card variant="flat">
          <v-card-title class="d-flex align-center justify-space-between">
            <span>Suchtrends heute</span>
            <v-btn to="/admin/nutzung" size="small" variant="text" prepend-icon="mdi-chart-box-outline">Analyse</v-btn>
          </v-card-title>
          <v-card-text>
            <v-data-table
              :headers="topGameHeaders"
              :items="todaySummary?.top_games ?? []"
              :items-per-page="8"
              :loading="loading"
              density="compact"
            >
              <template #no-data>
                <div class="pa-4 text-medium-emphasis">Heute wurden noch keine Spiele gesucht.</div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="5">
        <v-card variant="flat">
          <v-card-title>Heute häufig ausgewählt</v-card-title>
          <v-card-text>
            <v-data-table
              :headers="selectedPlayerHeaders"
              :items="todaySummary?.selected_players ?? []"
              :items-per-page="8"
              :loading="loading"
              density="compact"
            >
              <template #no-data>
                <div class="pa-4 text-medium-emphasis">Heute wurden noch keine Mitspieler:innen ausgewählt.</div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="6">
        <v-card variant="flat">
          <v-card-title class="d-flex align-center justify-space-between">
            <span>Datenqualität der Anwesenden</span>
            <v-btn to="/admin/logins" size="small" variant="text" prepend-icon="mdi-key-chain-variant">Accounts</v-btn>
          </v-card-title>
          <v-card-text>
            <div v-for="row in qualityRows" :key="row.label" class="quality-row">
              <div class="quality-row__header">
                <span>{{ row.label }}</span>
                <strong>{{ row.value }} / {{ row.total }}</strong>
              </div>
              <v-progress-linear :model-value="row.percent" height="8" rounded :color="row.color" />
              <div class="quality-row__hint">{{ row.hint }}</div>
            </div>

            <v-divider class="my-4" />

            <v-data-table
              :headers="participantIssueHeaders"
              :items="participantIssueRows"
              :items-per-page="6"
              :loading="loading"
              density="compact"
            >
              <template #no-data>
                <div class="pa-4 text-medium-emphasis">Keine offenen Punkte bei anwesenden Spieler:innen.</div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" lg="6">
        <v-card variant="flat">
          <v-card-title class="d-flex align-center justify-space-between">
            <span>Sync-Probleme</span>
            <v-btn to="/admin/sync" size="small" variant="text" prepend-icon="mdi-sync">Protokoll</v-btn>
          </v-card-title>
          <v-card-text>
            <v-data-table
              :headers="syncProblemHeaders"
              :items="syncProblemRows"
              :items-per-page="8"
              :loading="loading"
              density="compact"
            >
              <template #item.message="{ item }">
                <span class="clamped-message">{{ item.message }}</span>
              </template>
              <template #no-data>
                <div class="pa-4 text-medium-emphasis">Keine aktuellen Sync-Fehler gefunden.</div>
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12">
        <v-card variant="flat">
          <v-card-title>Provider-Status</v-card-title>
          <v-card-text>
            <v-data-table
              :headers="providerHeaders"
              :items="providerRows"
              :items-per-page="-1"
              :loading="loading"
              density="compact"
              hide-default-footer
            >
              <template #item.last_sync="{ item }">
                {{ item.last_sync ? formatDateTime(item.last_sync) : '-' }}
              </template>
            </v-data-table>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { platformTitle } from '../platforms'
import type { Account, AnalyticsSummary, Participant, SyncRun } from '../types'

interface QualityRow {
  label: string
  value: number
  total: number
  percent: number
  color: string
  hint: string
}

interface ParticipantIssueRow {
  nickname: string
  issue: string
  detail: string
}

interface SyncProblemRow {
  time: string
  account: string
  status: string
  message: string
}

interface ProviderRow {
  platform: string
  total: number
  synced: number
  failed: number
  pending: number
  last_sync?: string | null
}

const loading = ref(false)
const error = ref('')
const participants = ref<Participant[]>([])
const accounts = ref<Account[]>([])
const syncRuns = ref<SyncRun[]>([])
const todaySummary = ref<AnalyticsSummary | null>(null)

const topGameHeaders = [
  { title: 'Spiel', key: 'title' },
  { title: 'Suchen', key: 'searches' },
  { title: 'Nutzer:innen', key: 'unique_users' }
]
const selectedPlayerHeaders = [
  { title: 'Spieler:in', key: 'nickname' },
  { title: 'Auswahlen', key: 'selections' },
  { title: 'Suchende', key: 'unique_searchers' }
]
const participantIssueHeaders = [
  { title: 'Spieler:in', key: 'nickname' },
  { title: 'Punkt', key: 'issue' },
  { title: 'Details', key: 'detail' }
]
const syncProblemHeaders = [
  { title: 'Zeit', key: 'time' },
  { title: 'Account', key: 'account' },
  { title: 'Status', key: 'status' },
  { title: 'Meldung', key: 'message', sortable: false }
]
const providerHeaders = [
  { title: 'Provider', key: 'platform' },
  { title: 'Accounts', key: 'total' },
  { title: 'Synchronisiert', key: 'synced' },
  { title: 'Fehler', key: 'failed' },
  { title: 'Offen', key: 'pending' },
  { title: 'Letzter Sync', key: 'last_sync' }
]

const presentParticipants = computed(() => participants.value.filter((participant) => participant.present))
const presentWithAccounts = computed(() =>
  presentParticipants.value.filter((participant) => accountsFor(participant.id).length > 0)
)
const presentWithSuccessfulSync = computed(() =>
  presentParticipants.value.filter((participant) =>
    accountsFor(participant.id).some((account) => Boolean(account.last_successful_sync))
  )
)
const presentWithErrors = computed(() =>
  presentParticipants.value.filter((participant) => accountsFor(participant.id).some((account) => Boolean(account.last_error)))
)
const searchesToday = computed(() =>
  (todaySummary.value?.find_players_searches ?? 0) + (todaySummary.value?.group_games_searches ?? 0)
)

const metrics = computed(() => [
  {
    label: 'Anwesend',
    value: presentParticipants.value.length,
    hint: `${participants.value.length} Teilnehmer:innen insgesamt`
  },
  {
    label: 'Suchanfragen heute',
    value: searchesToday.value,
    hint: `${todaySummary.value?.page_views ?? 0} Seitenaufrufe`
  },
  {
    label: 'Aktive Nutzer:innen heute',
    value: todaySummary.value?.active_users ?? 0,
    hint: 'mit protokollierter Nutzung'
  },
  {
    label: 'Mit Sync-Daten',
    value: presentWithSuccessfulSync.value.length,
    hint: `von ${presentParticipants.value.length} Anwesenden`
  }
])

const qualityRows = computed<QualityRow[]>(() => {
  const total = presentParticipants.value.length
  return [
    {
      label: 'Account vorhanden',
      value: presentWithAccounts.value.length,
      total,
      percent: percent(presentWithAccounts.value.length, total),
      color: 'primary',
      hint: 'Mindestens eine direkte Anbindung, Playnite-Quelle oder manuelle Bestätigung.'
    },
    {
      label: 'Erfolgreich synchronisiert',
      value: presentWithSuccessfulSync.value.length,
      total,
      percent: percent(presentWithSuccessfulSync.value.length, total),
      color: 'success',
      hint: 'Mindestens ein Account hat bereits Daten geliefert.'
    },
    {
      label: 'Ohne aktuellen Account-Fehler',
      value: Math.max(0, total - presentWithErrors.value.length),
      total,
      percent: percent(Math.max(0, total - presentWithErrors.value.length), total),
      color: presentWithErrors.value.length ? 'warning' : 'success',
      hint: 'Spieler:innen mit Providerfehlern können gemeinsame Listen verzerren.'
    }
  ]
})

const participantIssueRows = computed<ParticipantIssueRow[]>(() =>
  presentParticipants.value.flatMap((participant) => {
    const rows = accountsFor(participant.id)
    if (!rows.length) {
      return [{ nickname: participant.nickname, issue: 'Keine Accounts', detail: 'Noch keine Bibliothek angebunden.' }]
    }
    const hasSuccess = rows.some((account) => Boolean(account.last_successful_sync))
    const failed = rows.filter((account) => Boolean(account.last_error))
    const issues: ParticipantIssueRow[] = []
    if (!hasSuccess) {
      issues.push({
        nickname: participant.nickname,
        issue: 'Kein erfolgreicher Sync',
        detail: `${rows.length} Account(s), aber noch keine erfolgreichen Daten.`
      })
    }
    failed.slice(0, 2).forEach((account) => {
      issues.push({
        nickname: participant.nickname,
        issue: `${platformTitle(account.platform)} Fehler`,
        detail: account.last_error ?? ''
      })
    })
    return issues
  })
)

const syncProblemRows = computed<SyncProblemRow[]>(() => {
  const failedAccounts = accounts.value
    .filter((account) => Boolean(account.last_error))
    .map((account) => ({
      time: account.last_successful_sync ? `nach ${formatDateTime(account.last_successful_sync)}` : '-',
      account: accountLabel(account),
      status: 'Account-Fehler',
      message: account.last_error ?? ''
    }))

  const failedRuns = syncRuns.value
    .filter((run) => run.finished_at && !run.success)
    .slice(0, 12)
    .map((run) => ({
      time: formatDateTime(run.finished_at ?? run.started_at),
      account: run.account_id ? accountLabelById(run.account_id) : run.kind,
      status: run.kind,
      message: run.message
    }))

  return [...failedAccounts, ...failedRuns].slice(0, 12)
})

const providerRows = computed<ProviderRow[]>(() => {
  const grouped = new Map<string, Account[]>()
  accounts.value.forEach((account) => {
    grouped.set(account.platform, [...(grouped.get(account.platform) ?? []), account])
  })

  return Array.from(grouped.entries())
    .map(([platform, rows]) => ({
      platform: platformTitle(platform),
      total: rows.length,
      synced: rows.filter((account) => Boolean(account.last_successful_sync)).length,
      failed: rows.filter((account) => Boolean(account.last_error)).length,
      pending: rows.filter((account) => !account.last_successful_sync && !account.last_error).length,
      last_sync: latestSync(rows)
    }))
    .sort((a, b) => a.platform.localeCompare(b.platform, 'de', { sensitivity: 'base' }))
})

onMounted(() => {
  void load()
})

async function load() {
  loading.value = true
  error.value = ''
  try {
    const today = localDateInput(new Date())
    const [loadedParticipants, loadedAccounts, loadedSyncRuns, loadedTodaySummary] = await Promise.all([
      api.participants(),
      api.accounts(),
      api.syncRuns(),
      api.usageSummary('custom', today, today)
    ])
    participants.value = loadedParticipants
    accounts.value = loadedAccounts
    syncRuns.value = loadedSyncRuns
    todaySummary.value = loadedTodaySummary
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

function accountsFor(participantId: number) {
  return accounts.value.filter((account) => account.participant_id === participantId)
}

function accountLabel(account: Account) {
  const participant = participants.value.find((item) => item.id === account.participant_id)
  return `${platformTitle(account.platform)}: ${account.display_name || account.account_id || participant?.nickname || 'Account'}`
}

function accountLabelById(accountId: number) {
  const account = accounts.value.find((item) => item.id === accountId)
  return account ? accountLabel(account) : `Account ${accountId}`
}

function latestSync(rows: Account[]) {
  return rows
    .map((account) => account.last_successful_sync)
    .filter((value): value is string => Boolean(value))
    .sort((a, b) => Date.parse(b) - Date.parse(a))[0] ?? null
}

function percent(value: number, total: number) {
  if (!total) return 0
  return Math.round((value / total) * 100)
}

function localDateInput(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function formatDateTime(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}
</script>

<style scoped>
.metric-card {
  height: 100%;
}

.metric-value {
  font-size: 2rem;
  font-weight: 700;
  line-height: 1.1;
}

.metric-label {
  margin-top: 4px;
  font-weight: 600;
}

.metric-hint,
.quality-row__hint {
  color: rgba(var(--v-theme-on-surface), 0.68);
  font-size: 0.82rem;
}

.quality-row + .quality-row {
  margin-top: 16px;
}

.quality-row__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 6px;
}

.clamped-message {
  display: -webkit-box;
  overflow: hidden;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}
</style>
