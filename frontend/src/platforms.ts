import type { Platform } from './types'

export const loginPlatforms: Platform[] = [
  'steam',
  'epic',
  'gog',
  'ubisoft',
  'xbox',
  'ea',
  'amazon',
  'battle_net',
  'humble',
  'meta'
]

export const accountPlatforms: Platform[] = [
  'steam',
  'epic',
  'gog',
  'xbox',
  'ubisoft',
  'ea'
]

const platformTitles: Record<string, string> = {
  steam: 'Steam',
  epic: 'Epic Games',
  gog: 'GOG',
  xbox: 'Xbox Live',
  ubisoft: 'Ubisoft Connect',
  ea: 'EA App',
  amazon: 'Amazon Games',
  battle_net: 'Battle.net',
  bethesda: 'Bethesda',
  gamejolt: 'Game Jolt',
  humble: 'Humble',
  humble_key: 'Humble Key',
  meta: 'Meta / Oculus',
  itch: 'itch.io',
  legacy: 'Legacy Games',
  nintendo: 'Nintendo',
  playstation: 'PlayStation',
  riot: 'Riot Games',
  rockstar: 'Rockstar Games',
  local: 'Lokal'
}

const platformIcons: Record<string, string> = {
  steam: 'mdi-steam',
  epic: 'mdi-gamepad-variant-outline',
  gog: 'mdi-gamepad-square-outline',
  ubisoft: 'mdi-alpha-u-circle-outline',
  xbox: 'mdi-microsoft-xbox',
  ea: 'mdi-alpha-e-circle-outline',
  amazon: 'mdi-amazon',
  battle_net: 'mdi-battle-net',
  humble: 'mdi-alpha-h-circle-outline',
  humble_key: 'mdi-key-variant',
  meta: 'mdi-virtual-reality',
  itch: 'mdi-gamepad-variant-outline',
  legacy: 'mdi-gamepad-variant-outline',
  local: 'mdi-harddisk'
}

export function platformTitle(platform: Platform | '') {
  return platform ? platformTitles[platform] || platform : ''
}

export function platformIcon(platform: Platform | '') {
  return platform ? platformIcons[platform] || 'mdi-gamepad-variant-outline' : 'mdi-gamepad-variant-outline'
}
