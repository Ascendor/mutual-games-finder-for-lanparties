import { defineStore } from 'pinia'
import { api } from './api'
import type { Account, Game, Ownership, Participant, Recommendation, SyncRun } from './types'

export const useLanStore = defineStore('lan', {
  state: () => ({
    participants: [] as Participant[],
    accounts: [] as Account[],
    games: [] as Game[],
    ownerships: [] as Ownership[],
    popular: [] as Recommendation[],
    lan: [] as Recommendation[],
    present: [] as Recommendation[],
    syncRuns: [] as SyncRun[],
    loading: false,
    error: ''
  }),
  getters: {
    presentParticipants: (state) => state.participants.filter((participant) => participant.present),
    totalPlaytime: (state) => state.ownerships.reduce((sum, own) => sum + own.playtime_minutes, 0)
  },
  actions: {
    async refresh() {
      this.loading = true
      this.error = ''
      try {
        const [participants, accounts, games, ownerships, popular, lan, present, syncRuns] = await Promise.all([
          api.participants(),
          api.accounts(),
          api.games(),
          api.ownerships(),
          api.recommendations('popular'),
          api.recommendations('lan'),
          api.recommendations('present'),
          api.syncRuns()
        ])
        Object.assign(this, { participants, accounts, games, ownerships, popular, lan, present, syncRuns })
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    }
  }
})

