import fs from 'node:fs'
import path from 'node:path'

const projectRoot = process.argv[2] || '/app'
const outputDirectory = process.argv[3] || '/out'
const lock = JSON.parse(fs.readFileSync(path.join(projectRoot, 'package-lock.json'), 'utf8'))
const inventory = ['package\tversion\tlicense\tsource']
const notices = [
  'Frontend dependency license documents',
  '=======================================',
  '',
  'Generated from the exact npm lockfile and installed dependency tree.',
  ''
]
const components = []

const packages = Object.entries(lock.packages || {})
  .filter(([packagePath]) => packagePath.startsWith('node_modules/'))
  .sort(([left], [right]) => left.localeCompare(right, 'en', { sensitivity: 'base' }))

for (const [packagePath, metadata] of packages) {
  const name = packagePath.replace(/^.*node_modules\//, '')
  const source =
    typeof metadata.repository === 'string'
      ? metadata.repository
      : metadata.repository?.url || metadata.homepage || ''
  inventory.push(
    [name, metadata.version || '', metadata.license || 'UNKNOWN', source]
      .map((value) => String(value).replaceAll('\t', ' '))
      .join('\t')
  )
  components.push({
    type: 'library',
    name,
    version: metadata.version || '',
    purl: `pkg:npm/${encodeURIComponent(name)}@${encodeURIComponent(metadata.version || '')}`,
    licenses: [{ license: { name: metadata.license || 'UNKNOWN' } }]
  })

  const installedPath = path.join(projectRoot, packagePath)
  if (!fs.existsSync(installedPath)) continue
  const documents = fs
    .readdirSync(installedPath)
    .filter((filename) => /^(license|copying|notice|authors)/i.test(filename))
    .sort((left, right) => left.localeCompare(right, 'en', { sensitivity: 'base' }))

  for (const filename of documents) {
    const documentPath = path.join(installedPath, filename)
    if (!fs.statSync(documentPath).isFile()) continue
    notices.push(
      '',
      '-'.repeat(78),
      `${name} ${metadata.version || ''}: ${filename}`,
      '-'.repeat(78),
      fs.readFileSync(documentPath, 'utf8').trimEnd()
    )
  }
}

fs.mkdirSync(outputDirectory, { recursive: true })
fs.writeFileSync(path.join(outputDirectory, 'frontend-dependencies.tsv'), `${inventory.join('\n')}\n`)
fs.writeFileSync(
  path.join(outputDirectory, 'frontend-dependency-licenses.txt'),
  `${notices.join('\n')}\n`
)
fs.writeFileSync(
  path.join(outputDirectory, 'frontend.cdx.json'),
  `${JSON.stringify(
    {
      bomFormat: 'CycloneDX',
      specVersion: '1.5',
      version: 1,
      metadata: {
        component: {
          type: 'application',
          name: 'lan-party-game-finder-frontend',
          version: '0.1.0'
        }
      },
      components
    },
    null,
    2
  )}\n`
)
