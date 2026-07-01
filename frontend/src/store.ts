import { defineStore } from 'pinia'
import { api } from './api'
import type { Account, Game, GameOption, Ownership, Participant, Recommendation, SyncRun } from './types'

const participantNameCollator = new Intl.Collator('de', {
  sensitivity: 'base',
  numeric: true
})

function sortParticipants(participants: Participant[]) {
  return [...participants].sort((left, right) =>
    participantNameCollator.compare(left.nickname, right.nickname)
  )
}

export const useLanStore = defineStore('lan', {
  state: () => ({
    participants: [] as Participant[],
    accounts: [] as Account[],
    games: [] as Game[],
    gameOptions: [] as GameOption[],
    ownerships: [] as Ownership[],
    popular: [] as Recommendation[],
    newForGroup: [] as Recommendation[],
    lan: [] as Recommendation[],
    present: [] as Recommendation[],
    syncRuns: [] as SyncRun[],
    loading: false,
    error: ''
  }),
  getters: {
    sortedParticipants: (state) => sortParticipants(state.participants),
    presentParticipants: (state) => sortParticipants(
      state.participants.filter((participant) => participant.present)
    ),
    totalPlaytime: (state) => state.ownerships.reduce((sum, own) => sum + own.playtime_minutes, 0)
  },
  actions: {
    async refreshParticipants() {
      this.loading = true
      this.error = ''
      try {
        this.participants = await api.participants()
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
    async refreshHome() {
      this.loading = true
      this.error = ''
      try {
        const [participants, gameOptions] = await Promise.all([
          api.participants(),
          api.gameOptions()
        ])
        Object.assign(this, { participants, gameOptions })
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    },
    async refresh() {
      this.loading = true
      this.error = ''
      try {
        const [participants, accounts, games, ownerships, popular, newForGroup, lan, present, syncRuns] = await Promise.all([
          api.participants(),
          api.accounts(),
          api.games(),
          api.ownerships(),
          api.recommendations('popular', 100),
          api.recommendations('new', 100),
          api.recommendations('lan', 100),
          api.recommendations('present', 100),
          api.syncRuns()
        ])
        Object.assign(this, { participants, accounts, games, ownerships, popular, newForGroup, lan, present, syncRuns })
      } catch (error) {
        this.error = error instanceof Error ? error.message : String(error)
      } finally {
        this.loading = false
      }
    }
  }
})
