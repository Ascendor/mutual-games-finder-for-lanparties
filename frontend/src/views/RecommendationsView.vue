<template>
  <div class="page">
    <h1 class="text-h4 mb-4">Was können wir spielen?</h1>
    <v-row class="mb-4">
      <v-col cols="12" md="6">
        <v-select v-model="selected" :items="store.participants" item-title="nickname" item-value="id" label="Ausgewählte Spieler" multiple chips density="compact" />
      </v-col>
      <v-col cols="12" md="3">
        <v-text-field v-model.number="groupSize" label="Gruppengröße" type="number" density="compact" />
      </v-col>
      <v-col cols="12" md="3" class="d-flex align-center">
        <v-btn color="primary" prepend-icon="mdi-star-search-outline" @click="load">Berechnen</v-btn>
      </v-col>
    </v-row>

    <v-tabs v-model="tab" color="primary">
      <v-tab value="common">Gemeinsam</v-tab>
      <v-tab value="coop">Koop</v-tab>
      <v-tab value="lan">LAN</v-tab>
      <v-tab value="size">Gruppengröße</v-tab>
      <v-tab value="popular">Beliebt</v-tab>
    </v-tabs>
    <v-window v-model="tab" class="mt-4">
      <v-window-item value="common"><RecommendationTable :items="common" /></v-window-item>
      <v-window-item value="coop"><RecommendationTable :items="coop" /></v-window-item>
      <v-window-item value="lan"><RecommendationTable :items="store.lan" /></v-window-item>
      <v-window-item value="size"><RecommendationTable :items="sized" /></v-window-item>
      <v-window-item value="popular"><RecommendationTable :items="store.popular" /></v-window-item>
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
const groupSize = ref(4)
const tab = ref('common')
const common = ref<Recommendation[]>([])
const coop = ref<Recommendation[]>([])
const sized = ref<Recommendation[]>([])

onMounted(async () => {
  await store.refresh()
  const queryPlayers = typeof route.query.players === 'string' ? route.query.players.split(',').map((item) => Number(item)).filter(Boolean) : []
  selected.value = queryPlayers.length ? queryPlayers : store.presentParticipants.map((participant) => participant.id)
  if (typeof route.query.tab === 'string') tab.value = route.query.tab
  await load()
})

async function load() {
  await store.refresh()
  common.value = await api.common(selected.value)
  coop.value = await api.coop(selected.value)
  sized.value = await api.groupSize(groupSize.value)
}
</script>


