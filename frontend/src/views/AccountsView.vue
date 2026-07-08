<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-4">
      <div>
        <h1 class="text-h4">Accounts</h1>
        <p class="text-medium-emphasis">Teilnehmer einmalig mit Steam, Epic oder GOG verbinden und danach synchronisieren.</p>
      </div>
      <v-btn to="/admin/sync" color="primary" variant="tonal" prepend-icon="mdi-sync">Zur Synchronisation</v-btn>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="message" type="success" variant="tonal" class="mb-4">{{ message }}</v-alert>

    <v-row>
      <v-col cols="12" md="4">
        <v-card variant="flat">
          <v-card-title>Bibliothek verbinden</v-card-title>
          <v-card-text>
            <v-select v-model="form.participant_id" :items="store.sortedParticipants" item-title="nickname" item-value="id" label="Teilnehmer" density="compact" />
            <v-select v-model="form.platform" :items="platforms" label="Plattform" density="compact" />

            <template v-if="form.platform === 'steam'">
              <v-text-field v-model="form.account_id" label="SteamID64" density="compact" />
              <v-text-field v-model="form.display_name" label="Anzeigename" density="compact" />
              <v-btn color="primary" prepend-icon="mdi-link-plus" :loading="busy === 'create'" @click="create">Speichern</v-btn>
            </template>

            <template v-else-if="form.platform === 'epic' || form.platform === 'gog'">
              <v-text-field v-model="form.display_name" label="Anzeigename optional" density="compact" />
              <v-alert type="info" variant="tonal" density="compact" class="mb-4">
                Fuer {{ platformTitle(form.platform) }} musst du keine Account-ID kennen. Der Login erzeugt den lokalen Account automatisch.
              </v-alert>
              <v-btn color="primary" prepend-icon="mdi-key-plus" :loading="busy === 'create-login'" @click="createAndStartLogin">
                Account anlegen und Login starten
              </v-btn>
            </template>

            <template v-else>
              <v-text-field v-model="form.account_id" label="Account-ID" density="compact" />
              <v-text-field v-model="form.display_name" label="Anzeigename" density="compact" />
              <v-btn color="primary" prepend-icon="mdi-link-plus" :loading="busy === 'create'" @click="create">Speichern</v-btn>
            </template>
          </v-card-text>
        </v-card>

        <v-card v-if="activeLogin" variant="flat" class="mt-4">
          <v-card-title>Login abschliessen</v-card-title>
          <v-card-text>
            <p class="text-body-2 text-medium-emphasis mb-3">{{ activeLogin.message }}</p>
            <v-btn :href="activeLogin.login_url" target="_blank" color="primary" prepend-icon="mdi-open-in-new" class="mb-3">Login öffnen</v-btn>
            <v-text-field v-model="loginCode" :label="activeLogin.code_label" density="compact" hide-details="auto" class="mb-3" />
            <v-btn color="secondary" prepend-icon="mdi-check" :disabled="!loginCode.trim()" :loading="busy === 'complete-login'" @click="completeLogin">
              Code bestätigen
            </v-btn>
          </v-card-text>
        </v-card>
      </v-col>

      <v-col cols="12" md="8">
        <v-data-table class="compact-table" :headers="headers" :items="rows" :items-per-page="-1" density="compact" hide-default-footer>
          <template #item.status="{ item }">
            <span v-if="item.last_error" class="text-error">{{ item.last_error }}</span>
            <span v-else>{{ item.status }}</span>
          </template>
          <template #item.actions="{ item }">
            <div class="actions-cell">
              <v-btn v-if="canLogin(item.platform)" size="small" variant="tonal" prepend-icon="mdi-key" :loading="busy === `login-${item.id}`" @click="startExistingLogin(item.id)">Login</v-btn>
              <v-btn v-if="canSync(item.platform)" size="small" color="primary" variant="text" prepend-icon="mdi-sync" :loading="busy === `sync-${item.id}`" @click="sync(item.id)">Sync</v-btn>
            </div>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { api } from '../api'
import { accountPlatforms, platformTitle } from '../platforms'
import { useLanStore } from '../store'
import type { Platform, ProviderLoginStart } from '../types'

const store = useLanStore()
const platforms = accountPlatforms
const form = reactive({ participant_id: undefined as number | undefined, platform: 'steam' as Platform, account_id: '', display_name: '' })
const activeLogin = ref<ProviderLoginStart | null>(null)
const loginCode = ref('')
const busy = ref<string | null>(null)
const error = ref('')
const message = ref('')
const headers = [
  { title: 'Teilnehmer', key: 'participant' },
  { title: 'Plattform', key: 'platform_title' },
  { title: 'Account', key: 'account_label' },
  { title: 'Status', key: 'status' },
  { title: 'Aktion', key: 'actions', sortable: false }
]
const rows = computed(() =>
  store.accounts.map((account) => ({
    ...account,
    participant: name(account.participant_id),
    platform_title: platformTitle(account.platform),
    account_label: account.display_name || account.account_id,
    status: account.last_error || account.last_successful_sync || 'Noch nicht synchronisiert'
  }))
)

onMounted(() => store.refresh())

function canLogin(platform: Platform) {
  return platform === 'epic' || platform === 'gog'
}

function canSync(platform: Platform) {
  return accountPlatforms.includes(platform)
}

async function create() {
  if (!form.participant_id) return
  busy.value = 'create'
  error.value = ''
  try {
    await api.createAccount(form)
    resetForm()
    await store.refresh()
    message.value = 'Account gespeichert.'
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function createAndStartLogin() {
  if (!form.participant_id) return
  busy.value = 'create-login'
  error.value = ''
  message.value = ''
  try {
    const account = await api.createAccount({ participant_id: form.participant_id, platform: form.platform, account_id: '', display_name: form.display_name })
    activeLogin.value = await api.startProviderLogin(account.id)
    loginCode.value = ''
    resetForm()
    await store.refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function startExistingLogin(accountId: number) {
  busy.value = `login-${accountId}`
  error.value = ''
  message.value = ''
  try {
    activeLogin.value = await api.startProviderLogin(accountId)
    loginCode.value = ''
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function completeLogin() {
  if (!activeLogin.value || !loginCode.value.trim()) return
  busy.value = 'complete-login'
  error.value = ''
  try {
    const result = await api.completeProviderLogin(activeLogin.value.account_id, { code: loginCode.value })
    message.value = result.message
    activeLogin.value = null
    loginCode.value = ''
    await store.refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

async function sync(accountId: number) {
  busy.value = `sync-${accountId}`
  error.value = ''
  try {
    await api.syncAccount(accountId)
    await store.refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    busy.value = null
  }
}

function resetForm() {
  Object.assign(form, { participant_id: undefined, platform: 'steam', account_id: '', display_name: '' })
}

const name = (id: number) => store.participants.find((participant) => participant.id === id)?.nickname ?? id
</script>

<style scoped>
.actions-cell {
  min-width: 160px;
  white-space: nowrap;
}
</style>

