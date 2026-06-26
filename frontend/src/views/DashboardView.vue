<template>
  <div class="page">
    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4">{{ store.error }}</v-alert>
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4">Dashboard</h1>
        <p class="text-medium-emphasis">Lokale Bibliotheken, Anwesenheit und Empfehlungen auf einen Blick.</p>
      </div>
      <v-btn color="primary" prepend-icon="mdi-refresh" :loading="store.loading" @click="store.refresh()">Aktualisieren</v-btn>
    </div>

    <v-row>
      <v-col cols="12" md="3">
        <v-card variant="flat">
          <v-card-text><div class="metric">{{ store.presentParticipants.length }}</div><div>Anwesend</div></v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card variant="flat">
          <v-card-text><div class="metric">{{ store.games.length }}</div><div>Spiele</div></v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card variant="flat">
          <v-card-text><div class="metric">{{ store.ownerships.length }}</div><div>Ownerships</div></v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="3">
        <v-card variant="flat">
          <v-card-text><div class="metric">{{ Math.round(store.totalPlaytime / 60) }}</div><div>Stunden gesamt</div></v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <v-row class="mt-2">
      <v-col cols="12" lg="6">
        <h2 class="text-h6 mb-2">Beliebteste Spiele</h2>
        <RecommendationTable :items="store.popular.slice(0, 8)" />
      </v-col>
      <v-col cols="12" lg="6">
        <h2 class="text-h6 mb-2">Beste LAN-Spiele</h2>
        <RecommendationTable :items="store.lan.slice(0, 8)" />
      </v-col>
      <v-col cols="12">
        <h2 class="text-h6 mb-2">Gemeinsame Spiele der Anwesenden</h2>
        <RecommendationTable :items="store.present.slice(0, 12)" />
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import RecommendationTable from '../components/RecommendationTable.vue'
import { useLanStore } from '../store'

const store = useLanStore()
onMounted(() => store.refresh())
</script>

