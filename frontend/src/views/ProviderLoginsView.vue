<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4">{{ adminMode ? 'Accounts & Logins aller Teilnehmer:innen' : 'Meine Accounts & Logins' }}</h1>
        <p class="text-medium-emphasis">
          {{ adminMode ? 'Spielekonten aller Teilnehmer verbinden und aktualisieren.' : 'Verbinde deine Spielekonten und aktualisiere deine Bibliotheken.' }}
        </p>
      </div>
      <v-btn icon="mdi-refresh" variant="text" :loading="loading" aria-label="Aktualisieren" @click="load">
        <v-icon>mdi-refresh</v-icon>
        <v-tooltip activator="parent" location="bottom">Aktualisieren</v-tooltip>
      </v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="message" type="success" variant="tonal" class="mb-4">{{ message }}</v-alert>
    <v-alert type="info" variant="tonal" :icon="false" class="playnite-guide mb-5">
      <div class="font-weight-bold mb-1">Playnite-Import empfohlen</div>
      <p class="mb-2">
        Playnite ist eine lokale Spielebibliothek, die Spiele aus vielen Launchern und von lokal installierten Quellen
        zusammenführt. Wenn du Playnite bereits eingerichtet hast, ist ein Playnite-Backup hier der bevorzugte und
        einfachste Importweg.
      </p>
      <p class="mb-2">
        Besonders für Rockstar Games und weitere unten nicht aufgeführte Plattformen ist Playnite der
        vorgesehene Importweg.
      </p>
      <p class="mb-2">
        Öffne in Playnite das Hauptmenü, wähle <strong>Bibliothek → Bibliothek sichern</strong> und erstelle ein
        ZIP-Backup. Diese ZIP-Datei kannst du unten direkt im Feld <strong>Playnite-Backup</strong> auswählen und
        importieren.
      </p>
      <p class="mb-0">
        Alternativ kannst du die unten aufgeführten Plattformen einzeln verbinden und deren Bibliotheken direkt
        aktualisieren.
      </p>
    </v-alert>
    <v-alert v-if="!loading && slotsByParticipant.length === 0" type="info" variant="tonal">
      Lege zuerst einen Teilnehmer an.
    </v-alert>

    <v-row v-else>
      <v-col v-for="group in slotsByParticipant" :key="group.participant.id" cols="12" :xl="adminMode ? 6 : 12">
        <v-card variant="flat">
          <v-card-title class="participant-title">
            <span>{{ group.participant.nickname }}</span>
            <v-chip size="small" variant="tonal">
              {{ connectedCount(group.slots) }} verbunden
            </v-chip>
          </v-card-title>

          <v-card-text>
            <div class="playnite-import mb-3">
              <v-file-input
                v-model="playniteFiles[group.participant.id]"
                accept="application/json,.json,application/zip,.zip"
                label="Playnite-Backup"
                prepend-icon="mdi-file-upload-outline"
                density="compact"
                hide-details="auto"
              />
              <v-btn
                color="primary"
                variant="tonal"
                prepend-icon="mdi-import"
                :loading="busy === `playnite:${group.participant.id}`"
                :disabled="!selectedPlayniteFile(group.participant.id) || busy === `playnite:${group.participant.id}`"
                @click="importPlaynite(group.participant)"
              >
                Importieren
              </v-btn>
              <div v-if="playniteProgress[group.participant.id]" class="playnite-progress">
                <v-progress-linear
                  :model-value="playniteProgress[group.participant.id].percent"
                  :indeterminate="playniteProgress[group.participant.id].indeterminate"
                  :color="playniteProgress[group.participant.id].phase === 'failed' ? 'error' : 'primary'"
                  height="8"
                />
                <div class="text-caption text-medium-emphasis mt-1">
                  {{ playniteProgress[group.participant.id].message }}
                </div>
              </div>
            </div>

            <ManualOwnershipPicker
              v-if="adminMode"
              :participant="group.participant"
              :accounts="accountsFor(group.participant.id)"
            />

            <div v-for="slot in group.slots" :key="slot.key" class="provider-row">
              <v-icon size="28" color="primary">{{ platformIcon(slot.platform) }}</v-icon>
              <div class="provider-info">
                <div class="d-flex align-center ga-2 flex-wrap">
                  <strong>{{ platformTitle(slot.platform) }}</strong>
                  <v-chip :color="statusColor(slot)" size="small" variant="tonal">
                    {{ statusLabel(slot) }}
                  </v-chip>
                </div>
                <div class="text-caption text-medium-emphasis mt-1">
                  {{ providerDetail(slot) }}
                </div>
                <div v-if="slot.account?.last_error" class="text-caption text-error mt-1">
                  {{ readableError(slot.account.last_error) }}
                </div>
              </div>

              <div class="provider-actions">
                <v-btn
                  v-if="!isConnected(slot)"
                  color="primary"
                  variant="tonal"
                  prepend-icon="mdi-link-plus"
                  @click="openWizard(slot)"
                >
                  Einrichten
                </v-btn>
                <template v-else>
                  <v-btn
                    color="primary"
                    variant="tonal"
                    prepend-icon="mdi-sync"
                    :loading="busy === `sync:${slot.account?.id}`"
                    @click="sync(slot)"
                  >
                    Spiele aktualisieren
                  </v-btn>
                  <v-btn variant="text" prepend-icon="mdi-account-convert-outline" @click="openWizard(slot)">
                    Neu verbinden
                  </v-btn>
                </template>
                <v-btn
                  v-if="slot.account && slot.platform !== 'steam'"
                  icon="mdi-link-off"
                  size="small"
                  variant="text"
                  color="error"
                  :loading="busy === `logout:${slot.account.id}`"
                  aria-label="Verbindung trennen"
                  @click="logout(slot.account)"
                >
                  <v-icon>mdi-link-off</v-icon>
                  <v-tooltip activator="parent" location="bottom">Verbindung trennen</v-tooltip>
                </v-btn>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <ProviderConnectDialog
      v-model="wizardOpen"
      :target="wizardTarget"
      @finished="load"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import ManualOwnershipPicker from '../components/ManualOwnershipPicker.vue'
import ProviderConnectDialog from '../components/ProviderConnectDialog.vue'
import { clearParticipant, currentParticipantId } from '../playerIdentity'
import { stateFromRun, waitForPlayniteImport, type PlayniteProgressState } from '../playniteImport'
import { useLanStore } from '../store'
import type { Account, Participant, Platform, ProviderAuthStatus } from '../types'

interface ProviderSlot {
  key: string
  participant: Participant
  platform: Platform
  account?: Account
}

const props = withDefaults(defineProps<{
  adminMode?: boolean
}>(), {
  adminMode: false
})

const loginPlatforms: Platform[] = [
  'steam',
  'epic',
  'gog',
  'ubisoft',
  'xbox',
  'ea',
  'amazon',
  'battle_net',
  'humble',
  'meta'
]
const router = useRouter()
const store = useLanStore()
const statuses = ref<ProviderAuthStatus[]>([])
const loading = ref(false)
const busy = ref<string | null>(null)
const error = ref('')
const message = ref('')
const playniteFiles = reactive<Record<number, File | File[] | null>>({})
const playniteProgress = reactive<Record<number, PlayniteProgressState>>({})
const wizardOpen = ref(false)
const wizardTarget = ref<ProviderSlot | null>(null)
const adminMode = computed(() => props.adminMode)
const visibleParticipants = computed(() =>
  props.adminMode
    ? store.sortedParticipants
    : store.sortedParticipants.filter((participant) => participant.id === currentParticipantId.value)
)

const slotsByParticipant = computed(() =>
  visibleParticipants.value
    .map((participant) => ({
      participant,
      slots: loginPlatforms.map((platform) => ({
        key: `${participant.id}:${platform}`,
        participant,
        platform,
        account: store.accounts.find(
          (account) => account.participant_id === participant.id && account.platform === platform
        )
      }))
    }))
)

onMounted(load)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const [participants, accounts, providerStatuses] = await Promise.all([
      api.participants(),
      api.accounts(),
      api.providerAuthStatus()
    ])
    store.participants = participants
    store.accounts = accounts
    statuses.value = providerStatuses
    if (!props.adminMode && !participants.some((participant) => participant.id === currentParticipantId.value)) {
      clearParticipant()
      await router.replace({ path: '/player', query: { redirect: '/logins' } })
    }
  } catch (err) {
    error.value = readableError(err)
  } finally {
    loading.value = false
  }
}

function openWizard(slot: ProviderSlot) {
  error.value = ''
  message.value = ''
  wizardTarget.value = slot
  wizardOpen.value = true
}

function statusFor(accountId: number) {
  return statuses.value.find((status) => status.account_id === accountId)
}

function isConnected(slot: ProviderSlot) {
  if (!slot.account) return false
  if (slot.platform === 'steam') return /^\d{17}$/.test(slot.account.account_id)
  return Boolean(statusFor(slot.account.id)?.authenticated)
}

function statusLabel(slot: ProviderSlot) {
  if (isConnected(slot)) return 'Verbunden'
  if (slot.account?.account_id.startsWith('playnite:')) return 'Nur Playnite'
  if (slot.account && statusFor(slot.account.id)?.needs_2fa) return '2FA ausstehend'
  if (slot.account?.last_error) return 'Fehler'
  return 'Nicht verbunden'
}

function statusColor(slot: ProviderSlot) {
  if (isConnected(slot)) return 'success'
  if (slot.account?.last_error) return 'error'
  if (slot.account?.account_id.startsWith('playnite:') || statusFor(slot.account?.id || 0)?.needs_2fa) return 'warning'
  return 'default'
}

function providerDetail(slot: ProviderSlot) {
  if (!slot.account) return 'Noch nicht eingerichtet'
  if (slot.account.last_successful_sync) {
    return `Zuletzt synchronisiert: ${new Intl.DateTimeFormat('de-DE', {
      dateStyle: 'short',
      timeStyle: 'short'
    }).format(new Date(slot.account.last_successful_sync))}`
  }
  return slot.account.display_name || 'Noch nicht synchronisiert'
}

function connectedCount(slots: ProviderSlot[]) {
  return slots.filter(isConnected).length
}

function accountsFor(participantId: number) {
  return store.accounts.filter((account) => account.participant_id === participantId)
}

function selectedPlayniteFile(participantId: number) {
  const value = playniteFiles[participantId]
  return Array.isArray(value) ? value[0] : value
}

async function importPlaynite(participant: Participant) {
  const file = selectedPlayniteFile(participant.id)
  if (!file) return
  busy.value = `playnite:${participant.id}`
  error.value = ''
  message.value = ''
  playniteProgress[participant.id] = {
    phase: 'upload',
    percent: 0,
    indeterminate: false,
    message: 'Playnite-Backup wird hochgeladen: 0 %'
  }
  try {
    const job = await api.importPlaynite(participant.id, file, (percent) => {
      playniteProgress[participant.id] = {
        phase: 'upload',
        percent,
        indeterminate: false,
        message: percent < 100
          ? `Playnite-Backup wird hochgeladen: ${percent} %`
          : 'Upload abgeschlossen. Der Server bereitet den Import vor.'
      }
    })
    playniteProgress[participant.id] = stateFromRun(job)
    const result = await waitForPlayniteImport(job.id, (run) => {
      playniteProgress[participant.id] = stateFromRun(run)
    })
    if (!result.success) throw new Error(result.message)
    message.value = `${participant.nickname}: ${result.message}`
    playniteFiles[participant.id] = null
    await load()
  } catch (err) {
    error.value = readableError(err)
    playniteProgress[participant.id] = {
      phase: 'failed',
      percent: 100,
      indeterminate: false,
      message: error.value
    }
  } finally {
    busy.value = null
  }
}

async function sync(slot: ProviderSlot) {
  if (!slot.account) return
  busy.value = `sync:${slot.account.id}`
  error.value = ''
  message.value = ''
  try {
    const result = await api.syncAccount(slot.account.id)
    if (!result.success) throw new Error(result.message || 'Synchronisation fehlgeschlagen.')
    message.value = `${platformTitle(slot.platform)} für ${slot.participant.nickname}: ${result.imported_games} Spiele aktualisiert.`
    await load()
  } catch (err) {
    error.value = readableError(err)
    await load()
  } finally {
    busy.value = null
  }
}

async function logout(account: Account) {
  busy.value = `logout:${account.id}`
  error.value = ''
  message.value = ''
  try {
    await api.logoutProvider(account.id)
    message.value = 'Verbindung wurde getrennt.'
    await load()
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busy.value = null
  }
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

function platformTitle(platform: Platform) {
  const titles: Record<string, string> = {
    steam: 'Steam',
    epic: 'Epic Games',
    gog: 'GOG',
    ubisoft: 'Ubisoft Connect',
    xbox: 'Xbox Live',
    ea: 'EA App',
    amazon: 'Amazon Games',
    battle_net: 'Battle.net',
    humble: 'Humble',
    meta: 'Meta / Oculus'
  }
  return titles[platform] || platform
}

function platformIcon(platform: Platform) {
  const icons: Record<string, string> = {
    steam: 'mdi-steam',
    epic: 'mdi-gamepad-variant-outline',
    gog: 'mdi-gamepad-square-outline',
    ubisoft: 'mdi-alpha-u-circle-outline',
    xbox: 'mdi-microsoft-xbox',
    ea: 'mdi-alpha-e-circle-outline',
    amazon: 'mdi-amazon',
    battle_net: 'mdi-battle-net',
    humble: 'mdi-alpha-h-circle-outline',
    meta: 'mdi-virtual-reality'
  }
  return icons[platform] || 'mdi-gamepad-variant-outline'
}
</script>

<style scoped>
.participant-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.playnite-guide {
  max-width: 980px;
}

.provider-row {
  display: grid;
  grid-template-columns: 36px minmax(180px, 1fr) auto;
  gap: 12px;
  align-items: center;
  min-height: 76px;
  padding: 10px 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.provider-info {
  min-width: 0;
}

.provider-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

.playnite-import {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding-bottom: 12px;
}

.playnite-progress {
  grid-column: 1 / -1;
}

@media (max-width: 760px) {
  .provider-row {
    grid-template-columns: 32px minmax(0, 1fr);
  }

  .provider-actions {
    grid-column: 1 / -1;
    justify-content: stretch;
  }

  .provider-actions :deep(.v-btn:not(.v-btn--icon)) {
    flex: 1;
  }

  .playnite-import {
    grid-template-columns: 1fr;
  }
}
</style>
