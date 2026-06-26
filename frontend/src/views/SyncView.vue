<template>
  <div class="page">
    <div class="d-flex align-center justify-space-between mb-4">
      <h1 class="text-h4">Synchronisation</h1>
      <div class="d-flex ga-2"><v-btn color="secondary" variant="tonal" prepend-icon="mdi-database-sync-outline" :loading="metadataLoading" @click="syncMetadata">Metadaten aktualisieren</v-btn><v-btn to="/accounts" color="primary" variant="tonal" prepend-icon="mdi-account-key">Accounts</v-btn></div>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
    <v-alert v-if="metadataMessage" type="success" variant="tonal" class="mb-4">{{ metadataMessage }}</v-alert>

    <v-row>
      <v-col cols="12" md="5">
        <v-card variant="flat">
          <v-card-title>Accounts synchronisieren</v-card-title>
          <v-list>
            <v-list-item v-for="account in store.accounts" :key="account.id" :title="`${account.platform}: ${account.display_name || account.account_id}`" :subtitle="account.last_error || account.last_successful_sync || 'Noch nie synchronisiert'">
              <template #append>
                <v-btn size="small" color="primary" variant="tonal" prepend-icon="mdi-sync" :loading="loading === account.id" @click="sync(account.id)">Sync</v-btn>
              </template>
            </v-list-item>
          </v-list>
        </v-card>
      </v-col>
      <v-col cols="12" md="7">
        <v-data-table class="compact-table" :headers="headers" :items="rows" :items-per-page="-1" density="compact" hide-default-footer>
          <template #item.status="{ item }">
            <v-chip :color="item.success ? 'secondary' : 'error'" size="small">{{ item.status }}</v-chip>
          </template>
        </v-data-table>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'
import { useLanStore } from '../store'

const store = useLanStore()
const loading = ref<number | null>(null)
const metadataLoading = ref(false)
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
    account: accountLabel(run.account_id),
    status: run.success ? 'OK' : 'Fehler'
  }))
)
onMounted(() => store.refresh())

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
    metadataMessage.value = `${result.updated_games} von ${result.scanned_games} Spielen aktualisiert${result.failed_games ? `, ${result.failed_games} Fehler` : ''}`
    await store.refresh()
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    metadataLoading.value = false
  }
}
function accountLabel(id: number) {
  const account = store.accounts.find((item) => item.id === id)
  return account ? `${account.platform}: ${account.display_name || account.account_id}` : id
}
</script>



