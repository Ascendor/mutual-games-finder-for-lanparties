<template>
  <div class="page usage-page">
    <div class="usage-header mb-5">
      <div>
        <h1 class="text-h4">Nutzungsanalyse</h1>
        <p class="text-medium-emphasis mb-0">Lokale Auswertung der tatsächlichen App-Nutzung.</p>
      </div>
      <div class="date-controls">
        <v-select
          v-model="period"
          :items="periodOptions"
          label="Zeitraum"
          density="compact"
          hide-details
          @update:model-value="changePeriod"
        />
        <template v-if="period === 'custom'">
          <v-text-field v-model="dateFrom" type="date" label="Von" density="compact" hide-details />
          <v-text-field v-model="dateTo" type="date" label="Bis" density="compact" hide-details />
        </template>
        <v-btn variant="tonal" prepend-icon="mdi-calendar-cog" @click="openConfiguration">
          Partyzeiten
        </v-btn>
        <v-btn color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="load">
          Aktualisieren
        </v-btn>
      </div>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <template v-if="summary">
      <v-row class="mb-5">
        <v-col v-for="metric in metrics" :key="metric.label" cols="6" md="3">
          <v-card variant="flat" class="metric-card">
            <div class="text-h4 font-weight-bold">{{ metric.value }}</div>
            <div class="text-body-2 text-medium-emphasis">{{ metric.label }}</div>
          </v-card>
        </v-col>
      </v-row>

      <section class="usage-section">
        <h2 class="text-h6 mb-3">Aktivität nach Tag</h2>
        <v-data-table
          class="compact-table"
          density="compact"
          :headers="dailyHeaders"
          :items="summary.daily"
          :items-per-page="-1"
          hide-default-footer
        >
          <template #item.date="{ item }">{{ formatDay(item.date) }}</template>
        </v-data-table>
      </section>

      <v-row>
        <v-col cols="12" lg="6">
          <section class="usage-section">
            <h2 class="text-h6 mb-3">Meistgesuchte Spiele</h2>
            <v-data-table
              class="compact-table"
              density="compact"
              :headers="gameHeaders"
              :items="summary.top_games"
              :items-per-page="10"
              :no-data-text="'Noch keine Mitspielersuchen im Zeitraum.'"
            />
          </section>
        </v-col>
        <v-col cols="12" lg="6">
          <section class="usage-section">
            <h2 class="text-h6 mb-3">Häufig als Mitspieler:in ausgewählt</h2>
            <v-data-table
              class="compact-table"
              density="compact"
              :headers="selectedPlayerHeaders"
              :items="summary.selected_players"
              :items-per-page="10"
              :no-data-text="'Noch keine Gruppensuchen im Zeitraum.'"
            />
          </section>
        </v-col>
      </v-row>

      <section class="usage-section">
        <h2 class="text-h6 mb-3">Nutzung nach Teilnehmer:in</h2>
        <v-data-table
          class="compact-table"
          density="compact"
          :headers="participantHeaders"
          :items="summary.participants"
          :items-per-page="25"
          no-data-text="Noch keine zugeordneten Ereignisse im Zeitraum."
        >
          <template #item.last_active_at="{ item }">{{ formatDateTime(item.last_active_at) }}</template>
          <template #item.actions="{ item }">
            <v-btn
              size="small"
              variant="text"
              color="primary"
              prepend-icon="mdi-magnify"
              @click="openParticipant(item.participant_id)"
            >
              Details
            </v-btn>
          </template>
        </v-data-table>
      </section>
    </template>

    <v-dialog v-model="detailOpen" max-width="980" scrollable>
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between">
          <span>{{ detail?.nickname || 'Nutzerdetails' }}</span>
          <div class="d-flex align-center ga-1">
            <v-btn
              v-if="detail"
              color="error"
              variant="text"
              size="small"
              prepend-icon="mdi-delete-outline"
              :loading="detailDeleting"
              @click="deleteDetailEvents"
            >
              Nutzungsdaten löschen
            </v-btn>
            <v-btn icon="mdi-close" variant="text" aria-label="Schließen" @click="detailOpen = false" />
          </div>
        </v-card-title>
        <v-card-text>
          <v-progress-linear v-if="detailLoading" indeterminate />
          <template v-else-if="detail">
            <div class="detail-counts mb-5">
              <div><strong>{{ detail.total_events }}</strong><span>Aktionen gesamt</span></div>
              <div><strong>{{ eventCount('find_players_search') }}</strong><span>Mitspielersuchen</span></div>
              <div><strong>{{ eventCount('group_games_search') }}</strong><span>Gruppensuchen</span></div>
              <div><strong>{{ eventCount('page_view') }}</strong><span>Seitenaufrufe</span></div>
            </div>

            <h3 class="text-subtitle-1 font-weight-bold mb-2">Gesuchte Spiele</h3>
            <v-data-table
              class="compact-table mb-5"
              density="compact"
              :headers="gameHeaders"
              :items="detail.top_games"
              :items-per-page="5"
              no-data-text="Keine Mitspielersuchen."
            />

            <h3 class="text-subtitle-1 font-weight-bold mb-2">Letzte Aktivitäten</h3>
            <v-data-table
              class="compact-table"
              density="compact"
              :headers="eventHeaders"
              :items="detail.recent_events"
              :items-per-page="15"
            >
              <template #item.occurred_at="{ item }">{{ formatDateTime(item.occurred_at) }}</template>
              <template #item.event_type="{ item }">{{ eventLabel(item.event_type) }}</template>
              <template #item.details="{ item }">{{ eventDescription(item) }}</template>
            </v-data-table>
          </template>
        </v-card-text>
      </v-card>
    </v-dialog>

    <v-dialog v-model="configurationOpen" max-width="520">
      <v-card>
        <v-card-title>Partyzeitraum festlegen</v-card-title>
        <v-card-text>
          <p class="text-body-2 text-medium-emphasis mb-4">
            Der Beginn trennt Vorbereitung und Party. Das Ende kann offenbleiben, solange die Party läuft.
          </p>
          <v-text-field
            v-model="partyStartInput"
            type="datetime-local"
            label="Partybeginn"
            density="compact"
            class="mb-3"
          />
          <v-text-field
            v-model="partyEndInput"
            type="datetime-local"
            label="Partyende (optional)"
            density="compact"
            clearable
          />
          <v-alert v-if="configurationError" type="error" variant="tonal" density="compact">
            {{ configurationError }}
          </v-alert>
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="configurationOpen = false">Abbrechen</v-btn>
          <v-btn
            color="primary"
            :loading="configurationSaving"
            :disabled="!partyStartInput"
            @click="saveConfiguration"
          >
            Speichern
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import type {
  AnalyticsConfiguration,
  AnalyticsPeriod,
  AnalyticsParticipantDetail,
  AnalyticsSummary,
  UsageEvent,
  UsageEventType
} from '../types'

const today = new Date()
const start = new Date(today)
start.setDate(start.getDate() - 6)
const dateFrom = ref(dateInput(start))
const dateTo = ref(dateInput(today))
const period = ref<AnalyticsPeriod>('custom')
const configuration = ref<AnalyticsConfiguration>({})
const summary = ref<AnalyticsSummary | null>(null)
const detail = ref<AnalyticsParticipantDetail | null>(null)
const loading = ref(false)
const detailLoading = ref(false)
const detailDeleting = ref(false)
const detailOpen = ref(false)
const configurationOpen = ref(false)
const configurationSaving = ref(false)
const configurationError = ref('')
const partyStartInput = ref('')
const partyEndInput = ref('')
const error = ref('')
const periodOptions = [
  { title: 'Auf der Party', value: 'party' },
  { title: 'Vor der Party', value: 'before_party' },
  { title: 'Gesamter Zeitraum', value: 'all' },
  { title: 'Eigener Zeitraum', value: 'custom' }
]

const metrics = computed(() => [
  { label: 'Aktive Teilnehmer:innen', value: summary.value?.active_users || 0 },
  { label: 'Mitspielersuchen', value: summary.value?.find_players_searches || 0 },
  { label: 'Gruppensuchen', value: summary.value?.group_games_searches || 0 },
  { label: 'Seitenaufrufe', value: summary.value?.page_views || 0 }
])

const dailyHeaders = [
  { title: 'Tag', key: 'date' },
  { title: 'Gesamt', key: 'total_events' },
  { title: 'Seiten', key: 'page_views' },
  { title: 'Mitspieler', key: 'find_players_searches' },
  { title: 'Gruppen', key: 'group_games_searches' }
]
const gameHeaders = [
  { title: 'Spiel', key: 'title' },
  { title: 'Suchen', key: 'searches' },
  { title: 'Nutzer:innen', key: 'unique_users' }
]
const selectedPlayerHeaders = [
  { title: 'Teilnehmer:in', key: 'nickname' },
  { title: 'Ausgewählt', key: 'selections' },
  { title: 'Von Nutzer:innen', key: 'unique_searchers' }
]
const participantHeaders = [
  { title: 'Teilnehmer:in', key: 'nickname' },
  { title: 'Gesamt', key: 'total_events' },
  { title: 'Seiten', key: 'page_views' },
  { title: 'Mitspieler', key: 'find_players_searches' },
  { title: 'Gruppen', key: 'group_games_searches' },
  { title: 'Zuletzt aktiv', key: 'last_active_at' },
  { title: '', key: 'actions', sortable: false }
]
const eventHeaders = [
  { title: 'Zeit', key: 'occurred_at' },
  { title: 'Aktion', key: 'event_type' },
  { title: 'Details', key: 'details', sortable: false }
]

onMounted(initialize)

async function initialize() {
  try {
    configuration.value = await api.usageConfiguration()
    const saved = window.localStorage.getItem('lan-usage-period') as AnalyticsPeriod | null
    period.value = saved || (configuration.value.party_start_at ? 'party' : 'custom')
    if (!configuration.value.party_start_at && ['party', 'before_party'].includes(period.value)) {
      period.value = 'custom'
    }
  } catch (err) {
    error.value = readableError(err)
  }
  await load()
}

function changePeriod(value: AnalyticsPeriod) {
  window.localStorage.setItem('lan-usage-period', value)
  void load()
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    summary.value = await api.usageSummary(period.value, dateFrom.value, dateTo.value)
  } catch (err) {
    error.value = readableError(err)
  } finally {
    loading.value = false
  }
}

async function openParticipant(participantId: number) {
  detailOpen.value = true
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await api.usageParticipant(
      participantId,
      period.value,
      dateFrom.value,
      dateTo.value
    )
  } catch (err) {
    error.value = readableError(err)
    detailOpen.value = false
  } finally {
    detailLoading.value = false
  }
}

async function deleteDetailEvents() {
  if (!detail.value) return
  if (!window.confirm(`Alle Nutzungsereignisse von ${detail.value.nickname} wirklich löschen?`)) return
  detailDeleting.value = true
  try {
    await api.deleteParticipantUsage(detail.value.participant_id)
    detailOpen.value = false
    detail.value = null
    await load()
  } catch (err) {
    error.value = readableError(err)
  } finally {
    detailDeleting.value = false
  }
}

function openConfiguration() {
  configurationError.value = ''
  partyStartInput.value = dateTimeInput(configuration.value.party_start_at)
  partyEndInput.value = dateTimeInput(configuration.value.party_end_at)
  configurationOpen.value = true
}

async function saveConfiguration() {
  if (!partyStartInput.value) return
  configurationSaving.value = true
  configurationError.value = ''
  try {
    const partyStart = new Date(partyStartInput.value)
    const partyEnd = partyEndInput.value ? new Date(partyEndInput.value) : null
    if (partyEnd && partyEnd <= partyStart) {
      configurationError.value = 'Das Partyende muss nach dem Partybeginn liegen.'
      return
    }
    configuration.value = await api.updateUsageConfiguration({
      party_start_at: partyStart.toISOString(),
      party_end_at: partyEnd?.toISOString() || null
    })
    configurationOpen.value = false
    period.value = 'party'
    window.localStorage.setItem('lan-usage-period', period.value)
    await load()
  } catch (err) {
    configurationError.value = readableError(err)
  } finally {
    configurationSaving.value = false
  }
}

function eventCount(type: UsageEventType) {
  return detail.value?.event_counts.find((item) => item.key === type)?.count || 0
}

function eventLabel(type: UsageEventType) {
  const labels: Record<UsageEventType, string> = {
    page_view: 'Seitenaufruf',
    find_players_search: 'Mitspieler gesucht',
    group_games_search: 'Gemeinsames Spiel gesucht'
  }
  return labels[type]
}

function eventDescription(event: UsageEvent) {
  if (event.event_type === 'page_view') return String(event.details.path || '')
  if (event.event_type === 'find_players_search') {
    return `${event.details.game_title || 'Spiel'} · ${event.details.result_count ?? 0} Treffer`
  }
  const players = Array.isArray(event.details.selected_players)
    ? event.details.selected_players
        .filter((item): item is { nickname?: string } => Boolean(item) && typeof item === 'object')
        .map((item) => item.nickname)
        .filter(Boolean)
        .join(', ')
    : ''
  return players || `${event.details.group_size || 0} Spieler:innen`
}

function formatDay(value: string) {
  return new Intl.DateTimeFormat('de-DE', { weekday: 'short', dateStyle: 'medium' })
    .format(new Date(`${value}T12:00:00`))
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat('de-DE', {
    dateStyle: 'short',
    timeStyle: 'short'
  }).format(new Date(`${value}Z`))
}

function dateInput(value: Date) {
  const year = value.getFullYear()
  const month = String(value.getMonth() + 1).padStart(2, '0')
  const day = String(value.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function dateTimeInput(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hours = String(date.getHours()).padStart(2, '0')
  const minutes = String(date.getMinutes()).padStart(2, '0')
  return `${year}-${month}-${day}T${hours}:${minutes}`
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
.usage-header {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 20px;
}

.date-controls {
  display: grid;
  grid-template-columns: minmax(170px, 1fr) repeat(2, minmax(145px, auto)) auto auto;
  gap: 10px;
  align-items: center;
}

.metric-card {
  min-height: 104px;
  padding: 16px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.usage-section {
  margin-bottom: 28px;
}

.detail-counts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.detail-counts > div {
  display: flex;
  flex-direction: column;
  padding: 12px;
  border-left: 3px solid rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-surface-variant), 0.35);
}

.detail-counts strong {
  font-size: 1.35rem;
}

.detail-counts span {
  font-size: 0.8rem;
  color: rgba(var(--v-theme-on-surface), 0.7);
}

@media (max-width: 760px) {
  .usage-header {
    align-items: stretch;
    flex-direction: column;
  }

  .date-controls {
    grid-template-columns: 1fr 1fr;
  }

  .date-controls .v-btn {
    grid-column: 1 / -1;
  }

  .detail-counts {
    grid-template-columns: 1fr 1fr;
  }
}
</style>
