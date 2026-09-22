import { reactive } from 'vue'
import { api } from './api'
import type { AppConfig } from './types'

export const branding = reactive<AppConfig>({
  display_name: 'Mutual Games Finder',
  title: 'Mutual Games Finder - Der Spielefinder',
  subtitle: 'Der Spielefinder',
  source_url: 'https://github.com/Ascendor/mutual-games-finder-for-lanparties',
  upstream_source_url: 'https://github.com/Ascendor/mutual-games-finder-for-lanparties'
})

export async function loadBranding() {
  try {
    Object.assign(branding, await api.appConfig())
  } catch {
    // Keep the application usable with the documented defaults during outages.
  }
  document.title = branding.title
}
