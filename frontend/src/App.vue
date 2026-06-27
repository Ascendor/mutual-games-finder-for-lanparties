<template>
  <v-app>
    <v-navigation-drawer permanent width="260">
      <v-list nav density="compact">
        <v-list-item title="LAN Party Game Finder" subtitle="Local library matcher" />
        <v-divider class="my-2" />
        <v-list-item v-for="item in items" :key="item.to" :to="item.to" :prepend-icon="item.icon" :title="item.title" />
      </v-list>
    </v-navigation-drawer>
    <v-main>
      <v-progress-linear v-if="pendingRequests > 0" indeterminate color="primary" class="global-loader" aria-label="Daten werden geladen" />
      <router-view />
    </v-main>
  </v-app>
</template>

<script setup lang="ts">
import { pendingRequests } from './api'

const items = [
  { title: 'Start', icon: 'mdi-home-outline', to: '/' },
  { title: 'Dashboard', icon: 'mdi-view-dashboard-outline', to: '/dashboard' },
  { title: 'Teilnehmer:innen', icon: 'mdi-account-group-outline', to: '/participants' },
  { title: 'Accounts & Logins', icon: 'mdi-key-chain-variant', to: '/logins' },
  { title: 'Spiele', icon: 'mdi-gamepad-variant-outline', to: '/games' },
  { title: 'Was können wir spielen?', icon: 'mdi-star-outline', to: '/recommendations' },
  { title: 'Mitspieler:in finden', icon: 'mdi-account-search-outline', to: '/find-players' },
  { title: 'Synchronisation', icon: 'mdi-sync', to: '/sync' },
  { title: 'Administration', icon: 'mdi-shield-cog-outline', to: '/admin' }
]
</script>

<style scoped>
.global-loader {
  position: fixed;
  z-index: 1000;
  width: calc(100% - 260px);
}
</style>


