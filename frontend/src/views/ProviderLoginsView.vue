<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4">Provider-Logins</h1>
        <p class="text-medium-emphasis">Provider-Accounts werden hier direkt pro Teilnehmer angelegt und verbunden.</p>
      </div>
      <v-btn color="primary" prepend-icon="mdi-refresh" :loading="loading || store.loading" @click="load">Aktualisieren</v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="message" type="success" variant="tonal" class="mb-4">{{ message }}</v-alert>

    <v-alert v-if="store.participants.length === 0" type="info" variant="tonal">
      Lege zuerst Teilnehmer an. Danach kannst du hier pro Teilnehmer die Provider verbinden.
    </v-alert>

    <v-row v-else>
      <v-col v-for="group in slotsByParticipant" :key="group.participant.id" cols="12" xl="6">
        <v-card variant="flat">
          <v-card-title class="d-flex align-center justify-space-between">
            <span>{{ group.participant.nickname }}</span>
            <v-chip size="small" variant="tonal">{{ connectedCount(group.slots) }} / {{ group.slots.length }} verbunden</v-chip>
          </v-card-title>
          <v-card-text>
            <div v-for="slot in group.slots" :key="slot.key" class="provider-row">
              <div class="provider-main">
                <div class="d-flex align-center ga-2 flex-wrap">
                  <strong>{{ platformTitle(slot.platform) }}</strong>
                  <v-chip :color="statusColor(slot.account)" size="small">{{ statusLabel(slot.account) }}</v-chip>
                </div>
                <p class="text-caption text-medium-emphasis mt-1 mb-0">{{ slot.account ? (slot.account.display_name || slot.account.account_id) : helpText(slot.platform) }}</p>
                <p v-if="slot.account" class="text-caption text-medium-emphasis mt-1 mb-0">{{ statusFor(slot.account.id)?.message }}</p>
              </div>

              <div class="provider-actions">
                <div v-if="!slot.account" class="d-flex flex-column ga-2">
                  <template v-if="slot.platform === 'steam'">
                    <v-text-field v-model="accountInputs[slot.key].accountId" label="SteamID64" density="compact" hide-details="auto" />
                    <v-text-field v-model="accountInputs[slot.key].displayName" label="Anzeigename optional" density="compact" hide-details="auto" />
                  </template>
                  <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" :loading="busy === `create:${slot.key}`" @click="createProviderAccount(slot)">
                    Anlegen
                  </v-btn>
                </div>

                <template v-else-if="slot.platform === 'steam'">
                  <div class="d-flex flex-wrap ga-2 justify-end">
                    <v-btn color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="busy === `${slot.account.id}:sync`" @click="sync(slot.account.id)">
                      Synchronisieren
                    </v-btn>
                  </div>
                </template>

                <template v-else>
                  <v-expand-transition>
                    <div v-if="loginStarts[slot.account.id]" class="login-fields">
                      <div v-if="slot.platform === 'ubisoft'" class="d-flex flex-column ga-2">
                        <v-text-field v-model="ubisoftForms[slot.account.id].email" label="E-Mail" density="compact" hide-details="auto" autocomplete="username" />
                        <v-text-field v-model="ubisoftForms[slot.account.id].password" label="Passwort" type="password" density="compact" hide-details="auto" autocomplete="current-password" />
                        <v-text-field v-if="statusFor(slot.account.id)?.needs_2fa || ubisoftForms[slot.account.id].needs2fa" v-model="ubisoftForms[slot.account.id].twoFactorCode" label="2FA-Code" density="compact" hide-details="auto" />
                      </div>
                      <div v-else-if="slot.platform === 'ea'" class="d-flex flex-column ga-2">
                        <v-alert type="warning" variant="tonal" density="compact">
                          EA hat hier noch keinen normalen Login. Wenn kein Authorization-Bearer sichtbar ist, kannst du den Cookie-Header aus einem eingeloggten ea.com-Request versuchen. Cookie wie ein Passwort behandeln.
                        </v-alert>
                        <v-textarea v-model="eaForms[slot.account.id].accessToken" label="access_token" density="compact" hide-details="auto" rows="3" auto-grow />
                        <v-textarea v-model="eaForms[slot.account.id].cookie" label="Cookie-Header alternativ" density="compact" hide-details="auto" rows="3" auto-grow />
                        <v-text-field v-model="eaForms[slot.account.id].pid" label="pid / user_id optional" density="compact" hide-details="auto" />
                      </div>
                      <div v-else-if="slot.platform === 'gog'" class="d-flex flex-column ga-2">
                        <v-alert type="info" variant="tonal" density="compact">
                          Nach dem GOG-Login landest du auf der GOG-Erfolgsseite. Kopiere die komplette URL aus der Adresszeile hier hinein; die App liest den code automatisch aus.
                        </v-alert>
                        <v-btn :href="loginStarts[slot.account.id]?.login_url" target="_blank" color="primary" prepend-icon="mdi-open-in-new">
                          GOG Login öffnen
                        </v-btn>
                        <v-textarea v-model="codes[slot.account.id]" label="Komplette Redirect-URL oder code" density="compact" hide-details="auto" rows="2" auto-grow />
                      </div>
                      <div v-else>
                        <v-btn :href="loginStarts[slot.account.id]?.login_url" target="_blank" color="primary" prepend-icon="mdi-open-in-new" class="mb-3">
                          Login öffnen
                        </v-btn>
                        <v-textarea v-model="codes[slot.account.id]" :label="loginStarts[slot.account.id]?.code_label || 'Code'" density="compact" hide-details="auto" rows="3" auto-grow />
                      </div>
                    </div>
                  </v-expand-transition>

                  <div class="d-flex flex-wrap ga-2 justify-end">
                    <v-btn color="primary" variant="tonal" prepend-icon="mdi-key-plus" :loading="busy === slot.account.id" @click="start(slot.account.id)">
                      Verbinden
                    </v-btn>
                    <v-btn color="secondary" prepend-icon="mdi-check" :disabled="!canComplete(slot.account)" :loading="busy === `${slot.account.id}:complete`" @click="complete(slot.account)">
                      {{ slot.platform === 'ubisoft' && (statusFor(slot.account.id)?.needs_2fa || ubisoftForms[slot.account.id]?.needs2fa) ? '2FA bestätigen' : 'Bestätigen' }}
                    </v-btn>
                    <v-btn color="primary" variant="text" prepend-icon="mdi-sync" :loading="busy === `${slot.account.id}:sync`" @click="sync(slot.account.id)">
                      Synchronisieren
                    </v-btn>
                    <v-btn variant="text" color="error" prepend-icon="mdi-link-off" :loading="busy === `${slot.account.id}:logout`" @click="logout(slot.account.id)">
                      Trennen
                    </v-btn>
                  </div>
                </template>
              </div>
            </div>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { useLanStore } from '../store'
import type { Account, Participant, Platform, ProviderAuthStatus, ProviderLoginStart } from '../types'

interface UbisoftForm {
  email: string
  password: string
  twoFactorCode: string
  needs2fa: boolean
}

interface EAForm {
  accessToken: string
  cookie: string
  pid: string
}

interface ProviderSlot {
  key: string
  participant: Participant
  platform: Platform
  account?: Account
}

const loginPlatforms: Platform[] = ['steam', 'epic', 'gog', 'ubisoft', 'xbox', 'ea']
const route = useRoute()
const store = useLanStore()
const statuses = ref<ProviderAuthStatus[]>([])
const loginStarts = reactive<Record<number, ProviderLoginStart | undefined>>({})
const codes = reactive<Record<number, string | undefined>>({})
const ubisoftForms = reactive<Record<number, UbisoftForm>>({})
const eaForms = reactive<Record<number, EAForm>>({})
const accountInputs = reactive<Record<string, { accountId: string; displayName: string }>>({})
const loading = ref(false)
const busy = ref<string | number | null>(null)
const error = ref('')
const message = ref('')

const slotsByParticipant = computed(() =>
  [...store.participants].sort((left, right) => {
    const focused = Number(route.query.participant)
    if (!focused) return left.nickname.localeCompare(right.nickname)
    if (left.id === focused) return -1
    if (right.id === focused) return 1
    return left.nickname.localeCompare(right.nickname)
  }).map((participant) => ({
    participant,
    slots: loginPlatforms.map((platform) => {
      const key = `${participant.id}:${platform}`
      ensureAccountInput(key)
      return {
        key,
        participant,
        platform,
        account: accountFor(participant.id, platform)
      }
    })
  }))
)

onMounted(load)

function accountFor(participantId: number, platform: Platform) {
  return store.accounts.find((account) => account.participant_id === participantId && account.platform === platform)
}

function ensureAccountInput(key: string) {
  if (!accountInputs[key]) {
    accountInputs[key] = { accountId: '', displayName: '' }
  }
  return accountInputs[key]
}

function ensureUbisoftForm(accountId: number) {
  if (!ubisoftForms[accountId]) {
    ubisoftForms[accountId] = { email: '', password: '', twoFactorCode: '', needs2fa: false }
  }
  return ubisoftForms[accountId]
}

function ensureEAForm(accountId: number) {
  if (!eaForms[accountId]) {
    eaForms[accountId] = { accessToken: '', cookie: '', pid: '' }
  }
  return eaForms[accountId]
}

function statusFor(accountId: number) {
  return statuses.value.find((status) => status.account_id === accountId)
}

function statusColor(account?: Account) {
  if (!account) return 'grey'
  if (account.platform === 'steam') return account.account_id ? 'secondary' : 'warning'
  const status = statusFor(account.id)
  if (status?.authenticated) return 'secondary'
  if (status?.needs_2fa) return 'warning'
  return 'error'
}

function statusLabel(account?: Account) {
  if (!account) return 'Nicht angelegt'
  if (account.platform === 'steam') return account.account_id ? 'Steam-ID hinterlegt' : 'Steam-ID fehlt'
  const status = statusFor(account.id)
  if (status?.authenticated) return 'Verbunden'
  if (status?.needs_2fa) return '2FA nötig'
  return 'Nicht verbunden'
}

function connectedCount(slots: ProviderSlot[]) {
  return slots.filter((slot) => slot.account && statusFor(slot.account.id)?.authenticated).length
}

function platformTitle(platform: Platform) {
  const titles: Record<Platform, string> = { steam: 'Steam', epic: 'Epic Games', gog: 'GOG', xbox: 'Xbox Live', ubisoft: 'Ubisoft Connect', ea: 'EA App' }
  return titles[platform]
}

function helpText(platform: Platform) {
  if (platform === 'steam') return 'SteamID64 fuer diesen Teilnehmer eintragen.'
  if (platform === 'epic') return 'Epic-Account fuer diesen Teilnehmer anlegen und danach verbinden.'
  if (platform === 'gog') return 'GOG-Account fuer diesen Teilnehmer anlegen und danach verbinden.'
  if (platform === 'ubisoft') return 'Ubisoft-Account fuer diesen Teilnehmer anlegen und danach mit E-Mail, Passwort und ggf. 2FA verbinden.'
  if (platform === 'xbox') return 'Xbox-Account fuer diesen Teilnehmer anlegen; XSTS-Daten werden beim Verbinden eingetragen.'
  if (platform === 'ea') return 'EA-Account fuer diesen Teilnehmer anlegen; EA App/Web-Token wird beim Verbinden eingetragen.'
  return ''
}

function canComplete(account: Account) {
  if (!loginStarts[account.id]) return false
  if (account.platform === 'ubisoft') {
    const form = ensureUbisoftForm(account.id)
    const needs2fa = statusFor(account.id)?.needs_2fa || form.needs2fa
    return Boolean(form.email && form.password && (!needs2fa || form.twoFactorCode))
  }
  if (account.platform === 'ea') {
    const form = ensureEAForm(account.id)
    return Boolean(form.accessToken.trim() || form.cookie.trim())
  }
  return Boolean(codes[account.id]?.trim())
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    await store.refresh()
    statuses.value = await api.providerAuthStatus()
    for (const account of store.accounts.filter((item) => item.platform === 'ubisoft')) {
      ensureUbisoftForm(account.id).needs2fa = Boolean(statusFor(account.id)?.needs_2fa)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}

async function createProviderAccount(slot: ProviderSlot) {
  busy.value = `create:${slot.key}`
  error.value = ''
  message.value = ''
  try {
    const input = ensureAccountInput(slot.key)
    if (slot.platform === 'steam' && !input.accountId.trim()) {
      error.value = 'Bitte SteamID64 eintragen.'
      return
    }
    await api.createAccount({
      participant_id: slot.participant.id,
      platform: slot.platform,
      account_id: slot.platform === 'steam' ? input.accountId.trim() : '',
      display_name: input.displayName.trim() || platformTitle(slot.platform)
    })
    message.value = `${platformTitle(slot.platform)} fuer ${slot.participant.nickname} angelegt.`
    input.accountId = ''
    input.displayName = ''
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function start(accountId: number) {
  busy.value = accountId
  error.value = ''
  message.value = ''
  try {
    loginStarts[accountId] = await api.startProviderLogin(accountId)
    const account = store.accounts.find((item) => item.id === accountId)
    if (account?.platform === 'ubisoft') ensureUbisoftForm(accountId)
    if (account?.platform === 'ea') ensureEAForm(accountId)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function complete(account: Account) {
  busy.value = `${account.id}:complete`
  error.value = ''
  message.value = ''
  try {
    const result = account.platform === 'ubisoft'
      ? await completeUbisoft(account.id)
      : account.platform === 'ea'
        ? await completeEA(account.id)
        : await api.completeProviderLogin(account.id, { code: codes[account.id]?.trim() || '' })
    message.value = result.message
    if (result.needs_2fa) {
      ensureUbisoftForm(account.id).needs2fa = true
      await load()
      return
    }
    codes[account.id] = ''
    delete loginStarts[account.id]
    if (account.platform === 'ubisoft') ensureUbisoftForm(account.id).twoFactorCode = ''
    if (account.platform === 'ea') Object.assign(ensureEAForm(account.id), { accessToken: '', cookie: '', pid: '' })
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
    await load()
  } finally {
    busy.value = null
  }
}

function completeUbisoft(accountId: number) {
  const form = ensureUbisoftForm(accountId)
  return api.completeProviderLogin(accountId, {
    email: form.email,
    password: form.password,
    two_factor_code: form.twoFactorCode || undefined
  })
}

function completeEA(accountId: number) {
  const form = ensureEAForm(accountId)
  return api.completeProviderLogin(accountId, {
    access_token: form.accessToken.trim(),
    cookie: form.cookie.trim() || undefined,
    pid: form.pid.trim() || undefined
  })
}

async function sync(accountId: number) {
  busy.value = `${accountId}:sync`
  error.value = ''
  message.value = ''
  try {
    await api.syncAccount(accountId)
    message.value = 'Synchronisation abgeschlossen.'
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function logout(accountId: number) {
  busy.value = `${accountId}:logout`
  error.value = ''
  message.value = ''
  try {
    const result = await api.logoutProvider(accountId)
    message.value = result.message
    delete loginStarts[accountId]
    if (ubisoftForms[accountId]) ubisoftForms[accountId] = { email: '', password: '', twoFactorCode: '', needs2fa: false }
    if (eaForms[accountId]) eaForms[accountId] = { accessToken: '', cookie: '', pid: '' }
    await load()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}
</script>

<style scoped>
.provider-row {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) minmax(320px, 1.4fr);
  gap: 16px;
  align-items: start;
  padding: 14px 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.provider-row:first-child {
  border-top: 0;
  padding-top: 0;
}

.provider-main {
  min-width: 0;
}

.provider-actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: stretch;
}

.login-fields {
  width: 100%;
}

@media (max-width: 760px) {
  .provider-row {
    grid-template-columns: 1fr;
  }
}
</style>



