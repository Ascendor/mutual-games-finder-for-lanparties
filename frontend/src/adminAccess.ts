import { ref } from 'vue'

const ADMIN_PASSWORD = 'QC4lF93bYgwTHRT4xRynsAIz3San1lDW'
const STORAGE_KEY = 'lan-admin-unlocked'
const storage = typeof window === 'undefined' ? null : window.sessionStorage

export const adminUnlocked = ref(storage?.getItem(STORAGE_KEY) === 'true')

export function tryUnlockAdmin(password: string) {
  if (password !== ADMIN_PASSWORD) return false
  storage?.setItem(STORAGE_KEY, 'true')
  adminUnlocked.value = true
  return true
}

export function lockAdmin() {
  storage?.removeItem(STORAGE_KEY)
  adminUnlocked.value = false
}
