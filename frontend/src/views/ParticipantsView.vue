<template>
  <div class="page">
    <h1 class="text-headline-large mb-4">Teilnehmer</h1>
    <v-row>
      <v-col cols="12" md="4">
        <v-card variant="flat">
          <v-card-title>Teilnehmer anlegen</v-card-title>
          <v-card-text>
            <v-text-field v-model="form.nickname" label="Nickname" density="compact" />
            <v-text-field v-model="form.real_name" label="Real Name" density="compact" />
            <v-checkbox v-model="form.present" label="Anwesend" density="compact" />
            <v-textarea v-model="form.notes" label="Notizen" density="compact" rows="3" />
            <v-btn color="primary" prepend-icon="mdi-plus" @click="create">Anlegen</v-btn>
          </v-card-text>
        </v-card>
      </v-col>
      <v-col cols="12" md="8">
        <v-data-table class="compact-table" :headers="headers" :items="rows" :loading="store.loading" loading-text="Teilnehmer werden geladen..." :items-per-page="-1" density="compact" hide-default-footer>
          <template #item.present="{ item }">
            <v-switch :model-value="item.present" color="primary" hide-details @update:model-value="toggle(item.id, Boolean($event))" />
          </template>
          <template #item.playtime_hours="{ item }">{{ item.playtime_hours }} h</template>
        </v-data-table>
      </v-col>
    </v-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { api } from '../api'
import { useLanStore } from '../store'

const store = useLanStore()
const form = reactive({ nickname: '', real_name: '', present: true, notes: '' })
const headers = [
  { title: 'Nickname', key: 'nickname' },
  { title: 'Real Name', key: 'real_name' },
  { title: 'Anwesend', key: 'present' },
  { title: 'Bibliothek', key: 'library_size' },
  { title: 'Spielzeit', key: 'playtime_hours' }
]
const rows = computed(() =>
  store.participants.map((participant) => ({
    ...participant,
    library_size: librarySize(participant.id),
    playtime_hours: playtime(participant.id)
  }))
)
onMounted(() => store.refresh())

async function create() {
  await api.createParticipant(form)
  Object.assign(form, { nickname: '', real_name: '', present: true, notes: '' })
  await store.refresh()
}

async function toggle(id: number, present: boolean) {
  await api.updateParticipant(id, { present })
  await store.refresh()
}

const librarySize = (id: number) => new Set(store.ownerships.filter((own) => own.participant_id === id).map((own) => own.game_id)).size
const playtime = (id: number) => Math.round(store.ownerships.filter((own) => own.participant_id === id).reduce((sum, own) => sum + own.playtime_minutes, 0) / 60)
</script>
