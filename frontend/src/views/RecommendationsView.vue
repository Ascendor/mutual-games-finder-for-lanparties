<template>
  <div class="page">
    <h1 class="text-h4 mb-4">Was können wir spielen?</h1>
    <v-row class="mb-4">
      <v-col cols="12" md="9">
        <v-select v-model="selected" :items="otherParticipants" item-title="nickname" item-value="id" label="Mitspieler:innen" multiple chips density="compact" />
      </v-col>
      <v-col cols="12" md="3" class="d-flex align-center">
        <v-btn color="primary" prepend-icon="mdi-star-search-outline" :loading="loading || commonLoading" :disabled="!currentParticipant" @click="load">Berechnen</v-btn>
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
      <v-window-item value="common">
        <div class="availability-filter mb-3">
          <span class="text-body-2 font-weight-medium">Mindestens verfügbar für</span>
          <v-btn-toggle
            v-model="minimumCoverage"
            color="primary"
            density="compact"
            mandatory
            divided
            @update:model-value="loadCommon"
          >
            <v-btn :value="100">Alle</v-btn>
            <v-btn :value="75">75 %</v-btn>
            <v-btn :value="50">50 %</v-btn>
          </v-btn-toggle>
        </div>
        <RecommendationTable
          :items="common"
          :loading="loading || commonLoading"
          show-availability
        />
      </v-window-item>
      <v-window-item value="coop"><RecommendationTable :items="coop" :loading="loading" /></v-window-item>
      <v-window-item value="lan"><RecommendationTable :items="lan" :loading="loading" /></v-window-item>
      <v-window-item value="popular"><RecommendationTable :items="popular" :loading="loading || store.loading" /></v-window-item>
      <v-window-item value="new"><RecommendationTable :items="newForGroup" :loading="loading" /></v-window-item>
    </v-window>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import RecommendationTable from '../components/RecommendationTable.vue'
import { clearParticipant, currentParticipantId } from '../playerIdentity'
import { useLanStore } from '../store'
import type { Recommendation } from '../types'

const store = useLanStore()
const route = useRoute()
const router = useRouter()
const selected = ref<number[]>([])
const tab = ref('common')
const common = ref<Recommendation[]>([])
const coop = ref<Recommendation[]>([])
const lan = ref<Recommendation[]>([])
const popular = ref<Recommendation[]>([])
const newForGroup = ref<Recommendation[]>([])
const loading = ref(false)
const commonLoading = ref(false)
const minimumCoverage = ref(75)
const error = ref('')
const currentParticipant = computed(() =>
  store.participants.find((participant) => participant.id === currentParticipantId.value)
)
const otherParticipants = computed(() =>
  store.sortedParticipants.filter((participant) => participant.id !== currentParticipantId.value)
)
const selectedPlayerIds = computed(() => {
  if (!currentParticipantId.value) return []
  return [currentParticipantId.value, ...selected.value.filter((id) => id !== currentParticipantId.value)]
})

onMounted(async () => {
  await store.refreshParticipants()
  if (!currentParticipant.value) {
    clearParticipant()
    await router.replace({ path: '/player', query: { redirect: '/recommendations' } })
    return
  }
  const queryPlayers = typeof route.query.players === 'string' ? route.query.players.split(',').map((item) => Number(item)).filter(Boolean) : []
  selected.value = (queryPlayers.length ? queryPlayers : store.presentParticipants.map((participant) => participant.id))
    .filter((id) => id !== currentParticipantId.value)
  if (typeof route.query.tab === 'string') tab.value = route.query.tab
  await load()
})

async function load() {
  if (!selectedPlayerIds.value.length) return
  loading.value = true
  error.value = ''
  try {
    const [commonGames, coopGames, lanGames, popularGames, newGames] = await Promise.all([
      api.common(selectedPlayerIds.value, minimumCoverage.value),
      api.coop(selectedPlayerIds.value),
      api.lanForGroup(selectedPlayerIds.value),
      api.recommendations('popular'),
      api.newForGroup(selectedPlayerIds.value)
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

async function loadCommon() {
  if (!selectedPlayerIds.value.length || loading.value) return
  commonLoading.value = true
  error.value = ''
  try {
    common.value = await api.common(selectedPlayerIds.value, minimumCoverage.value)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    commonLoading.value = false
  }
}
</script>

<style scoped>
.availability-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
</style>


