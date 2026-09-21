import { createServer } from 'node:http'
import { randomUUID } from 'node:crypto'
import QRCode from 'qrcode'
import SteamUser from 'steam-user'
import { EAuthTokenPlatformType, LoginSession } from 'steam-session'

const port = Number(process.env.PORT || 3000)
const loginTimeoutMs = Number(process.env.STEAM_LOGIN_TIMEOUT_MS || 180000)
const resultRetentionMs = Number(process.env.STEAM_RESULT_RETENTION_MS || 600000)
const sessions = new Map()

function sendJson(response, statusCode, payload) {
  const body = JSON.stringify(payload)
  response.writeHead(statusCode, {
    'content-type': 'application/json; charset=utf-8',
    'content-length': Buffer.byteLength(body),
    'cache-control': 'no-store'
  })
  response.end(body)
}

async function readJson(request) {
  const chunks = []
  let size = 0
  for await (const chunk of request) {
    size += chunk.length
    if (size > 64 * 1024) throw new Error('Anfrage ist zu groß.')
    chunks.push(chunk)
  }
  const raw = Buffer.concat(chunks).toString('utf8')
  return raw ? JSON.parse(raw) : {}
}

function numericValues(value) {
  if (Array.isArray(value)) return value.flatMap(numericValues)
  if (value && typeof value === 'object') return Object.values(value).flatMap(numericValues)
  const number = Number(value)
  return Number.isInteger(number) && number > 0 ? [number] : []
}

function appIdsFromPackage(packageInfo) {
  if (!packageInfo || typeof packageInfo !== 'object') return []
  return numericValues(packageInfo.appids ?? packageInfo.app_ids ?? packageInfo.apps ?? [])
}

function acquiredAt(license) {
  const timestamp = Number(license?.time_created || 0)
  if (!Number.isFinite(timestamp) || timestamp < 1063324800) return null
  return new Date(timestamp * 1000).toISOString()
}

function collectLibrary(refreshToken, steamID) {
  return new Promise((resolve, reject) => {
    const user = new SteamUser({
      enablePicsCache: true,
      changelistUpdateInterval: 0,
      dataDirectory: null,
      renewRefreshTokens: false,
      autoRelogin: false
    })
    let settled = false
    const timeout = setTimeout(() => finish(new Error('Steam-Bibliothek konnte nicht rechtzeitig gelesen werden.')), 120000)

    function finish(error, result) {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      try {
        user.logOff()
      } catch {
        // The connection may already be closed after an upstream error.
      }
      if (error) reject(error)
      else resolve(result)
    }

    user.once('error', (error) => finish(error))
    user.once('ownershipCached', () => {
      try {
        const datesByApp = new Map()
        const packageCache = user.picsCache?.packages || {}
        for (const license of user.licenses || []) {
          const date = acquiredAt(license)
          if (!date) continue
          const packageData = packageCache[String(license.package_id)] || packageCache[license.package_id]
          for (const appid of appIdsFromPackage(packageData?.packageinfo)) {
            const current = datesByApp.get(appid)
            if (!current || date < current) datesByApp.set(appid, date)
          }
        }

        const games = []
        for (const appid of user.getOwnedApps()) {
          const appData = user.picsCache?.apps?.[String(appid)] || user.picsCache?.apps?.[appid]
          const common = appData?.appinfo?.common || {}
          const type = String(common.type || '').toLocaleLowerCase()
          if (type && type !== 'game') continue
          const title = String(common.name || '').trim()
          if (!title) continue
          games.push({
            appid: String(appid),
            title,
            owned_since: datesByApp.get(Number(appid)) || null
          })
        }
        games.sort((left, right) => left.title.localeCompare(right.title, 'de', { sensitivity: 'base' }))
        finish(null, { steam_id: String(steamID), games })
      } catch (error) {
        finish(error)
      }
    })

    user.logOn({
      refreshToken,
      steamID: String(steamID),
      machineName: 'LAN Party Game Finder'
    })
  })
}

async function startSession() {
  const id = randomUUID()
  const login = new LoginSession(EAuthTokenPlatformType.SteamClient)
  login.loginTimeout = loginTimeoutMs
  const result = await login.startWithQR()
  const record = {
    status: 'pending',
    createdAt: Date.now(),
    expiresAt: Date.now() + loginTimeoutMs,
    message: 'QR-Code mit der Steam-App scannen und bestätigen.'
  }
  sessions.set(id, record)

  login.on('remoteInteraction', () => {
    record.status = 'scanned'
    record.message = 'QR-Code erkannt. Anmeldung jetzt in der Steam-App bestätigen.'
  })
  login.once('authenticated', async () => {
    record.status = 'processing'
    record.message = 'Steam ist bestätigt. Bibliothek und Lizenzdaten werden gelesen.'
    try {
      const refreshToken = login.refreshToken
      record.result = await collectLibrary(refreshToken, login.steamID)
      record.result.account_name = String(login.accountName || '')
      record.result.refresh_token = refreshToken
      record.status = 'complete'
      record.message = `${record.result.games.length} Steam-Spiele wurden gelesen.`
      record.expiresAt = Date.now() + resultRetentionMs
    } catch (error) {
      record.status = 'failed'
      record.message = error instanceof Error ? error.message : String(error)
      record.expiresAt = Date.now() + resultRetentionMs
    } finally {
      login.accessToken = undefined
      login.refreshToken = undefined
    }
  })
  login.once('timeout', () => {
    record.status = 'failed'
    record.message = 'Die Steam-Anmeldung ist abgelaufen. Bitte einen neuen QR-Code anfordern.'
    record.expiresAt = Date.now() + resultRetentionMs
  })
  login.once('error', (error) => {
    record.status = 'failed'
    record.message = error instanceof Error ? error.message : String(error)
    record.expiresAt = Date.now() + resultRetentionMs
  })

  return {
    state: id,
    qr_data_url: await QRCode.toDataURL(result.qrChallengeUrl, {
      errorCorrectionLevel: 'M',
      margin: 1,
      width: 300
    }),
    expires_in: Math.floor(loginTimeoutMs / 1000)
  }
}

function cleanupSessions() {
  const now = Date.now()
  for (const [id, record] of sessions) {
    if (record.expiresAt <= now) sessions.delete(id)
  }
}

const server = createServer(async (request, response) => {
  cleanupSessions()
  try {
    if (request.method === 'GET' && request.url === '/health') {
      sendJson(response, 200, { status: 'ok' })
      return
    }
    if (request.method === 'POST' && request.url === '/sessions') {
      sendJson(response, 201, await startSession())
      return
    }
    if (request.method === 'POST' && request.url === '/libraries') {
      const payload = await readJson(request)
      const refreshToken = String(payload.refresh_token || '')
      const steamID = String(payload.steam_id || '')
      if (!refreshToken || !/^\d{17}$/.test(steamID)) {
        sendJson(response, 400, { detail: 'Steam-Token oder SteamID fehlt.' })
        return
      }
      sendJson(response, 200, await collectLibrary(refreshToken, steamID))
      return
    }
    const match = request.method === 'GET' && request.url?.match(/^\/sessions\/([0-9a-f-]+)$/i)
    if (match) {
      const record = sessions.get(match[1])
      if (!record) {
        sendJson(response, 404, { status: 'failed', message: 'Steam-Anmeldung wurde nicht gefunden oder ist abgelaufen.' })
        return
      }
      const result = {
        status: record.status,
        message: record.message,
        ...(record.status === 'complete' ? record.result : {})
      }
      sendJson(response, 200, result)
      if (record.status === 'complete') {
        delete record.result.refresh_token
        sessions.delete(match[1])
      }
      return
    }
    sendJson(response, 404, { detail: 'not found' })
  } catch (error) {
    sendJson(response, 502, { detail: error instanceof Error ? error.message : String(error) })
  }
})

server.listen(port, '0.0.0.0')
