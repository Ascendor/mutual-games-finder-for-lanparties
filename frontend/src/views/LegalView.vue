<template>
  <main class="page legal-page">
    <v-btn
      variant="text"
      prepend-icon="mdi-arrow-left"
      class="mb-4"
      @click="goBack"
    >
      Zurück
    </v-btn>

    <header class="mb-8">
      <div class="text-overline text-primary">Transparenz</div>
      <h1 class="text-h3 mb-3">Datenschutz &amp; Hinweise</h1>
      <p class="text-body-1 text-medium-emphasis">
        Diese Anwendung ist für eine private, nichtkommerzielle LAN-Gruppe
        gedacht. Sie enthält keine Werbung und keine externe
        Nutzungsanalyse. Die interne Statistik dient ausschließlich der
        Auswertung dieser LAN-Party.
      </p>
    </header>

    <section>
      <h2>Verantwortliche Stelle</h2>
      <p>
        Verantwortlich für diese Installation ist
        <strong>{{ privacy.controller_name }}</strong>.
      </p>
      <p>
        Kontakt: <strong>{{ privacy.controller_contact }}</strong>
      </p>
      <p>
        Die Anwendung wird bei <strong>{{ privacy.hosting_provider }}</strong>
        betrieben. Ein Datenschutzbeauftragter ist für diese private
        Installation nicht bestellt.
      </p>
      <p>
        Die Anwendung ist für einen geschlossenen Freundeskreis bestimmt.
        Ob die Ausnahme für ausschließlich persönliche oder familiäre
        Tätigkeiten greift, hängt von der konkreten Nutzung ab. Die folgenden
        Informationen werden vorsorglich auch für den Fall bereitgestellt,
        dass die DSGVO anwendbar ist.
      </p>
    </section>

    <section>
      <h2>Verarbeitete Daten</h2>
      <ul>
        <li>Nickname, optionaler Realname, Anwesenheit und freiwillige Notizen</li>
        <li>Plattform, Account-ID und Anzeigename verbundener Spielekonten</li>
        <li>Spielebibliotheken, Besitzzuordnungen und Spielzeiten</li>
        <li>Playnite- und GOG-Galaxy-Importe sowie manuell bestätigte Besitzzuordnungen</li>
        <li>lokal gespeicherte Spielmetadaten und Synchronisationsprotokolle</li>
        <li>
          Nutzungsereignisse mit Teilnehmer, Zeitpunkt, aufgerufener
          Anwendungsseite, gesuchtem Spiel, Trefferzahl, ausgewählter Gruppe
          und Anzahl der berechneten Ergebnisse
        </li>
        <li>
          je nach freiwillig gewählter Verbindungsart erforderliche
          Provider-Tokens oder Sitzungsdaten im geschützten Server-Speicher;
          Passwörter werden nicht gespeichert
        </li>
        <li>
          technische Webserver- und Fehlerprotokolle; dabei können
          insbesondere IP-Adresse, Zeitpunkt, angeforderter Pfad und
          Fehlerdetails verarbeitet werden
        </li>
      </ul>
    </section>

    <section>
      <h2>Zwecke und Rechtsgrundlagen</h2>
      <p>
        Stammdaten, Bibliotheken und Spielzeiten werden verarbeitet, um
        gemeinsame Spiele zu finden und Empfehlungen zu berechnen. Soweit die
        DSGVO anwendbar ist, beruht dies auf dem berechtigten Interesse der
        geschlossenen Gruppe an der Organisation der gemeinsamen LAN-Party
        gemäß Art. 6 Abs. 1 lit. f DSGVO.
      </p>
      <p>
        Das freiwillige Verbinden eines Spielekontos und die dazu notwendige
        Verarbeitung von Sitzungsdaten beruhen auf der Einwilligung der
        jeweiligen Person gemäß Art. 6 Abs. 1 lit. a DSGVO. Die Verbindung
        kann jederzeit getrennt werden. Die Rechtmäßigkeit der Verarbeitung
        bis zum Widerruf bleibt unberührt.
      </p>
      <p>
        Die lokale Nutzungsanalyse dient dazu, die verwendeten Suchfunktionen
        während der Veranstaltung zu verstehen und die Anwendung für die
        Gruppe zu verbessern. Rechtsgrundlage ist, soweit erforderlich,
        Art. 6 Abs. 1 lit. f DSGVO. Gegen diese Verarbeitung kann bei der
        verantwortlichen Stelle Widerspruch eingelegt werden.
      </p>
      <p>
        Serverprotokolle werden zur Fehlerdiagnose und Abwehr missbräuchlicher
        Zugriffe verarbeitet. Rechtsgrundlage ist Art. 6 Abs. 1 lit. f DSGVO.
      </p>
    </section>

    <section>
      <h2>Datenquellen</h2>
      <p>
        Angaben werden direkt durch Teilnehmer eingegeben, aus freiwillig
        hochgeladenen Playnite-Backups oder GOG-Galaxy-Datenbanken übernommen oder nach einer bewusst
        eingerichteten Verbindung von der jeweiligen Spieleplattform
        abgerufen. Spielmetadaten stammen außerdem von Steam, IGDB/Twitch und
        gegebenenfalls RAWG.
      </p>
    </section>

    <section>
      <h2>Wahlmöglichkeit bei Steam</h2>
      <p>
        Für Steam stehen drei Verbindungsarten zur Verfügung. Bei der
        QR-Anmeldung wird nach der Bestätigung in der offiziellen Steam-App
        ein erneuerbares Steam-Token im geschützten Server-Speicher abgelegt.
        Das Steam-Passwort wird weder übermittelt noch gespeichert. Das Token
        wird ausschließlich zur Abfrage der verbundenen Bibliothek und ihrer
        Lizenzdaten verwendet, nie an den Browser ausgegeben und beim Wechsel
        auf die tokenlose Verbindung oder beim Löschen des Accounts entfernt.
      </p>
      <p>
        Wer kein Steam-Token speichern lassen möchte oder keine Steam-Mobile-App
        verwendet, kann sich über die offizielle Steam-OpenID-Seite im Browser
        anmelden. Benutzername, Passwort und Steam Guard werden dabei
        ausschließlich an Steam übermittelt. Diese Anwendung erhält und
        speichert nur die von Steam bestätigte SteamID und die anschließend
        abgerufenen Bibliotheksdaten. Alternativ kann eine Steam-Community-ID,
        ein Profilname oder ein Profillink manuell angegeben werden; dabei wird
        die Kontrolle über das angegebene Profil nicht technisch bestätigt.
      </p>
      <p>
        Beide tokenlosen Varianten verwenden die offizielle Steam Web API und
        erfordern ein öffentliches Profil mit öffentlichen
        Spieldetails. Öffentlich sichtbare Spielzeiten werden dabei
        übernommen. Private Bibliotheken sowie Lizenz- beziehungsweise
        Erwerbsdaten können auf diesem Weg nicht verarbeitet werden;
        ungenutzte oder deinstallierte Gratisspiele können fehlen. Separat
        ausgeblendete Spielzeiten sind auch mit der QR-Anmeldung nicht
        abrufbar. Weitere Synchronisationen benötigen trotzdem keine erneute
        Anmeldung.
      </p>
    </section>

    <section>
      <h2>Empfänger und externe Dienste</h2>
      <p>
        Die gemeinsam gepflegten Teilnehmer-, Bibliotheks- und
        Empfehlungsdaten sind für die zugelassene LAN-Gruppe sichtbar. Die
        Nutzungsanalyse ist über den Administrationsbereich erreichbar.
        Technischer Empfänger ist außerdem der oben genannte Hostinganbieter.
      </p>
      <p>
        Eine Übertragung an eine Spieleplattform findet nur statt, wenn deren
        Account verbunden oder synchronisiert wird. Für die
        Metadatenanreicherung werden insbesondere Spieltitel und
        Plattformangaben an IGDB/Twitch sowie, sofern konfiguriert, RAWG
        übermittelt. Je nach Anbieter können Daten außerhalb der EU bzw. des
        EWR verarbeitet werden. Dafür gelten zusätzlich die Bedingungen,
        Datenschutzinformationen und Übermittlungsmechanismen des jeweiligen
        Anbieters.
      </p>
      <div class="legal-links">
        <a href="https://steamcommunity.com/dev/apiterms" target="_blank" rel="noopener noreferrer">
          Steam Web API
        </a>
        <a href="https://partner.steamgames.com/doc/features/auth" target="_blank" rel="noopener noreferrer">
          Steam OpenID
        </a>
        <a href="https://api-docs.igdb.com/" target="_blank" rel="noopener noreferrer">
          IGDB
        </a>
        <a href="https://legal.twitch.com/en/legal/developer-agreement/" target="_blank" rel="noopener noreferrer">
          Twitch Developer Agreement
        </a>
        <a href="https://rawg.io/apidocs" target="_blank" rel="noopener noreferrer">
          RAWG API
        </a>
        <a href="https://www.ea.com/legal/user-agreement" target="_blank" rel="noopener noreferrer">
          EA-Nutzungsvereinbarung
        </a>
      </div>
    </section>

    <section>
      <h2>Speicherdauer</h2>
      <ul>
        <li>
          Teilnehmer-, Account- und Bibliotheksdaten bleiben bis zur Löschung
          des Teilnehmers oder Accounts beziehungsweise bis zum Ende des
          Betriebs gespeichert.
        </li>
        <li>
          Provider-Tokens und Sitzungsdaten bleiben bis zum Trennen der
          Verbindung oder Löschen des Accounts gespeichert.
        </li>
        <li>
          Nutzungsereignisse werden regelmäßig und grundsätzlich nach
          {{ privacy.analytics_retention_days }} Tagen automatisch gelöscht.
          Sie können im Administrationsbereich vorher personenbezogen
          gelöscht werden.
        </li>
        <li>
          Webserver- und Fehlerprotokolle sollen nach höchstens
          {{ privacy.access_log_retention_days }} Tagen rotiert werden.
          Sicherheitsbedingte Sperrlisten können davon abweichend bestehen,
          solange dies zur Abwehr erforderlich ist.
        </li>
        <li>
          Backups werden in einem rollierenden Verfahren mit mindestens
          {{ privacy.backup_retention_days }} Tagesständen geführt. Gelöschte
          Daten verschwinden mit der turnusmäßigen Ersetzung auch aus den
          Sicherungen; verschlüsselte externe Sicherungen können bis zum
          nächsten geprüften Sicherungszyklus bestehen bleiben.
        </li>
      </ul>
    </section>

    <section>
      <h2>Speicherung im Browser</h2>
      <p>
        Der Browser speichert lokal den ausgewählten Teilnehmer und im
        Administrationsbereich den zuletzt gewählten Analysezeitraum. Eine
        entsperrte Administrationssitzung wird nur bis zum Schließen des Tabs
        gespeichert. Diese Informationen sind für die ausdrücklich
        angeforderten Funktionen erforderlich. Die Anwendung setzt keine
        Analyse- oder Werbe-Cookies ein.
      </p>
    </section>

    <section>
      <h2>Rechte betroffener Personen</h2>
      <p>
        Soweit die DSGVO anwendbar ist, bestehen insbesondere Rechte auf
        Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung,
        Datenübertragbarkeit und Widerspruch. Eine erteilte Einwilligung kann
        jederzeit mit Wirkung für die Zukunft widerrufen werden. Zur Ausübung
        dieser Rechte ist die oben genannte verantwortliche Stelle zu
        kontaktieren.
      </p>
      <p>
        Accounts, Teilnehmer und personenbezogene Nutzungsereignisse können
        im Administrationsbereich gelöscht werden. Provider-Zugänge lassen
        sich zusätzlich beim jeweiligen Anbieter widerrufen.
      </p>
      <p>
        Es besteht außerdem ein Beschwerderecht bei einer
        Datenschutzaufsichtsbehörde, insbesondere bei
        <a
          :href="privacy.supervisory_authority_url"
          target="_blank"
          rel="noopener noreferrer"
        >
          {{ privacy.supervisory_authority }}
        </a>.
      </p>
    </section>

    <section>
      <h2>Automatisierte Entscheidungen</h2>
      <p>
        Die Anwendung berechnet Spielvorschläge anhand von Besitz,
        Spielerzahl, Funktionen und Spielzeit. Diese Empfehlungen haben keine
        rechtliche oder vergleichbar erhebliche Wirkung. Eine automatisierte
        Entscheidungsfindung im Sinne von Art. 22 DSGVO findet nicht statt.
      </p>
    </section>

    <section>
      <h2>Inoffizielle Anbindungen</h2>
      <p>
        Dieses Projekt ist mit keiner Spieleplattform verbunden und wird von
        keiner der genannten Firmen unterstützt. Einige Browser- und
        Sitzungsanbindungen verwenden nichtöffentliche Schnittstellen. Sie
        können sich jederzeit ändern und dürfen nur vom jeweiligen
        Accountinhaber für dessen eigene Bibliothek verwendet werden.
      </p>
    </section>

    <section>
      <h2>Quellcode und Lizenzen</h2>
      <p>
        Der eigene Quellcode steht unter der MIT-Lizenz. Eingesetzte
        Bibliotheken, Werkzeuge, Plattformen, Spieltexte und Cover behalten
        ihre jeweiligen Rechte und Bedingungen.
      </p>
      <div class="legal-links">
        <a href="/legal/LICENSE" target="_blank">MIT-Lizenz</a>
        <a href="/legal/THIRD_PARTY_NOTICES.md" target="_blank">Drittanbieterhinweise</a>
        <a
          href="https://codeberg.org/Ascendor/ref_ju_geeks-play-together"
          target="_blank"
          rel="noopener noreferrer"
        >
          Repository
        </a>
      </div>
    </section>

    <v-alert type="info" variant="tonal" class="mt-8">
      Stand: Juli 2026. Diese Information beschreibt die konfigurierte
      Installation und ist keine Rechtsberatung.
    </v-alert>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { currentParticipantId } from '../playerIdentity'
import type { PrivacyInfo } from '../types'

const router = useRouter()
const privacy = ref<PrivacyInfo>({
  controller_name: 'Betreiber:in dieser Installation',
  controller_contact: 'Kontakt über den internen LAN-Party-Gruppenkanal',
  hosting_provider: 'VServer-Hostinganbieter der Betreiberperson',
  analytics_retention_days: 180,
  access_log_retention_days: 7,
  backup_retention_days: 14,
  supervisory_authority: 'zuständige Landesdatenschutzaufsichtsbehörde',
  supervisory_authority_url: 'https://www.datenschutzkonferenz-online.de/datenschutzaufsichtsbehoerden.html'
})

onMounted(async () => {
  try {
    privacy.value = await api.privacyInfo()
  } catch {
    // The fallback remains readable even if the backend is temporarily unavailable.
  }
})

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  void router.push(currentParticipantId.value ? '/' : '/player')
}
</script>

<style scoped>
.legal-page {
  max-width: 900px;
}

header p {
  max-width: 760px;
}

section {
  margin-top: 32px;
}

section h2 {
  margin-bottom: 10px;
  font-size: 1.35rem;
  font-weight: 600;
}

section p,
section li {
  line-height: 1.65;
}

section ul {
  padding-left: 24px;
}

.legal-links {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
}

.legal-links a {
  color: rgb(var(--v-theme-primary));
}
</style>
