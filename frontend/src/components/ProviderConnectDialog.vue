<template>
  <v-dialog
    :model-value="modelValue"
    max-width="720"
    persistent
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card v-if="target">
      <v-toolbar color="surface" density="comfortable">
        <v-icon class="ml-4">{{ platformIcon(target.platform) }}</v-icon>
        <v-toolbar-title>{{ platformTitle(target.platform) }} für {{ target.participant.nickname }}</v-toolbar-title>
        <v-btn icon="mdi-close" :disabled="busy" aria-label="Dialog schließen" @click="close" />
      </v-toolbar>

      <v-progress-linear :model-value="progress" color="primary" height="4" />
      <div class="step-labels px-6 pt-4">
        <span :class="{ active: stage >= 1 }">Vorbereiten</span>
        <span :class="{ active: stage >= 2 }">Anmelden</span>
        <span :class="{ active: stage >= 3 }">Spiele laden</span>
        <span :class="{ active: stage >= 4 }">Fertig</span>
      </div>

      <v-card-text class="wizard-content">
        <v-alert v-if="error" type="error" variant="tonal" class="mb-4">
          {{ error }}
        </v-alert>

        <template v-if="stage === 1">
          <h2 class="text-h6 mb-3">{{ introTitle }}</h2>
          <p class="text-body-1 mb-4">{{ introText }}</p>
          <v-list density="compact" class="mb-2">
            <v-list-item
              v-for="(item, index) in introSteps"
              :key="item"
              :prepend-icon="`mdi-numeric-${index + 1}-circle-outline`"
              :title="item"
            />
          </v-list>
          <v-alert v-if="target.platform === 'ea'" type="info" variant="tonal">
            Der einfachste Weg für diese Plattform ist ein Playnite-Backup. Du kannst es im nächsten Schritt direkt auswählen.
          </v-alert>
        </template>

        <template v-else-if="stage === 2">
          <template v-if="target.platform === 'steam'">
            <h2 class="text-h6 mb-2">Steam-Profil angeben</h2>
            <p class="text-body-2 text-medium-emphasis mb-4">
              Öffne dein Steam-Profil und kopiere die Adresse aus der Browserzeile. Eine SteamID64 funktioniert ebenfalls.
            </p>
            <v-text-field
              v-model="steamProfile"
              label="Steam-Profil-Link oder SteamID64"
              prepend-inner-icon="mdi-steam"
              autocomplete="off"
              autofocus
              :disabled="busy"
              @keyup.enter="submit"
            />
          </template>

          <template v-else-if="target.platform === 'epic'">
            <h2 class="text-h6 mb-2">Bei Epic Games anmelden</h2>
            <p class="text-body-2 mb-4">
              Öffne die Loginseite, melde dich bei Epic an und kopiere anschließend den gesamten Inhalt der angezeigten Seite.
            </p>
            <v-btn
              :href="loginStart?.login_url"
              target="_blank"
              color="primary"
              prepend-icon="mdi-open-in-new"
              class="mb-4"
            >
              Epic-Login öffnen
            </v-btn>
            <v-textarea
              v-model="code"
              label="Kopierten Seiteninhalt einfügen"
              rows="4"
              auto-grow
              :disabled="busy"
              hint="JSON, nur der Code oder Text mit Anführungszeichen funktionieren."
              persistent-hint
            />
            <v-btn variant="text" prepend-icon="mdi-content-paste" class="mt-2" @click="pasteCode">
              Aus Zwischenablage einfügen
            </v-btn>
          </template>

          <template v-else-if="target.platform === 'gog'">
            <h2 class="text-h6 mb-2">Bei GOG anmelden</h2>
            <p class="text-body-2 mb-4">
              Öffne GOG und melde dich an. Danach erscheint normalerweise eine leere weiße Seite. Das ist richtig:
              Kopiere die vollständige Adresse dieser weißen Seite aus der Browserzeile und füge sie unten ein.
            </p>
            <v-btn
              :href="loginStart?.login_url"
              target="_blank"
              color="primary"
              prepend-icon="mdi-open-in-new"
              class="mb-4"
            >
              GOG-Login öffnen
            </v-btn>
            <v-textarea
              v-model="code"
              label="Adresse der weißen Seite einfügen"
              rows="3"
              auto-grow
              :disabled="busy"
              hint="Nicht den Seiteninhalt kopieren. Benötigt wird die URL oben in der Browserzeile."
              persistent-hint
            />
            <v-btn variant="text" prepend-icon="mdi-content-paste" class="mt-2" @click="pasteCode">
              Aus Zwischenablage einfügen
            </v-btn>
          </template>

          <template v-else-if="target.platform === 'ubisoft'">
            <h2 class="text-h6 mb-2">{{ needs2fa ? 'Zwei-Faktor-Code eingeben' : 'Bei Ubisoft anmelden' }}</h2>
            <p class="text-body-2 text-medium-emphasis mb-4">
              {{ needs2fa ? 'Öffne deine Authenticator-App oder E-Mail und gib den aktuellen Code ein.' : 'Die Anmeldung erfolgt direkt. Deine Zugangsdaten werden nicht in der Datenbank gespeichert.' }}
            </p>
            <v-text-field
              v-if="!needs2fa"
              v-model="ubisoft.email"
              label="E-Mail"
              autocomplete="username"
              prepend-inner-icon="mdi-email-outline"
              :disabled="busy"
            />
            <v-text-field
              v-if="!needs2fa"
              v-model="ubisoft.password"
              label="Passwort"
              type="password"
              autocomplete="current-password"
              prepend-inner-icon="mdi-lock-outline"
              :disabled="busy"
              @keyup.enter="submit"
            />
            <v-text-field
              v-if="needs2fa"
              v-model="ubisoft.twoFactorCode"
              label="2FA-Code"
              inputmode="numeric"
              autocomplete="one-time-code"
              prepend-inner-icon="mdi-two-factor-authentication"
              :disabled="busy"
              autofocus
              @keyup.enter="submit"
            />
          </template>

          <template v-else-if="target.platform === 'xbox'">
            <h2 class="text-h6 mb-2">Bei Microsoft anmelden</h2>
            <p class="text-body-2 mb-4">
              Öffne die Microsoft-Seite und melde dich mit dem Konto an, das zu deinem Xbox-Profil gehört.
              Gib dort diesen einmaligen Code ein:
            </p>
            <div class="xbox-code-row mb-4">
              <span class="xbox-device-code">{{ loginStart?.user_code }}</span>
              <v-btn
                icon="mdi-content-copy"
                variant="text"
                :aria-label="codeCopied ? 'Code kopiert' : 'Code kopieren'"
                :title="codeCopied ? 'Code kopiert' : 'Code kopieren'"
                @click="copyXboxCode"
              />
            </div>
            <v-btn
              :href="loginStart?.verification_uri || loginStart?.login_url"
              target="_blank"
              color="primary"
              prepend-icon="mdi-open-in-new"
              size="large"
              class="mb-4"
            >
              Microsoft-Anmeldung öffnen
            </v-btn>
            <v-alert type="info" variant="tonal">
              <template v-if="xboxChecking">
                <v-progress-circular indeterminate size="18" width="2" class="mr-2" />
                Anmeldung wird geprüft ...
              </template>
              <template v-else>
                Nach der Bestätigung geht es hier automatisch weiter. Du kannst den Status auch unten sofort prüfen.
              </template>
            </v-alert>
          </template>

          <template v-else-if="target.platform === 'ea'">
            <h2 class="text-h6 mb-2">Playnite-Backup importieren</h2>
            <p class="text-body-2 mb-4">
              Erstelle in Playnite ein Backup und wähle die ZIP-Datei hier aus. Die enthaltenen Spiele werden {{ target.participant.nickname }} zugeordnet.
            </p>
            <v-file-input
              v-model="playniteFile"
              label="Playnite-Backup auswählen"
              accept="application/zip,.zip,application/json,.json"
              prepend-icon="mdi-file-upload-outline"
              :disabled="busy"
            />
            <v-btn
              color="primary"
              prepend-icon="mdi-import"
              :disabled="!selectedPlayniteFile"
              :loading="busy"
              @click="importPlaynite"
            >
              Backup importieren
            </v-btn>

          </template>

          <template v-else-if="target.platform === 'amazon'">
            <h2 class="text-h6 mb-2">Bei Amazon anmelden</h2>
            <p class="text-body-2 mb-4">
              Melde dich auf der geöffneten Amazon-Seite an. Kopiere danach die vollständige Adresse aus der Browserzeile,
              auch wenn dort nur die normale Amazon-Seite erscheint.
            </p>
            <v-btn
              :href="loginStart?.login_url"
              target="_blank"
              color="primary"
              prepend-icon="mdi-open-in-new"
              class="mb-4"
            >
              Amazon-Anmeldung öffnen
            </v-btn>
            <v-textarea
              v-model="code"
              label="Adresse nach der Anmeldung"
              rows="3"
              auto-grow
              :disabled="busy"
              hint="Die App liest den Bestätigungscode selbst aus der vollständigen URL."
              persistent-hint
            />
            <v-btn variant="text" prepend-icon="mdi-content-paste" class="mt-2" @click="pasteCode">
              Aus Zwischenablage einfügen
            </v-btn>
          </template>

          <template v-else-if="isBrowserSessionPlatform">
            <h2 class="text-h6 mb-2">{{ platformTitle(target.platform) }}-Sitzung übernehmen</h2>
            <v-alert type="warning" variant="tonal" class="mb-4">
              Diese direkte Anbindung nutzt eine inoffizielle Browser-Sitzung. Sie kann nach Änderungen des Anbieters
              vorübergehend ausfallen und muss nach Ablauf der Sitzung erneut verbunden werden.
            </v-alert>
            <ol class="session-steps mb-4">
              <li>Öffne die Loginseite und melde dich vollständig an.</li>
              <li>Drücke in Firefox <strong>F12</strong>, öffne <strong>Netzwerkanalyse</strong> und lade die Seite neu.</li>
              <li>Klicke die oberste Anfrage mit Status 200 rechts an und wähle <strong>Wert kopieren → Als cURL kopieren</strong>.</li>
              <li>Füge die komplette kopierte Anfrage unten ein. Die App findet die Sitzungsdaten selbst.</li>
            </ol>
            <v-btn
              :href="loginStart?.login_url"
              target="_blank"
              color="primary"
              prepend-icon="mdi-open-in-new"
              class="mb-4"
            >
              {{ platformTitle(target.platform) }} öffnen
            </v-btn>
            <v-textarea
              v-model="code"
              label="Komplette cURL-Anfrage einfügen"
              rows="5"
              auto-grow
              :disabled="busy"
              hint="Zugangsdaten werden nicht benötigt. Die gespeicherte Sitzung gilt nur für diesen Teilnehmer."
              persistent-hint
            />
            <v-btn variant="text" prepend-icon="mdi-content-paste" class="mt-2" @click="pasteCode">
              Aus Zwischenablage einfügen
            </v-btn>
          </template>
        </template>

        <template v-else-if="stage === 3">
          <div class="sync-state">
            <v-progress-circular v-if="busy" indeterminate color="primary" size="48" />
            <v-icon v-else-if="error" color="error" size="48">mdi-alert-circle-outline</v-icon>
            <v-icon v-else color="primary" size="48">mdi-cloud-download-outline</v-icon>
            <h2 class="text-h6 mt-4">Spiele werden geladen</h2>
            <p class="text-body-2 text-medium-emphasis">
              Die Verbindung steht. Jetzt wird die Bibliothek einmal vollständig synchronisiert.
            </p>
          </div>
        </template>

        <template v-else>
          <div class="sync-state">
            <v-icon color="success" size="56">mdi-check-circle-outline</v-icon>
            <h2 class="text-h6 mt-4">Alles erledigt</h2>
            <p class="text-body-1">
              {{ resultMessage }}
            </p>
          </div>
        </template>
      </v-card-text>

      <v-divider />
      <v-card-actions class="px-6 py-4">
        <v-btn v-if="stage < 4" variant="text" :disabled="busy" @click="close">Abbrechen</v-btn>
        <v-spacer />
        <v-btn v-if="stage === 1" color="primary" append-icon="mdi-arrow-right" :loading="busy" @click="prepare">
          Weiter
        </v-btn>
        <v-btn
          v-else-if="stage === 2 && target.platform !== 'ea' && target.platform !== 'xbox'"
          color="primary"
          append-icon="mdi-arrow-right"
          :disabled="!canSubmit"
          :loading="busy"
          @click="submit"
        >
          {{ needs2fa ? 'Code bestätigen' : target.platform === 'steam' ? 'Verbinden und Spiele laden' : 'Anmeldung abschließen' }}
        </v-btn>
        <v-btn
          v-else-if="stage === 2 && target.platform === 'xbox'"
          color="primary"
          prepend-icon="mdi-refresh"
          :disabled="!loginStart?.user_code"
          :loading="xboxChecking"
          @click="pollXboxLogin"
        >
          Anmeldestatus prüfen
        </v-btn>
        <v-btn v-else-if="stage === 3 && error && !busy" color="primary" prepend-icon="mdi-refresh" @click="syncLibrary">
          Erneut versuchen
        </v-btn>
        <v-btn v-else-if="stage === 4" color="primary" prepend-icon="mdi-check" @click="finish">
          Fertig
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { api } from '../api'
import type { Account, Participant, Platform, ProviderLoginStart } from '../types'

interface ProviderTarget {
  participant: Participant
  platform: Platform
  account?: Account
}

const props = defineProps<{
  modelValue: boolean
  target: ProviderTarget | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  finished: []
}>()

const stage = ref(1)
const busy = ref(false)
const error = ref('')
const account = ref<Account | undefined>()
const loginStart = ref<ProviderLoginStart>()
const code = ref('')
const steamProfile = ref('')
const needs2fa = ref(false)
const resultMessage = ref('')
const playniteFile = ref<File | File[] | null>(null)
const ubisoft = reactive({ email: '', password: '', twoFactorCode: '' })
const xboxChecking = ref(false)
const codeCopied = ref(false)
let xboxPollTimer: ReturnType<typeof setTimeout> | undefined

const progress = computed(() => stage.value * 25)
const selectedPlayniteFile = computed(() => {
  const value = playniteFile.value
  return Array.isArray(value) ? value[0] : value
})
const canSubmit = computed(() => {
  const platform = props.target?.platform
  if (platform === 'steam') return Boolean(extractSteamId(steamProfile.value))
  if (platform === 'ubisoft') {
    return needs2fa.value
      ? Boolean(ubisoft.twoFactorCode.trim())
      : Boolean(ubisoft.email.trim() && ubisoft.password)
  }
  if (platform === 'ea' || platform === 'xbox') return false
  return Boolean(code.value.trim())
})
const isBrowserSessionPlatform = computed(() =>
  ['battle_net', 'humble', 'meta'].includes(props.target?.platform || '')
)
const introTitle = computed(() => `${platformTitle(props.target?.platform || '')} verbinden`)
const introText = computed(() => {
  const platform = props.target?.platform
  if (platform === 'steam') return 'Du brauchst nur den Link zu deinem öffentlichen Steam-Profil. Danach werden deine Spiele automatisch geladen.'
  if (platform === 'epic') return 'Die Anmeldung findet auf der offiziellen Epic-Seite statt. Danach gibst du die angezeigte Bestätigung hier zurück.'
  if (platform === 'gog') return 'Die Anmeldung findet auf der offiziellen GOG-Seite statt. Danach übernimmt die App den Bestätigungscode.'
  if (platform === 'ubisoft') return 'Du meldest dich direkt mit deinem Ubisoft-Konto an. Falls 2FA aktiv ist, führt der Assistent automatisch zum nächsten Schritt.'
  if (platform === 'xbox') return 'Du bestätigst die Verbindung einmalig bei Microsoft. Danach lädt die App automatisch deine auf dem PC gespielten Xbox-Titel.'
  if (platform === 'amazon') return 'Du meldest dich einmalig bei Amazon an. Die App speichert eine erneuerbare Geräteanmeldung und lädt deine Amazon-Games-Bibliothek.'
  if (platform === 'battle_net') return 'Die App übernimmt einmalig deine angemeldete Battle.net-Browsersitzung und kann damit deine PC-Spiele laden.'
  if (platform === 'humble') return 'Die App übernimmt einmalig deine angemeldete Humble-Browsersitzung und lädt daraus deine Windows-Spiele.'
  if (platform === 'meta') return 'Die App übernimmt einmalig deine angemeldete Meta-Sitzung und lädt deine Rift-, PCVR- und Quest-Bibliothek.'
  return 'Für diese Plattform ist der Playnite-Import derzeit der verlässlichste und einfachste Weg.'
})
const introSteps = computed(() => {
  const platform = props.target?.platform
  if (platform === 'steam') return ['Steam-Profil-Link einfügen', 'Bibliothek automatisch laden', 'Fertig']
  if (platform === 'epic' || platform === 'gog') return ['Offizielle Loginseite öffnen', 'Bestätigung kopieren und einfügen', 'Bibliothek automatisch laden']
  if (platform === 'ubisoft') return ['E-Mail und Passwort eingeben', 'Falls nötig 2FA bestätigen', 'Bibliothek automatisch laden']
  if (platform === 'xbox') return ['Einmaligen Code anzeigen', 'Bei Microsoft bestätigen', 'Bibliothek automatisch laden']
  if (platform === 'amazon') return ['Amazon-Anmeldung öffnen', 'Adresse zurückgeben', 'Bibliothek automatisch laden']
  if (['battle_net', 'humble', 'meta'].includes(platform || '')) return ['Anbieterseite öffnen', 'Browser-Anfrage kopieren', 'Bibliothek automatisch laden']
  return ['Playnite-Backup auswählen', 'Backup importieren', 'Spiele prüfen']
})

watch(
  () => props.modelValue,
  (open) => {
    clearXboxPoll()
    if (!open || !props.target) return
    stage.value = 1
    busy.value = false
    error.value = ''
    account.value = props.target.account
    loginStart.value = undefined
    code.value = ''
    steamProfile.value = props.target.platform === 'steam' && props.target.account && !props.target.account.account_id.startsWith('playnite:')
      ? props.target.account.account_id
      : ''
    needs2fa.value = false
    resultMessage.value = ''
    playniteFile.value = null
    xboxChecking.value = false
    codeCopied.value = false
    Object.assign(ubisoft, { email: '', password: '', twoFactorCode: '' })
  }
)

async function prepare() {
  if (!props.target) return
  error.value = ''
  if (props.target.platform === 'steam') {
    stage.value = 2
    return
  }
  busy.value = true
  try {
    if (props.target.platform === 'ea') {
      stage.value = 2
      return
    }
    account.value = await ensureAccount()
    loginStart.value = await api.startProviderLogin(account.value.id)
    stage.value = 2
    if (props.target.platform === 'xbox') {
      scheduleXboxPoll(loginStart.value.interval || 5)
    }
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busy.value = false
  }
}

async function ensureAccount() {
  if (!props.target) throw new Error('Kein Teilnehmer ausgewählt.')
  if (account.value) return account.value
  return api.createAccount({
    participant_id: props.target.participant.id,
    platform: props.target.platform,
    account_id: '',
    display_name: platformTitle(props.target.platform)
  })
}

async function submit() {
  if (!props.target) return
  busy.value = true
  error.value = ''
  try {
    if (props.target.platform === 'steam') {
      const steamId = extractSteamId(steamProfile.value)
      if (!steamId) throw new Error('Bitte einen Steam-Profil-Link oder eine 17-stellige SteamID64 eingeben.')
      account.value = await api.createAccount({
        participant_id: props.target.participant.id,
        platform: 'steam',
        account_id: steamId,
        display_name: props.target.participant.nickname
      })
      await syncLibrary()
      return
    }

    account.value = await ensureAccount()
    const result = props.target.platform === 'ubisoft'
      ? await api.completeProviderLogin(account.value.id, {
          email: ubisoft.email.trim(),
          password: ubisoft.password,
          two_factor_code: ubisoft.twoFactorCode.trim() || undefined
        })
      : await api.completeProviderLogin(account.value.id, { code: code.value })

    if (result.needs_2fa) {
      needs2fa.value = true
      ubisoft.twoFactorCode = ''
      error.value = ''
      return
    }
    await syncLibrary()
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busy.value = false
  }
}

async function syncLibrary() {
  if (!account.value) return
  stage.value = 3
  busy.value = true
  error.value = ''
  try {
    const result = await api.syncAccount(account.value.id)
    if (!result.success) throw new Error(result.message || 'Die Bibliothek konnte nicht geladen werden.')
    resultMessage.value = `${result.imported_games} Spiele wurden erfolgreich synchronisiert.`
    stage.value = 4
    emit('finished')
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busy.value = false
  }
}

async function importPlaynite() {
  if (!props.target || !selectedPlayniteFile.value) return
  busy.value = true
  error.value = ''
  try {
    const result = await api.importPlaynite(props.target.participant.id, selectedPlayniteFile.value)
    resultMessage.value = `${result.imported_games} Spiele wurden aus Playnite importiert.`
    stage.value = 4
    emit('finished')
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busy.value = false
  }
}

function scheduleXboxPoll(delaySeconds: number) {
  clearXboxPoll()
  xboxPollTimer = setTimeout(() => {
    void pollXboxLogin()
  }, Math.max(5, delaySeconds) * 1000)
}

function clearXboxPoll() {
  if (xboxPollTimer) {
    clearTimeout(xboxPollTimer)
    xboxPollTimer = undefined
  }
}

async function pollXboxLogin() {
  if (!account.value || xboxChecking.value || !props.modelValue) return
  clearXboxPoll()
  xboxChecking.value = true
  error.value = ''
  try {
    const result = await api.pollProviderLogin(account.value.id)
    if (result.authenticated) {
      await syncLibrary()
      return
    }
    scheduleXboxPoll(result.interval || loginStart.value?.interval || 5)
  } catch (err) {
    error.value = readableError(err)
  } finally {
    xboxChecking.value = false
  }
}

async function copyXboxCode() {
  const value = loginStart.value?.user_code
  if (!value) return
  try {
    await navigator.clipboard.writeText(value)
    codeCopied.value = true
  } catch {
    error.value = 'Der Code konnte nicht kopiert werden. Markiere ihn bitte und kopiere ihn mit Strg+C.'
  }
}

async function pasteCode() {
  error.value = ''
  try {
    code.value = await navigator.clipboard.readText()
  } catch {
    error.value = 'Die Zwischenablage konnte nicht gelesen werden. Füge den Inhalt mit Strg+V in das Feld ein.'
  }
}

function extractSteamId(value: string) {
  const cleaned = value.trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '')
  return cleaned.match(/(?:^|profiles\/)(\d{17})(?:\/|$|\?)/)?.[1]
    || cleaned.match(/^\d{17}$/)?.[0]
    || ''
}

function readableError(value: unknown) {
  const raw = value instanceof Error ? value.message : String(value)
  const normalized = raw.toLocaleLowerCase()
  if (normalized.includes('authorization_code_not_for_your_client') || normalized.includes('invalidcredential')) {
    return 'Der Anmeldecode wurde nicht akzeptiert. Öffne die Loginseite erneut und kopiere die neue Antwort vollständig.'
  }
  if (normalized.includes('expired') || normalized.includes('abgelaufen')) {
    return 'Der Anmeldecode ist abgelaufen. Öffne die Loginseite erneut und versuche es mit einem neuen Code.'
  }
  if (normalized.includes('network') || normalized.includes('connection') || normalized.includes('timeout')) {
    return 'Der Anbieter ist gerade nicht erreichbar. Deine bisherigen Daten bleiben erhalten; versuche es später erneut.'
  }
  try {
    const parsed = JSON.parse(raw)
    return parsed.detail || parsed.message || raw
  } catch {
    return raw.replace(/^Error:\s*/i, '')
  }
}

function close() {
  if (busy.value) return
  clearXboxPoll()
  emit('update:modelValue', false)
}

function finish() {
  clearXboxPoll()
  emit('update:modelValue', false)
}

onBeforeUnmount(clearXboxPoll)

function platformTitle(platform: Platform | '') {
  const titles: Record<string, string> = {
    steam: 'Steam',
    epic: 'Epic Games',
    gog: 'GOG',
    ubisoft: 'Ubisoft Connect',
    xbox: 'Xbox Live',
    ea: 'EA App',
    amazon: 'Amazon Games',
    battle_net: 'Battle.net',
    humble: 'Humble',
    meta: 'Meta / Oculus'
  }
  return titles[platform] || platform
}

function platformIcon(platform: Platform) {
  const icons: Record<string, string> = {
    steam: 'mdi-steam',
    epic: 'mdi-gamepad-variant-outline',
    gog: 'mdi-gamepad-square-outline',
    ubisoft: 'mdi-alpha-u-circle-outline',
    xbox: 'mdi-microsoft-xbox',
    ea: 'mdi-alpha-e-circle-outline',
    amazon: 'mdi-amazon',
    battle_net: 'mdi-battle-net',
    humble: 'mdi-alpha-h-circle-outline',
    meta: 'mdi-virtual-reality'
  }
  return icons[platform] || 'mdi-gamepad-variant-outline'
}
</script>

<style scoped>
.wizard-content {
  min-height: 360px;
  padding: 24px;
}

.step-labels {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  color: rgb(var(--v-theme-on-surface-variant));
  font-size: 0.75rem;
}

.session-steps {
  padding-left: 22px;
}

.session-steps li {
  margin-bottom: 8px;
}

.xbox-code-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.xbox-device-code {
  min-width: 0;
  padding: 12px 16px;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 6px;
  background: rgb(var(--v-theme-surface-variant));
  font-family: monospace;
  font-size: 1.6rem;
  font-weight: 700;
  letter-spacing: 0;
  user-select: all;
}

.step-labels span {
  overflow-wrap: anywhere;
}

.step-labels .active {
  color: rgb(var(--v-theme-primary));
  font-weight: 700;
}

.sync-state {
  min-height: 270px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

@media (max-width: 600px) {
  .wizard-content {
    min-height: 420px;
    padding: 18px;
  }
}
</style>
