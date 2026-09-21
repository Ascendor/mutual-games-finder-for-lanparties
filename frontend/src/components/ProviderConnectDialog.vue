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
        </template>

        <template v-else-if="stage === 2">
          <template v-if="target.platform === 'steam'">
            <h2 class="text-h6 mb-3">Wie möchtest du Steam verbinden?</h2>
            <v-btn-toggle
              v-model="steamConnectionMode"
              mandatory
              divided
              color="primary"
              variant="outlined"
              class="steam-mode-toggle mb-5"
            >
              <v-btn value="qr" prepend-icon="mdi-qrcode-scan">QR-Anmeldung</v-btn>
              <v-btn value="openid" prepend-icon="mdi-open-in-new">Browser-Anmeldung</v-btn>
              <v-btn value="community" prepend-icon="mdi-card-account-details-outline">Community-ID</v-btn>
            </v-btn-toggle>
            <p class="text-caption text-medium-emphasis mb-4">
              Einzelheiten zur Speicherung findest du unter
              <a href="/legal" target="_blank" rel="noopener noreferrer">Datenschutz &amp; Hinweise</a>.
            </p>

            <template v-if="steamConnectionMode === 'qr'">
              <v-alert type="info" variant="tonal" class="mb-4">
                <div class="font-weight-bold mb-1">Komfortabel und vollständig</div>
                Scanne den QR-Code mit der Steam-App und bestätige die Anmeldung. Dein Passwort wird nie an die App
                übermittelt. Eine erneuerbare Steam-Anmeldung wird geschützt auf dem Server gespeichert, damit auch
                private Bibliotheken, Lizenzdaten und spätere Synchronisationen funktionieren.
              </v-alert>
              <v-btn
                v-if="!steamQrDataUrl"
                color="primary"
                size="large"
                prepend-icon="mdi-steam"
                :loading="steamLoginPending"
                :disabled="busy"
                @click="startSteamLogin"
              >
                Steam-QR-Code anzeigen
              </v-btn>
              <div v-else class="steam-qr-login">
                <img :src="steamQrDataUrl" alt="QR-Code für die Steam-Anmeldung" class="steam-qr-code" />
                <v-alert type="info" variant="tonal">
                  <v-progress-circular v-if="steamLoginPending" indeterminate size="18" width="2" class="mr-2" />
                  {{ steamStatusMessage }}
                </v-alert>
                <v-btn
                  variant="text"
                  prepend-icon="mdi-refresh"
                  :disabled="busy"
                  @click="startSteamLogin"
                >
                  Neuen QR-Code anfordern
                </v-btn>
              </div>
            </template>

            <template v-else-if="steamConnectionMode === 'openid'">
              <v-alert type="info" variant="tonal" class="mb-4">
                <div class="font-weight-bold mb-1">Ohne Steam-App und ohne gespeichertes Token</div>
                Steam öffnet sich in diesem Browser. Benutzername, Passwort und Steam Guard gibst du ausschließlich
                auf <strong>steamcommunity.com</strong> ein; sie werden nicht an diese Anwendung übermittelt.
                Nach der Bestätigung erhält die Anwendung nur deine SteamID.
              </v-alert>
              <p class="text-body-2 mb-2"><strong>Dafür gelten folgende Einschränkungen:</strong></p>
              <ul class="text-body-2 text-medium-emphasis mb-4 steam-limitations">
                <li>Dein Steam-Profil und die „Spieldetails“ müssen öffentlich sein.</li>
                <li>Lizenz- und Erwerbsdaten (z.B. Kaufzeitpunkt) fehlen.</li>
                <li>Ungenutzte oder deinstallierte Gratisspiele können fehlen.</li>
              </ul>
              <v-btn
                color="primary"
                size="large"
                prepend-icon="mdi-steam"
                :loading="busy"
                @click="startSteamOpenIdLogin"
              >
                Bei Steam anmelden
              </v-btn>
              <p class="text-caption text-medium-emphasis mt-3 mb-0">
                Du kehrst danach automatisch hierher zurück und die Bibliothek wird synchronisiert.
              </p>
            </template>

            <template v-else>
              <v-alert type="info" variant="tonal" class="mb-4">
                <div class="font-weight-bold mb-1">Manuell über das öffentliche Community-Profil</div>
                Es wird kein Steam-Zugangs- oder Refresh-Token gespeichert. Spätere Synchronisationen laufen anhand
                deiner SteamID über die offizielle Steam Web API und benötigen keine erneute Anmeldung.
              </v-alert>
              <p class="text-body-2 mb-2"><strong>Dafür gelten folgende Einschränkungen:</strong></p>
              <ul class="text-body-2 text-medium-emphasis mb-4 steam-limitations">
                <li>Dein Steam-Profil und die „Spieldetails“ müssen öffentlich sein.</li>
                <li>Lizenz- und Erwerbsdaten (z.B. Kaufzeitpunkt) fehlen</li>
                <li>Ungenutzte oder deinstallierte Gratisspiele können fehlen.</li>
              </ul>
              <v-text-field
                v-model="steamProfile"
                label="Steam-Community-ID, Profilname oder Profillink"
                prepend-inner-icon="mdi-account-search-outline"
                autocomplete="off"
                :disabled="busy"
                hint="Beispiel: nickname, SteamID64 oder https://steamcommunity.com/id/nickname"
                persistent-hint
                @keyup.enter="submit"
              />

              <div v-if="steamResolvedProfile" class="steam-profile-preview mt-4">
                <v-avatar size="48">
                  <v-img v-if="steamResolvedProfile.avatar_url" :src="steamResolvedProfile.avatar_url" alt="" />
                  <v-icon v-else icon="mdi-account-circle" />
                </v-avatar>
                <div>
                  <div class="font-weight-bold">{{ steamResolvedProfile.display_name }}</div>
                  <div class="text-caption text-medium-emphasis">
                    <template v-if="steamResolvedProfile.library_accessible">
                      {{ steamResolvedProfile.game_count }} Spiele öffentlich sichtbar
                    </template>
                    <template v-else>Spielebibliothek ist nicht öffentlich</template>
                  </div>
                </div>
              </div>
              <v-alert v-if="steamResolvedProfile && !steamResolvedProfile.library_accessible" type="warning" variant="tonal" class="mt-4">
                Öffne bei Steam „Profil bearbeiten → Privatsphäreeinstellungen“ und setze „Spieldetails“ auf
                „Öffentlich“. Prüfe das Profil danach erneut.
              </v-alert>
            </template>
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
            <v-select
              v-model="browserFamily"
              :items="browserOptions"
              label="Erkannter Browser"
              density="compact"
              variant="outlined"
              hide-details
              class="browser-select mb-4"
            />
            <ol class="session-steps mb-4">
              <li v-for="step in sessionGuideSteps" :key="step">{{ step }}</li>
            </ol>
            <v-alert type="info" variant="tonal" density="compact" class="mb-4">
              {{ browserRequestHint }}
            </v-alert>
            <v-alert v-if="target.platform === 'ea'" type="success" variant="tonal" density="compact" class="mb-4">
              Das ist nur einmal nötig. Die App prüft den enthaltenen EA-Token und verwirft die übrige cURL-Anfrage
              einschließlich ihrer Cookies.
            </v-alert>
            <div class="d-flex flex-wrap ga-2 mb-4">
              <v-btn
                :href="loginStart?.login_url"
                target="_blank"
                color="primary"
                prepend-icon="mdi-open-in-new"
              >
                {{ providerOpenButtonLabel }}
              </v-btn>
              <v-btn
                v-if="target.platform === 'ea'"
                :href="loginStart?.capture_url"
                target="_blank"
                color="primary"
                variant="tonal"
                prepend-icon="mdi-gamepad-variant-outline"
              >
                Danach EA-Bibliothek öffnen
              </v-btn>
            </div>
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
            <h2 class="text-h6 mt-4">
              Spiele werden geladen
            </h2>
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
          v-else-if="stage === 2 && target.platform !== 'xbox' && (target.platform !== 'steam' || steamConnectionMode === 'community')"
          color="primary"
          append-icon="mdi-arrow-right"
          :disabled="!canSubmit"
          :loading="busy"
          @click="submit"
        >
          {{ needs2fa ? 'Code bestätigen' : target.platform === 'steam' ? steamActionLabel : 'Anmeldung abschließen' }}
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
        <v-btn
          v-else-if="stage === 3 && error && !busy"
          color="primary"
          prepend-icon="mdi-refresh"
          @click="syncLibrary"
        >
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
import { platformIcon, platformTitle } from '../platforms'
import type { Account, Participant, Platform, ProviderLoginStart, SteamProfile } from '../types'

interface ProviderTarget {
  participant: Participant
  platform: Platform
  account?: Account
}

type BrowserFamily = 'firefox' | 'edge' | 'chromium' | 'safari' | 'other'
type SteamConnectionMode = 'qr' | 'openid' | 'community'

const browserOptions: Array<{ title: string; value: BrowserFamily }> = [
  { title: 'Firefox', value: 'firefox' },
  { title: 'Microsoft Edge', value: 'edge' },
  { title: 'Chrome / Chromium', value: 'chromium' },
  { title: 'Safari', value: 'safari' },
  { title: 'Anderer Browser', value: 'other' }
]

const browserGuides: Record<BrowserFamily, { steps: string[] }> = {
  firefox: {
    steps: [
      'Öffne die Loginseite und melde dich vollständig an.',
      'Drücke F12 und öffne den Tab „Netzwerkanalyse“.',
      'Lade die Anbieterseite neu, damit die Anfragen in der Liste erscheinen.',
      'Klicke die passende erfolgreiche Anfrage mit der rechten Maustaste an und wähle „Wert kopieren“ und danach „Als cURL kopieren“.',
      'Füge die komplette kopierte Anfrage unten ein.'
    ]
  },
  edge: {
    steps: [
      'Öffne die Loginseite und melde dich vollständig an.',
      'Drücke F12 und öffne in den Entwicklertools den Tab „Netzwerk“ beziehungsweise „Network“.',
      'Lade die Anbieterseite neu, damit die Anfragen in der Liste erscheinen.',
      'Klicke die passende erfolgreiche Anfrage mit der rechten Maustaste an und wähle „Kopieren“ beziehungsweise „Copy“ und dann „Als cURL kopieren (bash)“.',
      'Füge die komplette kopierte Anfrage unten ein.'
    ]
  },
  chromium: {
    steps: [
      'Öffne die Loginseite und melde dich vollständig an.',
      'Drücke F12 und öffne in den Entwicklertools den Tab „Netzwerk“ beziehungsweise „Network“.',
      'Lade die Anbieterseite neu, damit die Anfragen in der Liste erscheinen.',
      'Klicke die passende erfolgreiche Anfrage mit der rechten Maustaste an und wähle „Kopieren“ beziehungsweise „Copy“ und dann „Als cURL kopieren (bash)“.',
      'Füge die komplette kopierte Anfrage unten ein.'
    ]
  },
  safari: {
    steps: [
      'Öffne die Loginseite und melde dich vollständig an.',
      'Öffne mit ⌥⌘I die Webinformationen und dort den Tab „Netzwerk“. Fehlt das Entwickler-Menü, aktiviere es zuvor in Safari unter „Einstellungen > Erweitert“.',
      'Lade die Anbieterseite neu, damit die Anfragen in der Liste erscheinen.',
      'Klicke die passende erfolgreiche Anfrage mit der rechten Maustaste an und wähle „Als cURL kopieren“.',
      'Füge die komplette kopierte Anfrage unten ein.'
    ]
  },
  other: {
    steps: [
      'Öffne die Loginseite und melde dich vollständig an.',
      'Öffne die Entwicklertools deines Browsers und darin den Bereich „Netzwerk“ beziehungsweise „Network“.',
      'Lade die Anbieterseite neu, damit die Anfragen in der Liste erscheinen.',
      'Kopiere die passende erfolgreiche Anfrage als cURL.',
      'Füge die komplette kopierte Anfrage unten ein.'
    ]
  }
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
const steamConnectionMode = ref<SteamConnectionMode>('qr')
const steamProfile = ref('')
const steamResolvedProfile = ref<SteamProfile>()
const steamLoginPending = ref(false)
const steamLoginState = ref('')
const steamQrDataUrl = ref('')
const steamStatusMessage = ref('QR-Code mit der Steam-App scannen und bestätigen.')
const needs2fa = ref(false)
const resultMessage = ref('')
const ubisoft = reactive({ email: '', password: '', twoFactorCode: '' })
const xboxChecking = ref(false)
const codeCopied = ref(false)
const browserFamily = ref<BrowserFamily>(detectBrowser())
let xboxPollTimer: ReturnType<typeof setTimeout> | undefined
let steamPollTimer: ReturnType<typeof setTimeout> | undefined

const progress = computed(() => stage.value * 25)
const browserGuide = computed(() => browserGuides[browserFamily.value])
const providerOpenButtonLabel = computed(() => {
  if (props.target?.platform === 'ea') return 'EA-Login öffnen'
  if (props.target?.platform === 'battle_net') return 'Battle.net-Bibliotheksseite öffnen'
  return `${platformTitle(props.target?.platform || '')} öffnen`
})
const sessionGuideSteps = computed(() => {
  if (props.target?.platform === 'battle_net') {
    return [
      'Nutze unten den Button „Battle.net-Bibliotheksseite öffnen“. Öffne Battle.net bitte nicht manuell in einem anderen Tab.',
      'Melde dich an, falls Battle.net dich dazu auffordert. Danach solltest du auf der technischen Seite „games-and-subs“ landen.',
      browserGuide.value.steps[1],
      'Lade die Seite neu, damit die Anfrage „games-and-subs“ in der Netzwerkliste erscheint.',
      'Klicke die erfolgreiche Anfrage „games-and-subs“ mit Status 200 mit der rechten Maustaste an und kopiere sie als cURL.',
      'Füge die komplette kopierte Anfrage unten ein.'
    ]
  }
  if (props.target?.platform !== 'ea') return browserGuide.value.steps
  return [
    'Öffne den EA-Login und melde dich vollständig an.',
    'Kehre zu diesem Dialog zurück und öffne danach über den zweiten Button die EA-Bibliothek.',
    browserGuide.value.steps[1],
    'Lade die EA-Bibliotheksseite neu, damit die Bibliotheksanfrage in der Liste erscheint.',
    'Filtere im Netzwerk-Tab nach „GetUserOwnedGameProducts“ oder nach „juno.ea.com/graphql“.',
    browserGuide.value.steps[3],
    'Füge die komplette kopierte Anfrage unten ein.'
  ]
})
const browserRequestHint = computed(() => {
  if (props.target?.platform === 'battle_net') {
    return 'Wichtig: Starte über den Button in diesem Dialog. Gesucht ist danach die Anfrage „games-and-subs“ mit Status 200.'
  }
  if (props.target?.platform === 'humble') {
    return 'Filtere nach „user/order“ und kopiere diese Anfrage mit Status 200. Falls sie fehlt, öffne deine Humble-Bibliothek und lade sie neu.'
  }
  if (props.target?.platform === 'meta') {
    return 'Kopiere eine erfolgreiche Anfrage an „secure.oculus.com“ aus der neu geladenen Profilseite.'
  }
  if (props.target?.platform === 'ea') {
    return 'Kopiere die erfolgreiche Anfrage „GetUserOwnedGameProducts“ an „juno.ea.com/graphql“ als cURL.'
  }
  return 'Wähle eine erfolgreiche Anfrage an den gerade geöffneten Anbieter.'
})
const canSubmit = computed(() => {
  const platform = props.target?.platform
  if (platform === 'steam') {
    return steamConnectionMode.value === 'community'
      && Boolean(steamProfile.value.trim())
      && !steamLoginPending.value
  }
  if (platform === 'ubisoft') {
    return needs2fa.value
      ? Boolean(ubisoft.twoFactorCode.trim())
      : Boolean(ubisoft.email.trim() && ubisoft.password)
  }
  if (platform === 'xbox') return false
  return Boolean(code.value.trim())
})
const steamActionLabel = computed(() => {
  if (!steamResolvedProfile.value) return 'Profil prüfen'
  if (!steamResolvedProfile.value.library_accessible) return 'Erneut prüfen'
  return 'Ohne Token verbinden und Spiele laden'
})
const isBrowserSessionPlatform = computed(() =>
  ['battle_net', 'humble', 'meta', 'ea'].includes(props.target?.platform || '')
)
const introTitle = computed(() => `${platformTitle(props.target?.platform || '')} verbinden`)
const introText = computed(() => {
  const platform = props.target?.platform
  if (platform === 'steam') return 'Du entscheidest selbst: Die QR-Anmeldung liefert die vollständigsten Daten und speichert eine erneuerbare Anmeldung. Alternativ nutzt die App nur dein öffentliches Steam-Community-Profil und speichert kein Steam-Token.'
  if (platform === 'epic') return 'Die Anmeldung findet auf der offiziellen Epic-Seite statt. Danach gibst du die angezeigte Bestätigung hier zurück.'
  if (platform === 'gog') return 'Die Anmeldung findet auf der offiziellen GOG-Seite statt. Danach übernimmt die App den Bestätigungscode.'
  if (platform === 'ubisoft') return 'Du meldest dich direkt mit deinem Ubisoft-Konto an. Falls 2FA aktiv ist, führt der Assistent automatisch zum nächsten Schritt.'
  if (platform === 'xbox') return 'Du bestätigst die Verbindung einmalig bei Microsoft. Danach lädt die App automatisch deine auf dem PC gespielten Xbox-Titel.'
  if (platform === 'ea') return 'Du meldest dich einmalig auf der offiziellen EA-Seite an. Der Assistent übernimmt danach die Bibliotheksberechtigung aus einer Browser-Anfrage und lädt deine PC-Spiele.'
  if (platform === 'amazon') return 'Du meldest dich einmalig bei Amazon an. Die App speichert eine erneuerbare Geräteanmeldung und lädt deine Amazon-Games-Bibliothek.'
  if (platform === 'battle_net') return 'Die App übernimmt einmalig deine angemeldete Battle.net-Browsersitzung und kann damit deine PC-Spiele laden.'
  if (platform === 'humble') return 'Die App übernimmt einmalig deine angemeldete Humble-Browsersitzung und lädt daraus deine Windows-Spiele.'
  if (platform === 'meta') return 'Die App übernimmt einmalig deine angemeldete Meta-Sitzung und lädt deine Rift-, PCVR- und Quest-Bibliothek.'
  return 'Für diese Plattform ist der Playnite-Import derzeit der verlässlichste und einfachste Weg.'
})
const introSteps = computed(() => {
  const platform = props.target?.platform
  if (platform === 'steam') return ['Verbindungsart und Datenumfang auswählen', 'Steam-Konto oder öffentliches Community-Profil verbinden', 'Bibliothek automatisch laden']
  if (platform === 'epic' || platform === 'gog') return ['Offizielle Loginseite öffnen', 'Bestätigung kopieren und einfügen', 'Bibliothek automatisch laden']
  if (platform === 'ubisoft') return ['E-Mail und Passwort eingeben', 'Falls nötig 2FA bestätigen', 'Bibliothek automatisch laden']
  if (platform === 'xbox') return ['Einmaligen Code anzeigen', 'Bei Microsoft bestätigen', 'Bibliothek automatisch laden']
  if (platform === 'amazon') return ['Amazon-Anmeldung öffnen', 'Adresse zurückgeben', 'Bibliothek automatisch laden']
  if (['battle_net', 'humble', 'meta', 'ea'].includes(platform || '')) return ['Anbieterseite öffnen und anmelden', 'Bibliotheksanfrage kopieren', 'Bibliothek automatisch laden']
  return ['Playnite-Backup auswählen', 'Backup importieren', 'Spiele prüfen']
})

watch(
  () => props.modelValue,
  (open) => {
    clearXboxPoll()
    clearSteamLogin()
    if (!open || !props.target) return
    stage.value = 1
    busy.value = false
    error.value = ''
    account.value = props.target.account
    loginStart.value = undefined
    code.value = ''
    steamConnectionMode.value = 'qr'
    steamProfile.value = props.target.platform === 'steam' && props.target.account && !props.target.account.account_id.startsWith('playnite:')
      ? props.target.account.account_id
      : ''
    steamResolvedProfile.value = undefined
    steamLoginPending.value = false
    steamLoginState.value = ''
    steamQrDataUrl.value = ''
    steamStatusMessage.value = 'QR-Code mit der Steam-App scannen und bestätigen.'
    needs2fa.value = false
    resultMessage.value = ''
    xboxChecking.value = false
    codeCopied.value = false
    browserFamily.value = detectBrowser()
    Object.assign(ubisoft, { email: '', password: '', twoFactorCode: '' })
  }
)

watch(steamProfile, (value) => {
  if (steamResolvedProfile.value?.steam_id !== value.trim()) {
    steamResolvedProfile.value = undefined
  }
})

watch(steamConnectionMode, (mode) => {
  error.value = ''
  steamResolvedProfile.value = undefined
  if (mode === 'qr') return
  clearSteamLogin()
  steamLoginState.value = ''
  steamQrDataUrl.value = ''
  steamStatusMessage.value = 'QR-Code mit der Steam-App scannen und bestätigen.'
})

async function prepare() {
  if (!props.target) return
  error.value = ''
  if (props.target.platform === 'steam') {
    stage.value = 2
    return
  }
  busy.value = true
  try {
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
    display_name: ''
  })
}

async function submit() {
  if (!props.target) return
  busy.value = true
  error.value = ''
  try {
    if (props.target.platform === 'steam') {
      if (!steamResolvedProfile.value || !steamResolvedProfile.value.library_accessible) {
        steamResolvedProfile.value = await api.resolveSteamProfile(steamProfile.value)
        if (!steamResolvedProfile.value.library_accessible) return
        return
      }
      const connection = await api.connectSteam(
        props.target.participant.id,
        steamResolvedProfile.value.steam_id
      )
      account.value = connection.account
      steamResolvedProfile.value = connection
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

async function startSteamLogin() {
  if (!props.target) return
  clearSteamLogin()
  error.value = ''
  busy.value = true
  try {
    const result = await api.startSteamLogin(props.target.participant.id)
    steamLoginState.value = result.state
    steamQrDataUrl.value = result.qr_data_url
    steamStatusMessage.value = 'QR-Code mit der Steam-App scannen und bestätigen.'
    steamLoginPending.value = true
    scheduleSteamPoll()
  } catch (err) {
    error.value = readableError(err)
  } finally {
    busy.value = false
  }
}

async function startSteamOpenIdLogin() {
  if (!props.target) return
  clearSteamLogin()
  error.value = ''
  busy.value = true
  try {
    const returnPath = window.location.pathname.startsWith('/admin/') ? '/admin/logins' : '/logins'
    const result = await api.startSteamOpenId(
      props.target.participant.id,
      window.location.origin,
      returnPath
    )
    window.location.assign(result.login_url)
  } catch (err) {
    error.value = readableError(err)
    busy.value = false
  }
}

function scheduleSteamPoll() {
  if (steamPollTimer) clearTimeout(steamPollTimer)
  steamPollTimer = setTimeout(() => void pollSteamLogin(), 1500)
}

async function pollSteamLogin() {
  if (!steamLoginState.value || !props.modelValue) return
  try {
    const result = await api.pollSteamLogin(steamLoginState.value)
    steamStatusMessage.value = result.message
    if (result.status === 'failed') {
      steamLoginPending.value = false
      error.value = result.message
      return
    }
    if (result.status !== 'complete') {
      scheduleSteamPoll()
      return
    }
    if (!result.account || !result.profile) {
      throw new Error('Steam wurde bestätigt, aber der Account konnte nicht gespeichert werden.')
    }
    steamLoginPending.value = false
    steamProfile.value = result.profile.steam_id
    steamResolvedProfile.value = result.profile
    account.value = result.account
    resultMessage.value = result.message
    stage.value = 4
    emit('finished')
  } catch (err) {
    steamLoginPending.value = false
    error.value = readableError(err)
  }
}

function clearSteamLogin() {
  if (steamPollTimer) {
    clearTimeout(steamPollTimer)
    steamPollTimer = undefined
  }
  steamLoginPending.value = false
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

function detectBrowser(): BrowserFamily {
  if (typeof navigator === 'undefined') return 'other'
  const userAgent = navigator.userAgent
  if (/Edg\//i.test(userAgent)) return 'edge'
  if (/Firefox\//i.test(userAgent)) return 'firefox'
  if (/(Chrome|Chromium|CriOS)\//i.test(userAgent)) return 'chromium'
  if (/Safari\//i.test(userAgent)) return 'safari'
  return 'other'
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
  clearSteamLogin()
  emit('update:modelValue', false)
}

function finish() {
  clearXboxPoll()
  clearSteamLogin()
  emit('update:modelValue', false)
}

onBeforeUnmount(() => {
  clearXboxPoll()
  clearSteamLogin()
})

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

.browser-select {
  max-width: 320px;
}

.steam-mode-toggle {
  display: flex;
  width: 100%;
}

.steam-mode-toggle :deep(.v-btn) {
  flex: 1 1 0;
  min-height: 48px;
  height: auto;
  white-space: normal;
}

.steam-limitations {
  padding-left: 22px;
}

.steam-limitations li {
  margin-bottom: 6px;
}

.steam-profile-preview {
  display: flex;
  align-items: center;
  gap: 12px;
}

.steam-qr-login {
  display: grid;
  justify-items: center;
  gap: 16px;
}

.steam-qr-code {
  width: min(300px, 100%);
  aspect-ratio: 1;
  display: block;
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

.sync-progress {
  width: min(420px, 100%);
}

@media (max-width: 600px) {
  .wizard-content {
    min-height: 420px;
    padding: 18px;
  }

  .steam-mode-toggle {
    flex-direction: column;
  }

  .steam-mode-toggle :deep(.v-btn) {
    width: 100%;
  }
}
</style>
