import { createRouter, createWebHistory } from 'vue-router'
import { adminUnlocked } from './adminAccess'
import { currentParticipantId } from './playerIdentity'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/player', component: () => import('./views/PlayerGateView.vue') },
    { path: '/', component: () => import('./views/HomeView.vue') },
    { path: '/dashboard', component: () => import('./views/DashboardView.vue') },
    { path: '/participants', redirect: '/admin/participants' },
    { path: '/accounts', redirect: '/logins' },
    { path: '/logins', component: () => import('./views/ProviderLoginsView.vue') },
    { path: '/games', redirect: '/admin/games' },
    { path: '/recommendations', component: () => import('./views/RecommendationsView.vue') },
    { path: '/find-players', component: () => import('./views/FindPlayersView.vue') },
    { path: '/sync', redirect: '/admin/sync' },
    { path: '/admin', component: () => import('./views/AdminView.vue') },
    {
      path: '/admin/logins',
      component: () => import('./views/ProviderLoginsView.vue'),
      props: { adminMode: true },
      meta: { requiresAdmin: true }
    },
    {
      path: '/admin/participants',
      component: () => import('./views/ParticipantsView.vue'),
      meta: { requiresAdmin: true }
    },
    {
      path: '/admin/games',
      component: () => import('./views/GamesView.vue'),
      meta: { requiresAdmin: true }
    },
    {
      path: '/admin/sync',
      component: () => import('./views/SyncView.vue'),
      meta: { requiresAdmin: true }
    }
  ]
})

router.beforeEach((to) => {
  if (to.path !== '/player' && !currentParticipantId.value) {
    return { path: '/player', query: { redirect: to.fullPath } }
  }
  if (to.meta.requiresAdmin && !adminUnlocked.value) {
    return { path: '/admin', query: { redirect: to.fullPath } }
  }
})
