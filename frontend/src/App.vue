<template>
  <v-app>
    <v-navigation-drawer v-if="route.path !== '/player'" permanent width="260">
      <v-list v-model:opened="openedGroups" nav density="compact">
        <v-list-item :title="branding.display_name" :subtitle="branding.subtitle" />
        <v-divider class="my-2" />
        <v-list-item
          to="/player"
          prepend-icon="mdi-account-circle-outline"
          :title="currentParticipant?.nickname || currentParticipantName || 'Spieler auswählen'"
          subtitle="Spieler wechseln"
        />
        <v-divider class="my-2" />
        <v-list-item v-for="item in mainItems" :key="item.to" :to="item.to" :prepend-icon="item.icon" :title="item.title" />
        <v-list-group value="administration">
          <template #activator="{ props }">
            <v-list-item v-bind="props" prepend-icon="mdi-shield-cog-outline" title="Administration" />
          </template>
          <v-list-item to="/admin" prepend-icon="mdi-shield-key-outline" title="Adminbereich" />
          <template v-if="adminUnlocked">
            <v-list-item to="/admin/dashboard" prepend-icon="mdi-view-dashboard-outline" title="Orga-Dashboard" />
            <v-list-item to="/admin/nutzung" prepend-icon="mdi-chart-box-outline" title="Nutzungsanalyse" />
            <v-list-item to="/admin/logins" prepend-icon="mdi-key-chain-variant" title="Accounts & Logins" />
            <v-list-item to="/admin/participants" prepend-icon="mdi-account-group-outline" title="Teilnehmer:innen" />
            <v-list-item to="/admin/games" prepend-icon="mdi-gamepad-variant-outline" title="Spiele" />
            <v-list-item to="/admin/sync" prepend-icon="mdi-sync" title="Synchronisation" />
            <v-list-item prepend-icon="mdi-lock-outline" title="Administration sperren" @click="lockAdministration" />
          </template>
        </v-list-group>
      </v-list>
    </v-navigation-drawer>
    <v-main class="app-main">
      <v-progress-linear
        v-if="pendingRequests > 0"
        indeterminate
        color="primary"
        class="global-loader"
        :class="{ 'global-loader--full': route.path === '/player' }"
        aria-label="Daten werden geladen"
      />
      <div class="app-content">
        <router-view />
      </div>
      <footer class="app-footer">
        <router-link to="/legal">Datenschutz &amp; Hinweise</router-link>
        <span aria-hidden="true">·</span>
        <span>Metadaten:</span>
        <a href="https://www.igdb.com/" target="_blank" rel="noopener noreferrer">IGDB</a>
        <span aria-hidden="true">·</span>
        <a href="https://rawg.io/" target="_blank" rel="noopener noreferrer">RAWG</a>
        <span aria-hidden="true">·</span>
        <a
          :href="branding.source_url"
          target="_blank"
          rel="noopener noreferrer"
        >
          Quellcode
        </a>
      </footer>
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { adminUnlocked, lockAdmin } from './adminAccess'
import { pendingRequests } from './api'
import { branding } from './branding'
import { currentParticipantId, currentParticipantName } from './playerIdentity'
import { useLanStore } from './store'

const route = useRoute()
const router = useRouter()
const store = useLanStore()
const openedGroups = ref<string[]>([])
const currentParticipant = computed(() =>
  store.participants.find((participant) => participant.id === currentParticipantId.value)
)

const mainItems = [
  { title: 'Start', icon: 'mdi-home-outline', to: '/' },
  { title: 'Was können wir spielen?', icon: 'mdi-star-outline', to: '/recommendations' },
  { title: 'Mitspieler:in finden', icon: 'mdi-account-search-outline', to: '/find-players' },
  { title: 'Meine Spiele', icon: 'mdi-format-list-bulleted', to: '/my-games' },
  { title: 'Meine Accounts & Logins', icon: 'mdi-key-chain-variant', to: '/logins' },
]

watch(
  () => route.path,
  (path) => {
    if (path.startsWith('/admin')) openedGroups.value = ['administration']
  },
  { immediate: true }
)

function lockAdministration() {
  lockAdmin()
  if (route.path !== '/admin') void router.push('/admin')
}
</script>

<style scoped>
.global-loader {
  position: fixed;
  z-index: 1000;
  width: calc(100% - 260px);
}

.global-loader--full {
  width: 100%;
}

.app-main {
  min-height: 100vh;
}

.app-content {
  min-height: calc(100vh - 42px);
}

.app-footer {
  min-height: 42px;
  padding: 8px 24px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: rgba(var(--v-theme-on-background), 0.68);
  font-size: 0.78rem;
}

.app-footer a {
  color: rgb(var(--v-theme-primary));
  text-decoration: none;
}

.app-footer a:hover,
.app-footer a:focus-visible {
  text-decoration: underline;
}
</style>
