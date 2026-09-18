<template>
  <div class="page home-page home-page-container d-flex flex-column pa-4">
    <div class="mb-6 title-section">
      <h1 class="text-h3">ref'ju:geeks play together - Der Spielefinder</h1>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

     <v-spacer class="flex-grow-1" />
     <div class="cards-wrapper w-100">
    <v-row class="flex-grow-0">
      <v-col cols="12" lg="4">
        <v-card variant="flat" class="action-card">
          <v-card-title><strong>Mitspieler:innen finden</strong></v-card-title>
          <v-card-text class="action-content">
            <div class="inline-action text-body-1">
              <span>Ich will</span>
              <v-autocomplete
                v-model="gameName"
                :items="store.gameOptions"
                item-title="title"
                item-value="title"
                label="Spiel"
                prepend-inner-icon="mdi-gamepad-variant-outline"
                density="comfortable"
                hide-details="auto"
                clearable
                auto-select-first
                :loading="store.loading"
                @keyup.enter="findPlayers"
              />
              <span>spielen.</span>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" prepend-icon="mdi-account-search-outline" :disabled="!gameName.trim()" @click="findPlayers">Wer spielt mit?</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" lg="4">
        <v-card variant="flat" class="action-card">
          <v-card-title><strong>Gemeinsames Spiel finden</strong></v-card-title>
          <v-card-text class="action-content">
            <div class="inline-action text-body-1">
              <span>Ich will mit</span>
              <v-autocomplete
                v-model="selectedPlayers"
                :items="otherParticipants"
                item-title="nickname"
                item-value="id"
                label="Mitspieler:innen"
                prepend-inner-icon="mdi-account-group-outline"
                multiple
                chips
                density="comfortable"
                hide-details="auto"
              >
                <template #item="{ props: itemProps, item }">
                  <v-list-item
                    v-bind="itemProps"
                    :title="participantOptionLabel(item.raw)"
                  >
                    <template #prepend>
                      <v-checkbox-btn
                        :model-value="selectedPlayers.includes(item.raw.id)"
                        class="participant-option-checkbox"
                        tabindex="-1"
                        aria-hidden="true"
                      />
                    </template>
                  </v-list-item>
                </template>
              </v-autocomplete>
              <span>spielen.</span>
            </div>
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" prepend-icon="mdi-star-search-outline" :disabled="selectedPlayers.length === 0" @click="findGroupGames">Was können wir spielen?</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>

      <v-col cols="12" lg="4">
        <v-card variant="flat" class="action-card">
          <v-card-title class="settings-title">
            <span><strong>Einstellungen</strong></span>
            <v-btn
              variant="text"
              color="primary"
              size="small"
              prepend-icon="mdi-logout"
              @click="logout"
            >
              Abmelden
            </v-btn>
          </v-card-title>
          <v-card-text class="action-content text-center">
            <span class="text-body-1">Eingeloggt als <strong>{{ currentParticipant?.nickname }}</strong></span>
          </v-card-text>
          <v-card-actions class="settings-actions">
            <v-btn to="/my-games" color="primary" variant="text" prepend-icon="mdi-format-list-bulleted">Meine Spiele</v-btn>
            <v-btn to="/logins" color="primary" variant="text" prepend-icon="mdi-key-chain-variant">Meine Accounts</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
</div>

 <v-spacer class="flex-grow-1" />

 <!-- NEU: Ein flexibler Container, der den restlichen Platz füllt -->
      <section class="recent-acquisitions mt-auto">
        <div class="recent-acquisitions__header">
          <div>
            <h2 class="text-subtitle-1 mb-1">Neu in euren Bibliotheken</h2>
            <p class="text-caption text-medium-emphasis mb-0">
              Erwerbsdaten aus den verbundenen Bibliotheken, nicht bloß neue Imports.
            </p>
          </div>
          <v-select
            v-model="acquisitionDays"
            :items="acquisitionDayOptions"
            density="compact"
            hide-details
            variant="plain"
            class="period-select"
            @update:model-value="() => loadRecentAcquisitions()"
          />
        </div>

        <v-data-table
          class="recent-acquisitions__table"
          :headers="acquisitionHeaders"
          :items="recentAcquisitions"
          :items-per-page="6"
          :loading="loadingAcquisitions"
          density="compact"
        >
          <template #item.participant="{ item }">
            {{ item.participant.nickname }}
          </template>
          <template #item.game="{ item }">
            <em>{{ item.game.title }}</em>
          </template>
          <template #item.owned_since="{ item }">
            {{ formatDate(item.owned_since) }}
          </template>
          <template #no-data>
            <div class="pa-4 text-medium-emphasis">
              Keine Spiele mit Erwerbsdatum im gewählten Zeitraum gefunden.
            </div>
          </template>
        </v-data-table>
      </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { clearParticipant, currentParticipantId } from '../playerIdentity'
import { platformTitle } from '../platforms'
import { useLanStore } from '../store'
import type { Participant, RecentAcquisition } from '../types'

const router = useRouter()
const store = useLanStore()
const gameName = ref('')
const selectedPlayers = ref<number[]>([])
const error = ref('')
const recentAcquisitions = ref<RecentAcquisition[]>([])
const acquisitionDays = ref(90)
const loadingAcquisitions = ref(false)
const acquisitionDayOptions = [
  { title: '7 Tage', value: 7 },
  { title: '30 Tage', value: 30 },
  { title: '90 Tage', value: 90 },
  { title: '1 Jahr', value: 365 }
]
const acquisitionHeaders = [
  { title: 'Spieler:in', key: 'participant' },
  { title: 'Spiel', key: 'game' },
  { title: 'Erworben', key: 'owned_since' },
]
const currentParticipant = computed(() =>
  store.participants.find((participant) => participant.id === currentParticipantId.value)
)
const otherParticipants = computed(() =>
  store.sortedParticipants.filter((participant) => participant.id !== currentParticipantId.value)
)

onMounted(async () => {
  await store.refreshHome()
  await loadRecentAcquisitions()
  if (!currentParticipant.value) {
    clearParticipant()
    await router.replace({ path: '/player', query: { redirect: '/' } })
  }
})

function findPlayers() {
  const game = gameName.value.trim()
  if (!game) return
  router.push({ path: '/find-players', query: { game } })
}

function findGroupGames() {
  if (!selectedPlayers.value.length || !currentParticipantId.value) return
  const players = [currentParticipantId.value, ...selectedPlayers.value]
  router.push({ path: '/recommendations', query: { players: players.join(','), tab: 'common' } })
}

function participantOptionLabel(participant: Participant) {
  return participant.real_name
    ? `${participant.nickname} (${participant.real_name})`
    : participant.nickname
}

async function logout() {
  clearParticipant()
  await router.replace('/player')
}

async function loadRecentAcquisitions() {
  loadingAcquisitions.value = true
  try {
    recentAcquisitions.value = await api.recentAcquisitions(acquisitionDays.value, 100)
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    loadingAcquisitions.value = false
  }
}

function formatDate(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('de-DE', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric'
  }).format(date)
}
</script>

<style scoped>
.home-page {
  max-width: 1320px;
  min-height: 0; /* Verhindert Überlauf-Bugs */
}

.home-page-container {
  /* Berechnet den mathematisch exakten, maximal verfügbaren Platz im Viewport */
  height: calc(100vh - var(--v-layout-top, 0px) - var(--v-layout-bottom, 0px) - 32px);
  min-height: 0;
  box-sizing: border-box;
}

/* NEU: Richtet die Karten im zugewiesenen Raum vertikal mittig aus */
.cards-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
}

/* Drückt die Sektion nach ganz unten, falls Platz auf dem Bildschirm ist */
.recent-acquisitions {
  width: 100%;
}

/* Auf kleinen Bildschirmen heben wir die starre Zentrierung und Höhe wieder auf */
@media (max-width: 1264px) {
  .home-page-container {
    height: auto;
    min-height: 100%;
  }
  
  .cards-wrapper {
    display: block; /* Normaler Block-Fluss untereinander */
    margin-bottom: 32px;
  }
  
  .recent-acquisitions {
    margin-top: 16px;
  }
}

.action-card {
  min-height: 260px;
  display: flex;
  flex-direction: column;
}

.action-card :deep(.v-card-text) {
  flex: 1;
}

.action-content {
  display: flex;
  align-items: center;
  justify-content: center;
}

.settings-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.settings-actions {
  justify-content: center;
  flex-wrap: nowrap;
  gap: 8px;
}

.settings-actions :deep(.v-btn) {
  min-width: 0;
  padding-inline: 10px;
}

.inline-action {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  width: 100%;
}

.participant-option-checkbox {
  pointer-events: none;
}

.recent-acquisitions {
  border-top: 1px solid rgba(var(--v-border-color), 0.28);
  padding-top: 18px;
}

.recent-acquisitions__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
}

.recent-acquisitions__table {
  background: transparent;
}

.period-select {
  max-width: 120px;
}

.platform-chip-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

@media (max-width: 620px) {
  .inline-action {
    grid-template-columns: 1fr;
  }

  .settings-actions {
    flex-wrap: wrap;
  }

  .recent-acquisitions__header {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
