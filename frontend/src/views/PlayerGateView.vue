<template>
  <div class="player-gate">
    <v-card variant="flat" class="player-card">
      <v-card-text class="pa-6 pa-sm-8">
        <div class="text-overline text-primary mb-2">ref'ju:geeks play together</div>
        <h1 class="text-h4 mb-2">Wer bist du?</h1>
        <p class="text-body-1 text-medium-emphasis mb-6">
          Wähle deinen Nickname oder gib einen neuen ein.
        </p>

        <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>

        <v-combobox
          v-model="nickname"
          :items="participantNicknames"
          label="Nickname"
          prepend-inner-icon="mdi-account-outline"
          density="comfortable"
          auto-select-first
          autofocus
          :loading="store.loading"
          :disabled="busy"
          @keyup.enter="continueAsParticipant"
        />

        <v-expand-transition>
          <v-text-field
            v-if="isNewParticipant"
            v-model="realName"
            label="Real Name (optional)"
            prepend-inner-icon="mdi-card-account-details-outline"
            density="comfortable"
            :disabled="busy"
            class="mt-2"
            @keyup.enter="continueAsParticipant"
          />
        </v-expand-transition>

        <v-btn
          color="primary"
          size="large"
          block
          :prepend-icon="existingParticipant ? 'mdi-login' : 'mdi-account-plus-outline'"
          :loading="busy"
          :disabled="!cleanNickname"
          @click="continueAsParticipant"
        >
          {{ existingParticipant ? `Weiter als ${existingParticipant.nickname}` : 'Neu anlegen und Spiele hinzufügen' }}
        </v-btn>
      </v-card-text>
    </v-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { currentParticipantId, selectParticipant } from '../playerIdentity'
import { useLanStore } from '../store'

const route = useRoute()
const router = useRouter()
const store = useLanStore()
const nickname = ref<string | null>('')
const realName = ref('')
const busy = ref(false)
const error = ref('')

const cleanNickname = computed(() => String(nickname.value || '').trim())
const participantNicknames = computed(() => store.sortedParticipants.map((participant) => participant.nickname))
const existingParticipant = computed(() => {
  const normalized = cleanNickname.value.toLocaleLowerCase()
  if (!normalized) return undefined
  return store.participants.find(
    (participant) => participant.nickname.toLocaleLowerCase() === normalized
  )
})
const isNewParticipant = computed(() => Boolean(cleanNickname.value && !existingParticipant.value))

onMounted(async () => {
  await store.refreshParticipants()
  const current = store.participants.find((participant) => participant.id === currentParticipantId.value)
  if (current) nickname.value = current.nickname
})

async function continueAsParticipant() {
  if (!cleanNickname.value || busy.value) return
  busy.value = true
  error.value = ''
  try {
    let participant = existingParticipant.value
    let created = false
    if (!participant) {
      participant = await api.createParticipant({
        nickname: cleanNickname.value,
        real_name: realName.value.trim() || null,
        present: true,
        notes: ''
      })
      created = true
      await store.refreshParticipants()
    }

    selectParticipant(participant.id, participant.nickname)
    if (created) {
      await router.replace({ path: '/logins', query: { onboarding: 'true' } })
      return
    }

    const redirect = typeof route.query.redirect === 'string'
      && route.query.redirect.startsWith('/')
      && !route.query.redirect.startsWith('//')
      ? route.query.redirect
      : '/'
    await router.replace(redirect)
  } catch (value) {
    error.value = value instanceof Error ? value.message : String(value)
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.player-gate {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgb(var(--v-theme-surface-variant));
}

.player-card {
  width: min(100%, 480px);
  border: 1px solid rgb(var(--v-theme-outline-variant));
}
</style>
