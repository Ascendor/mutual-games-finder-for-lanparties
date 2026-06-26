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
          <v-card-text>
            <div class="inline-action">
              <span>Ich will</span>
              <v-text-field v-model="gameName" label="Spiel" prepend-inner-icon="mdi-gamepad-variant-outline" density="comfortable" hide-details="auto" @keyup.enter="findPlayers" />
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
          <v-card-title>Spiel finden</v-card-title>
          <v-card-text>
            <div class="inline-action">
              <span>Ich will mit</span>
              <v-autocomplete
                v-model="selectedPlayers"
                :items="store.participants"
                item-title="nickname"
                item-value="id"
                label="Mitspieler:innen"
                prepend-inner-icon="mdi-account-group-outline"
                multiple
                chips
                density="comfortable"
                hide-details="auto"
              />
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
          <v-card-title>Meine Spiele hinzufuegen</v-card-title>
          <v-card-text>
            <v-combobox v-model="participant.nickname" :items="participantNicknames" label="Nickname" prepend-inner-icon="mdi-account-outline" density="comfortable" hide-details="auto" class="mb-3" auto-select-first />
            <v-text-field v-model="participant.real_name" label="Real Name optional" density="comfortable" hide-details="auto" />
          </v-card-text>
          <v-card-actions>
            <v-btn color="primary" prepend-icon="mdi-plus" :loading="creating" :disabled="!participantNickname()" @click="createParticipant">Loslegen</v-btn>
          </v-card-actions>
        </v-card>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useLanStore } from '../store'

const router = useRouter()
const store = useLanStore()
const gameName = ref('')
const selectedPlayers = ref<number[]>([])
const creating = ref(false)
const error = ref('')
const participant = reactive({ nickname: '', real_name: '' })
const participantNicknames = computed(() => store.participants.map((item) => item.nickname))

onMounted(() => store.refresh())

function findPlayers() {
  const game = gameName.value.trim()
  if (!game) return
  router.push({ path: '/find-players', query: { game } })
}

function findGroupGames() {
  if (!selectedPlayers.value.length) return
  router.push({ path: '/recommendations', query: { players: selectedPlayers.value.join(','), tab: 'common' } })
}

async function createParticipant() {
  const nickname = participantNickname()
  if (!nickname) return
  creating.value = true
  error.value = ''
  try {
    const existing = store.participants.find((item) => item.nickname.toLocaleLowerCase() === nickname.toLocaleLowerCase())
    if (existing) {
      router.push({ path: '/logins', query: { participant: String(existing.id) } })
      return
    }
    const created = await api.createParticipant({
      nickname,
      real_name: participant.real_name.trim() || null,
      present: true,
      notes: ''
    })
    await store.refresh()
    router.push({ path: '/logins', query: { participant: String(created.id) } })
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err)
  } finally {
    creating.value = false
  }
}

function participantNickname() {
  return participant.nickname.trim()
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

.inline-action {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

@media (max-width: 620px) {
  .inline-action {
    grid-template-columns: 1fr;
  }
}
</style>
