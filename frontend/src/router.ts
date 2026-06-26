import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/HomeView.vue') },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/participants', component: () => import('./views/ParticipantsView.vue') },
    { path: '/accounts', redirect: '/logins' },
    { path: '/logins', component: () => import('./views/ProviderLoginsView.vue') },
    { path: '/games', component: () => import('./views/GamesView.vue') },
    { path: '/recommendations', component: () => import('./views/RecommendationsView.vue') },
    { path: '/find-players', component: () => import('./views/FindPlayersView.vue') },
    { path: '/sync', component: () => import('./views/SyncView.vue') },
    { path: '/admin', component: () => import('./views/AdminView.vue') }
  ]
})





