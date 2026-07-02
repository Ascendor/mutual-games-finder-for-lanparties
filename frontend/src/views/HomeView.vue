<template>
  <div class="page home-page">
    <div class="mb-6">
      <h1 class="text-h3">ref'ju:geeks play together - Der Spielefinder</h1>
    </div>

    <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

    <v-row>
      <v-col cols="12" lg="4">
        <v-card variant="flat" class="action-card">
          <v-card-title>Mitspieler:innen finden</v-card-title>
          <v-card-text class="action-content">
            <div class="inline-action">
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
          <v-card-title>Gemeinsames Spiel finden</v-card-title>
          <v-card-text class="action-content">
            <div class="inline-action">
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
          <v-card-title>Einstellungen</v-card-title>
          <v-card-text class="action-content text-center">
            <span class="text-body-1">Eingeloggt als <strong>{{ currentParticipant?.nickname }}</strong></span>
          </v-card-text>
          <v-card-actions class="settings-actions">
            <v-btn variant="text" color="primary" prepend-icon="mdi-logout" @click="logout">Abmelden</v-btn>
            <v-btn to="/logins" color="primary" prepend-icon="mdi-key-chain-variant">Meine Accounts</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { clearParticipant, currentParticipantId } from '../playerIdentity'
import { useLanStore } from '../store'
import type { Participant } from '../types'

const router = useRouter()
const store = useLanStore()
const gameName = ref('')
const selectedPlayers = ref<number[]>([])
const error = ref('')
const currentParticipant = computed(() =>
  store.participants.find((participant) => participant.id === currentParticipantId.value)
)
const otherParticipants = computed(() =>
  store.sortedParticipants.filter((participant) => participant.id !== currentParticipantId.value)
)

onMounted(async () => {
  await store.refreshHome()
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
</script>

<style scoped>
.home-page {
  max-width: 1180px;
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

.settings-actions {
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
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

@media (max-width: 620px) {
  .inline-action {
    grid-template-columns: 1fr;
  }
}
</style>
