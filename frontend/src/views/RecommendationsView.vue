<template>
  <div class="page">
    <h1 class="text-h4 mb-4">Was können wir spielen?</h1>
    <v-row class="mb-4">
      <v-col cols="12" md="9">
        <v-select v-model="selected" :items="store.participants" item-title="nickname" item-value="id" label="Ausgewählte Spieler" multiple chips density="compact" />
      </v-col>
      <v-col cols="12" md="3" class="d-flex align-center">
        <v-btn color="primary" prepend-icon="mdi-star-search-outline" :loading="loading" :disabled="selected.length === 0" @click="load">Berechnen</v-btn>
      </v-col>
    </v-row>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <v-tabs v-model="tab" color="primary">
      <v-tab value="common">Gemeinsam</v-tab>
      <v-tab value="coop">Koop</v-tab>
      <v-tab value="lan">LAN</v-tab>
      <v-tab value="popular">Beliebt</v-tab>
      <v-tab value="new">Neu für die Gruppe</v-tab>
    </v-tabs>
    <v-window v-model="tab" class="mt-4">
      <v-window-item value="common"><RecommendationTable :items="common" :loading="loading" /></v-window-item>
      <v-window-item value="coop"><RecommendationTable :items="coop" :loading="loading" /></v-window-item>
      <v-window-item value="lan"><RecommendationTable :items="lan" :loading="loading" /></v-window-item>
      <v-window-item value="popular"><RecommendationTable :items="popular" :loading="loading || store.loading" /></v-window-item>
      <v-window-item value="new"><RecommendationTable :items="newForGroup" :loading="loading" /></v-window-item>
    </v-window>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import RecommendationTable from '../components/RecommendationTable.vue'
import { useLanStore } from '../store'
import type { Recommendation } from '../types'

const store = useLanStore()
const route = useRoute()
const selected = ref<number[]>([])
const tab = ref('common')
const common = ref<Recommendation[]>([])
const coop = ref<Recommendation[]>([])
const lan = ref<Recommendation[]>([])
const popular = ref<Recommendation[]>([])
const newForGroup = ref<Recommendation[]>([])
const loading = ref(false)
const error = ref('')

onMounted(async () => {
  await store.refreshParticipants()
  const queryPlayers = typeof route.query.players === 'string' ? route.query.players.split(',').map((item) => Number(item)).filter(Boolean) : []
  selected.value = queryPlayers.length ? queryPlayers : store.presentParticipants.map((participant) => participant.id)
  if (typeof route.query.tab === 'string') tab.value = route.query.tab
  await load()
})

async function load() {
  if (!selected.value.length) return
  loading.value = true
  error.value = ''
  try {
    const [commonGames, coopGames, lanGames, popularGames, newGames] = await Promise.all([
      api.common(selected.value),
      api.coop(selected.value),
      api.lanForGroup(selected.value),
      api.recommendations('popular'),
      api.newForGroup(selected.value)
    ])
    common.value = commonGames
    coop.value = coopGames
    lan.value = lanGames
    popular.value = popularGames
    newForGroup.value = newGames
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loading.value = false
  }
}
</script>


