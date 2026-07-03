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
        gedacht. Sie enthält kein Tracking, keine Werbung und keine
        Benutzerprofile für fremde Zwecke.
      </p>
    </header>

    <section>
      <h2>Wer ist verantwortlich?</h2>
      <p>
        Verantwortlich für eine konkrete Installation ist die Person, die den
        Server betreibt. Ihre Kontaktdaten werden innerhalb der LAN-Gruppe
        bekanntgegeben. Wer diese Software selbst öffentlich bereitstellt,
        muss diesen Abschnitt um eigene, erreichbare Kontaktdaten und
        gegebenenfalls weitere Pflichtangaben ergänzen.
      </p>
    </section>

    <section>
      <h2>Welche Daten werden gespeichert?</h2>
      <ul>
        <li>Nickname, optionaler Realname, Anwesenheit und freiwillige Notizen</li>
        <li>Plattform, Account-ID und Anzeigename verbundener Spielekonten</li>
        <li>Spielebibliotheken, Besitzzuordnungen und Spielzeiten</li>
        <li>lokal zwischengespeicherte Spielmetadaten und Synchronisationsprotokolle</li>
        <li>
          notwendige Provider-Tokens oder Sitzungsdaten im geschützten
          Server-Speicher; Passwörter werden nicht gespeichert
        </li>
      </ul>
      <p>
        Die Daten dienen ausschließlich dazu, gemeinsame Spiele zu finden,
        Empfehlungen zu berechnen und Bibliotheken später erneut zu
        synchronisieren.
      </p>
    </section>

    <section>
      <h2>Externe Dienste</h2>
      <p>
        Eine Übertragung an Spieleplattformen findet nur statt, wenn ein
        Account verbunden oder synchronisiert wird. Für die
        Metadatenanreicherung werden Spieltitel und Plattformangaben an
        IGDB/Twitch und, sofern konfiguriert, RAWG gesendet. Dabei gelten die
        Bedingungen und Datenschutzhinweise des jeweiligen Dienstes.
      </p>
      <div class="legal-links">
        <a href="https://steamcommunity.com/dev/apiterms" target="_blank" rel="noopener noreferrer">
          Steam Web API
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
      <h2>Speicherung im Browser</h2>
      <p>
        Der Browser merkt sich lokal den ausgewählten Teilnehmer. Eine
        entsperrte Administrationssitzung wird nur bis zum Schließen des Tabs
        gespeichert. Die Anwendung setzt selbst keine Analyse- oder
        Werbe-Cookies ein.
      </p>
    </section>

    <section>
      <h2>Löschung und Kontrolle</h2>
      <p>
        Alle Teilnehmer dürfen die gemeinsamen Daten bearbeiten. Accounts und
        Teilnehmer können im Administrationsbereich gelöscht werden.
        Provider-Zugänge lassen sich zusätzlich beim jeweiligen Anbieter
        widerrufen. Für Auskunft, Berichtigung, Export oder Löschung ist die
        betreibende Person anzusprechen.
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
      Diese Information beschreibt die Standardinstallation und ist keine
      Rechtsberatung. Betreiber öffentlicher Instanzen müssen sie an ihre
      tatsächliche Konfiguration und Rechtslage anpassen.
    </v-alert>
  </main>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { currentParticipantId } from '../playerIdentity'

const router = useRouter()

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
