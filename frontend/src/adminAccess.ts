import { ref } from 'vue'

import { api } from './api'

const STORAGE_KEY = 'lan-admin-unlocked-v2'
const storage = typeof window === 'undefined' ? null : window.sessionStorage

export const adminUnlocked = ref(storage?.getItem(STORAGE_KEY) === 'true')

export async function tryUnlockAdmin(password: string) {
  let result: { unlocked: boolean }
  try {
    result = await api.adminUnlock(password)
  } catch (err) {
    const raw = err instanceof Error ? err.message : String(err)
    try {
      const parsed = JSON.parse(raw)
      if (parsed.detail === 'invalid admin password') return false
    } catch {
      // Keep the original error for non-API failures.
    }
    throw err
  }
  if (!result.unlocked) return false
  storage?.setItem(STORAGE_KEY, 'true')
  adminUnlocked.value = true
  return true
}

export function lockAdmin() {
  storage?.removeItem(STORAGE_KEY)
  adminUnlocked.value = false
}
