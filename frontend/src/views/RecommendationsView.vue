<template>
  <div class="page">
    <h1 class="text-h4 mb-4">Was können wir spielen?</h1>
    <v-row class="mb-4">
      <v-col cols="12" md="9">
        <v-select
          v-model="selected"
          :items="participants"
          item-title="nickname"
          item-value="id"
          label="Spieler:innen"
          multiple
          chips
          density="compact"
        >
          <template #item="{ props: itemProps, item }">
            <v-list-item
              v-bind="itemProps"
              :title="participantOptionLabel(item.raw)"
            >
              <template #prepend>
                <v-checkbox-btn
                  :model-value="selected.includes(item.raw.id)"
                  class="participant-option-checkbox"
                  tabindex="-1"
                  aria-hidden="true"
                />
              </template>
            </v-list-item>
          </template>
        </v-select>
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
          <v-switch
            v-model="freeGamesAsOwned"
            label="Free Games wie Besitz werten"
            color="primary"
            density="compact"
            hide-details
            @update:model-value="loadCommon"
          />
        </div>
        <RecommendationTable
          :items="common"
          :loading="loading || commonLoading"
          show-availability
          :free-games-as-owned="freeGamesAsOwned"
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
import type { Participant, Recommendation } from '../types'
import { trackUsage } from '../usageAnalytics'

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
const freeGamesAsOwned = ref(true)
const error = ref('')
const currentParticipant = computed(() =>
  store.participants.find((participant) => participant.id === currentParticipantId.value)
)
const participants = computed(() => store.sortedParticipants)
const selectedPlayerIds = computed(() => [...new Set(selected.value)])

onMounted(async () => {
  await store.refreshParticipants()
  if (!currentParticipant.value) {
    clearParticipant()
    await router.replace({ path: '/player', query: { redirect: '/recommendations' } })
    return
  }
  const queryPlayers = typeof route.query.players === 'string' ? route.query.players.split(',').map((item) => Number(item)).filter(Boolean) : []
  const initialPlayers = queryPlayers.length
    ? queryPlayers
    : store.presentParticipants.map((participant) => participant.id)
  selected.value = [...new Set([currentParticipantId.value!, ...initialPlayers])]
  if (typeof route.query.tab === 'string') tab.value = route.query.tab
  await load()
})

async function load() {
  if (!selectedPlayerIds.value.length) return
  loading.value = true
  error.value = ''
  try {
    const [commonGames, coopGames, lanGames, popularGames, newGames] = await Promise.all([
      api.common(selectedPlayerIds.value, minimumCoverage.value, freeGamesAsOwned.value),
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
    trackUsage('group_games_search', {
      selected_players: selectedPlayerIds.value.map((id) => {
        const participant = participants.value.find((item) => item.id === id)
        return { id, nickname: participant?.nickname || `Teilnehmer ${id}` }
      }),
      group_size: selectedPlayerIds.value.length,
      common_results: commonGames.length,
      coop_results: coopGames.length,
      lan_results: lanGames.length
    })
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
    common.value = await api.common(
      selectedPlayerIds.value,
      minimumCoverage.value,
      freeGamesAsOwned.value
    )
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    commonLoading.value = false
  }
}

function participantOptionLabel(participant: Participant) {
  return participant.real_name
    ? `${participant.nickname} (${participant.real_name})`
    : participant.nickname
}
</script>

<style scoped>
.availability-filter {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.participant-option-checkbox {
  pointer-events: none;
}
</style>
