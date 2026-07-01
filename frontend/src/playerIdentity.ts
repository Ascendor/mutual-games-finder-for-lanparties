import { ref } from 'vue'

const STORAGE_KEY = 'lan-current-participant-id'
const NAME_STORAGE_KEY = 'lan-current-participant-name'
const storage = typeof window === 'undefined' ? null : window.localStorage
const storedId = Number(storage?.getItem(STORAGE_KEY))

export const currentParticipantId = ref<number | null>(
  Number.isInteger(storedId) && storedId > 0 ? storedId : null
)
export const currentParticipantName = ref(storage?.getItem(NAME_STORAGE_KEY) || '')

export function selectParticipant(participantId: number, nickname: string) {
  storage?.setItem(STORAGE_KEY, String(participantId))
  storage?.setItem(NAME_STORAGE_KEY, nickname)
  currentParticipantId.value = participantId
  currentParticipantName.value = nickname
}

export function clearParticipant() {
  storage?.removeItem(STORAGE_KEY)
  storage?.removeItem(NAME_STORAGE_KEY)
  currentParticipantId.value = null
  currentParticipantName.value = ''
}
