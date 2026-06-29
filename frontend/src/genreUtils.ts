const uuidPattern = /\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b/i
const objectFieldPattern = /['"]?[A-Za-z_][A-Za-z0-9_ ]*['"]?\s*:/

export function isPlausibleGenre(value: string) {
  const genre = value.trim()
  if (!genre || genre.length > 80) return false
  if (/[{}\[\]]/.test(genre)) return false
  if (objectFieldPattern.test(genre) || uuidPattern.test(genre)) return false
  if (['true', 'false', 'none', 'null', 'nan'].includes(genre.toLocaleLowerCase())) return false
  return /\p{L}/u.test(genre)
}
