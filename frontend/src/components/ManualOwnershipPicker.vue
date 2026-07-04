<template>
  <section class="manual-library">
    <div>
      <h3 class="text-subtitle-1 font-weight-bold">Fehlende Spiele ergänzen</h3>
      <p class="text-body-2 text-medium-emphasis mb-3">
        Suche ein bereits bekanntes Spiel und ergänze es dauerhaft in deiner Bibliothek.
      </p>
    </div>

    <v-text-field
      v-model="search"
      label="Spiel suchen"
      placeholder="Zum Beispiel Portal 2"
      density="compact"
      variant="outlined"
      clearable
      hide-details
      @update:model-value="scheduleSearch"
    />

    <v-progress-linear v-if="loading" indeterminate height="2" class="mt-2" />
    <v-alert v-if="error" type="error" variant="tonal" density="compact" class="mt-3">
      {{ error }}
    </v-alert>
    <v-alert v-if="message" type="success" variant="tonal" density="compact" class="mt-3">
      {{ message }}
    </v-alert>

    <div v-if="results.length" class="manual-results mt-2">
      <div v-for="game in results" :key="game.id" class="manual-result">
        <div class="manual-game-info">
          <strong>{{ game.title }}</strong>
          <div class="text-caption text-medium-emphasis">
            {{ gameMeta(game) }}
          </div>
        </div>
        <div class="manual-action">
          <template v-if="game.owned">
            <v-chip color="success" variant="tonal" size="small">In meiner Bibliothek</v-chip>
            <v-btn
              v-if="game.manual_confirmations.length"
              color="error"
              variant="text"
              size="small"
              :loading="busyGameId === game.id"
              @click="removeManual(game)"
            >
              Manuellen Eintrag entfernen
            </v-btn>
          </template>
          <v-btn
            v-else
            color="primary"
            variant="tonal"
            size="small"
            :loading="busyGameId === game.id"
            @click="beginAdd(game)"
          >
            Auch in meiner Bibliothek
          </v-btn>
        </div>
      </div>
    </div>
    <p v-else-if="searched && !loading" class="text-body-2 text-medium-emphasis mt-3 mb-0">
      Kein passendes bekanntes Spiel gefunden.
    </p>

    <v-dialog v-model="platformDialog" max-width="420">
      <v-card>
        <v-card-title>Plattform auswählen</v-card-title>
        <v-card-text>
          <p class="text-body-2 mb-4">Wo besitzt du „{{ selectedGame?.title }}“?</p>
          <v-select
            v-model="selectedPlatform"
            :items="platformChoices"
            item-title="title"
            item-value="value"
            label="Plattform"
            variant="outlined"
            density="compact"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="platformDialog = false">Abbrechen</v-btn>
          <v-btn color="primary" :disabled="!selectedPlatform" @click="confirmAdd">
            Hinzufügen
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { api } from '../api'
import type { Account, ManualOwnershipGameOption, Participant, Platform } from '../types'

const props = defineProps<{
  participant: Participant
  accounts: Account[]
}>()

const search = ref('')
const results = ref<ManualOwnershipGameOption[]>([])
const loading = ref(false)
const searched = ref(false)
const busyGameId = ref<number | null>(null)
const error = ref('')
const message = ref('')
const platformDialog = ref(false)
const selectedGame = ref<ManualOwnershipGameOption | null>(null)
const selectedPlatform = ref<Platform | null>(null)
let searchTimer: ReturnType<typeof setTimeout> | undefined
let searchSequence = 0

const platformChoices = computed(() =>
  candidatePlatforms(selectedGame.value).map((platform) => ({
    value: platform,
    title: platformTitle(platform)
  }))
)

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer)
})

function scheduleSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  const term = search.value?.trim() || ''
  if (!term) {
    results.value = []
    searched.value = false
    loading.value = false
    return
  }
  searchTimer = setTimeout(loadResults, 250)
}

async function loadResults() {
  const term = search.value?.trim() || ''
  if (!term) return
  const sequence = ++searchSequence
  loading.value = true
  error.value = ''
  try {
    const response = await api.manualOwnershipOptions(props.participant.id, term)
    if (sequence === searchSequence) {
      results.value = response
      searched.value = true
    }
  } catch (err) {
    if (sequence === searchSequence) error.value = readableError(err)
  } finally {
    if (sequence === searchSequence) loading.value = false
  }
}

function beginAdd(game: ManualOwnershipGameOption) {
  error.value = ''
  message.value = ''
  selectedGame.value = game
  const candidates = candidatePlatforms(game)
  if (candidates.length === 1) {
    selectedPlatform.value = candidates[0]
    void confirmAdd()
    return
  }
  selectedPlatform.value = candidates[0] || null
  platformDialog.value = true
}

async function confirmAdd() {
  const game = selectedGame.value
  const platform = selectedPlatform.value
  if (!game || !platform) return
  platformDialog.value = false
  busyGameId.value = game.id
  error.value = ''
  message.value = ''
  try {
    await api.createManualOwnership({
      participant_id: props.participant.id,
      game_id: game.id,
      platform
    })
    message.value = `„${game.title}“ ist jetzt in deiner Bibliothek.`
    await loadResults()
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busyGameId.value = null
  }
}

async function removeManual(game: ManualOwnershipGameOption) {
  busyGameId.value = game.id
  error.value = ''
  message.value = ''
  try {
    await Promise.all(
      game.manual_confirmations.map((confirmation) =>
        api.deleteManualOwnership(confirmation.id)
      )
    )
    message.value = `Der manuelle Eintrag für „${game.title}“ wurde entfernt.`
    await loadResults()
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busyGameId.value = null
  }
}

function candidatePlatforms(game: ManualOwnershipGameOption | null): Platform[] {
  if (!game) return ['local']
  const accountPlatforms = [...new Set(props.accounts.map((account) => account.platform))]
  const mappedPlatforms = [...new Set(game.platforms)]
  const matching = mappedPlatforms.filter((platform) => accountPlatforms.includes(platform))
  if (matching.length) return matching
  if (mappedPlatforms.length) return mappedPlatforms
  if (accountPlatforms.length) return accountPlatforms
  return ['local']
}

function gameMeta(game: ManualOwnershipGameOption) {
  const parts = [
    `${game.owner_count} ${game.owner_count === 1 ? 'Besitzer:in' : 'Besitzer:innen'}`
  ]
  if (game.release_date) parts.push(new Date(game.release_date).getFullYear().toString())
  if (game.platforms.length) parts.push(game.platforms.map(platformTitle).join(', '))
  return parts.join(' · ')
}

function platformTitle(platform: Platform) {
  const names: Record<string, string> = {
    steam: 'Steam',
    epic: 'Epic Games',
    gog: 'GOG',
    xbox: 'Xbox / Microsoft Store',
    ubisoft: 'Ubisoft Connect',
    ea: 'EA App',
    amazon: 'Amazon Games',
    battle_net: 'Battle.net',
    humble: 'Humble',
    humble_key: 'Humble Key',
    meta: 'Meta / Oculus',
    itch: 'itch.io',
    legacy: 'Legacy Games',
    riot: 'Riot Games',
    rockstar: 'Rockstar Games',
    local: 'Lokal / andere Quelle'
  }
  return names[platform] || platform
}

function readableError(value: unknown) {
  const raw = value instanceof Error ? value.message : String(value)
  try {
    const parsed = JSON.parse(raw)
    return parsed.detail || parsed.message || raw
  } catch {
    return raw.replace(/^Error:\s*/i, '')
  }
}
</script>

<style scoped>
.manual-library {
  padding: 16px 0;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.manual-results {
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.manual-result {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: center;
  min-height: 62px;
  padding: 8px 0;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.manual-game-info {
  min-width: 0;
}

.manual-action {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  flex-wrap: wrap;
}

@media (max-width: 680px) {
  .manual-result {
    grid-template-columns: 1fr;
    gap: 6px;
  }

  .manual-action {
    justify-content: flex-start;
  }
}
</style>
