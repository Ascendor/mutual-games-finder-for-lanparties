import { expect, test, type Page } from '@playwright/test'

const participants = [
  { id: 1, nickname: 'Alpha', real_name: 'Alex', present: true, notes: '' },
  { id: 2, nickname: 'beta', real_name: 'Bea', present: true, notes: '' }
]
const games = [{ id: 1, title: 'Test Co-op Game' }]
const recommendations = [
  { id: 2, title: 'Zulu Co-op', owners: 2, multiplayer: true, genre: 'Action' },
  { id: 3, title: 'Alpha Versus', owners: 1, multiplayer: true, genre: 'Strategy' },
  { id: 4, title: 'Solo Adventure', owners: 2, multiplayer: false, genre: 'Adventure' }
].map(game => ({
  game: {
    id: game.id, title: game.title, genres: [game.genre], singleplayer: !game.multiplayer,
    multiplayer: game.multiplayer, online_coop: game.id === 2, versus: game.id === 3,
    min_players: game.multiplayer ? 2 : 1, max_players: game.multiplayer ? 4 : 1,
    player_count_known: true, is_free: false
  },
  owner_count: game.owners, selected_player_count: 2, coverage_percent: game.owners * 50,
  unknown_players: [], platforms: ['steam'], total_playtime_minutes: 120,
  median_playtime_minutes: 60, average_playtime_minutes: 60
}))

test.beforeEach(async ({ page }) => {
  // Synthetic API responses keep browser checks independent of private libraries.
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname
    let body: unknown = []
    if (path === '/api/config') body = {
      display_name: 'Mutual Games Finder',
      title: 'Mutual Games Finder - Der Spielefinder',
      subtitle: 'Der Spielefinder',
      source_url: 'https://github.com/Ascendor/mutual-games-finder-for-lanparties',
      upstream_source_url: 'https://github.com/Ascendor/mutual-games-finder-for-lanparties'
    }
    else if (path === '/api/participants') body = participants
    else if (path === '/api/games/options') body = games
    else if (path === '/api/recommendations/common') body = recommendations
    else if (path.endsWith('/owners')) body = [{
      participant: participants[1], platforms: ['steam'], account_names: [],
      total_playtime_minutes: 120, last_seen: '2026-09-01T12:00:00'
    }]
    else if (path.startsWith('/api/app-log')) body = { status: 'ok' }
    await route.fulfill({ json: body })
  })
})

async function signIn(page: Page) {
  await page.goto('/player')
  await page.getByRole('combobox', { name: 'Nickname' }).fill('Alpha')
  await page.getByRole('option', { name: 'Alpha', exact: true }).click()
  await page.getByRole('button', { name: 'Weiter als Alpha' }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(page.getByText('Eingeloggt als Alpha')).toBeVisible()
}

test('existing participant can sign in, use settings links and sign out', async ({ page }) => {
  await signIn(page)
  const settings = page.locator('.action-card').filter({ hasText: 'Einstellungen' })
  await expect(settings.getByRole('link', { name: 'Meine Spiele', exact: true })).toHaveAttribute('href', '/my-games')
  await expect(settings.getByRole('link', { name: 'Meine Accounts', exact: true })).toHaveAttribute('href', '/logins')
  expect(await settings.locator('.settings-actions svg').count()).toBe(0)
  await page.reload()
  await expect(page.getByText('Eingeloggt als Alpha')).toBeVisible()
  await settings.getByRole('button', { name: 'Abmelden' }).click()
  await expect(page).toHaveURL(/\/player$/)
})

test('game autocomplete opens the prefilled owner search', async ({ page }) => {
  await signIn(page)
  const search = page.getByRole('combobox', { name: 'Spiel', exact: true })
  await search.fill('Test Co')
  await page.getByRole('option', { name: 'Test Co-op Game', exact: true }).click()
  await page.getByRole('button', { name: 'Wer spielt mit?' }).click()
  await expect(page).toHaveURL(/\/find-players\?game=Test/)
  await expect(page.locator('table').getByText('beta', { exact: true })).toBeVisible()
})

test('group selection preserves real names, checkboxes and selected participants', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await signIn(page)
  await page.getByRole('combobox', { name: 'Mitspieler:innen' }).click()
  const other = page.getByRole('option', { name: 'beta (Bea)', exact: true })
  await expect(other.locator('input[type=checkbox]')).not.toBeChecked()
  await other.click()
  await expect(other.locator('input[type=checkbox]')).toBeChecked()
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Was können wir spielen?' }).click()
  await expect(page).toHaveURL(/\/recommendations\?players=1,2&tab=common/)
  await page.locator('.v-select').filter({ has: page.getByRole('combobox', { name: 'Spieler:innen' }) }).locator('.v-field').click()
  await expect(page.getByRole('option', { name: 'Alpha (Alex)', exact: true }).locator('input[type=checkbox]')).toBeChecked()
  const selectedOther = page.getByRole('option', { name: 'beta (Bea)', exact: true })
  await expect(selectedOther.locator('input[type=checkbox]')).toBeChecked()
  await selectedOther.click()
  await expect(selectedOther.locator('input[type=checkbox]')).not.toBeChecked()
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: 'Koop', exact: true }).click()
  await expect(page.getByRole('tab', { name: 'Koop', exact: true })).toHaveAttribute('aria-selected', 'true')
  expect(errors).toEqual([])
})

test('home actions remain visible without horizontal page overflow', async ({ page }, testInfo) => {
  await signIn(page)
  for (const name of ['Wer spielt mit?', 'Was können wir spielen?']) {
    const button = page.getByRole('button', { name, exact: true })
    await expect(button).toBeVisible()
    expect(await button.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: testInfo.outputPath('home.png'), fullPage: true })
})

test('navigation remains accessible on small screens', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'Desktop uses a permanent navigation drawer')
  await signIn(page)
  await page.getByRole('button', { name: 'Navigation öffnen' }).click()
  await page.locator('nav').getByRole('link', { name: 'Was können wir spielen?' }).click()
  await expect(page).toHaveURL(/\/recommendations/)
  await expect(page.locator('nav')).not.toBeInViewport()
})

test('recommendation tables retain sorting, genre filters and singleplayer visibility', async ({ page }) => {
  await signIn(page)
  await page.goto('/recommendations?players=1,2&tab=common')
  const table = page.locator('table:visible')
  await expect(table.locator('tbody tr').first()).toContainText('Zulu Co-op')
  await expect(table.getByText('Solo Adventure')).toHaveCount(0)
  await table.getByRole('columnheader', { name: 'Spiel', exact: true }).click()
  await expect(table.locator('tbody tr').first()).toContainText('Alpha Versus')
  await page.getByRole('button', { name: 'Filter', exact: true }).click()
  await page.getByRole('combobox', { name: 'Genres', exact: true }).fill('Action')
  await page.getByRole('option', { name: 'Action', exact: true }).click()
  await page.keyboard.press('Escape')
  await expect(table.locator('tbody tr')).toHaveCount(1)
  await expect(table.locator('tbody tr')).toContainText('Zulu Co-op')
  await page.getByRole('button', { name: 'Zurücksetzen', exact: true }).click()
  await page.getByRole('checkbox', { name: 'Reine Singleplayer anzeigen' }).check()
  await expect(table.getByText('Solo Adventure')).toBeVisible()
})
