# Third-Party Notices

This project is distributed under the MIT License. It uses and interoperates
with third-party software and data sources that remain subject to their own
licenses and terms. The project is not affiliated with, endorsed by, or
sponsored by any game platform or metadata provider named below.

## Material References

### Playnite

- Project: https://github.com/JosefNemec/Playnite
- Reference revision: `02fc1972a1f0c4b7e5f2bc2b91d8dfe643141965`
- Copyright: Copyright (c) 2020 Josef Nemec
- License: MIT
- Local license copy: `LICENSES/Playnite-MIT.txt`

The Playnite backup importer implements compatibility with Playnite's exported
library format. Playnite itself is not bundled with this application.

### Jeshibu PlayniteExtensions

- Project: https://github.com/Jeshibu/PlayniteExtensions
- Reference revision: `0db3630dc6763b5ae222666a2fa0e994f4969603`
- Copyright: Copyright (c) 2025 Jeshibu
- License: MIT
- Local license copy: `LICENSES/PlayniteExtensions-MIT.txt`

The EA provider was informed by the EA Library integration, including its
documented request structure, persisted-query identifiers, pagination
behaviour, and playtime lookup. The implementation in this repository is a
separate Python implementation.

### FriendsOfGalaxy GOG Galaxy Integrations

- Ubisoft/Uplay project: https://github.com/FriendsOfGalaxy/galaxy-integration-uplay
- Ubisoft/Uplay reference revision: `61d24e4ed0f1b2378252142e5ee2c92cd309612b`
- Copyright: Copyright (c) 2019 FriendsOfGalaxy
- License: MIT
- Local license copy: `LICENSES/FriendsOfGalaxy-Uplay-MIT.txt`

The Ubisoft provider was informed by the Galaxy Uplay integration's direct
Ubisoft Club GraphQL library request and PC-platform filtering. The
implementation in this repository is a separate Python implementation.

- Origin project: https://github.com/FriendsOfGalaxy/galaxy-integration-origin
- Origin reference revision: `350b11a62fd46ae5124d1edb94c1d1d94fe66110`

The EA provider's legacy Origin fallback was informed by the Origin
integration's documented identity, entitlement, and offer-detail endpoints.
No source code from that repository is incorporated in this project.

### DoctorMcKay Steam Libraries

- Projects: https://github.com/DoctorMcKay/node-steam-session and https://github.com/DoctorMcKay/node-steam-user
- Packages: `steam-session` 1.9.4 and `steam-user` 5.3.0
- License: MIT

The helper also uses `qrcode` 1.5.4 (MIT) to render the challenge supplied by
Steam as an image in the browser. Its transitive `node-bignumber` dependency
contains the Tom Wu and Kenji Urushima notices reproduced in
`LICENSES/node-bignumber-MIT.txt`.

The internal Steam helper uses these libraries for the user-approved QR login
and the reading of Steam license data. A renewable login token is stored in the
protected backend provider-auth volume for later synchronizations. It is never
returned to the browser and is removed when the linked account is deleted.
Users may instead authenticate through Steam's official OpenID 2.0 endpoint or
manually connect a public Steam Community profile. These modes store no Steam
login token and do not use this helper, but cannot read private libraries or
Steam license acquisition dates. The OpenID flow sends passwords and Steam
Guard data only to Steam and returns only the verified SteamID to this app.

### Legendary

- Project: https://github.com/legendary-gl/legendary
- Package: `legendary-gl`
- Version locked by this release: 0.21.1
- License: GNU General Public License v3 or later
- Local license copy: `LICENSES/Legendary-GPL-3.0-or-later.txt`
- Corresponding source: https://github.com/legendary-gl/legendary/tree/0.21.1

Legendary is installed unmodified in the backend image and invoked as a
separate command-line process for Epic authentication and library access. It
is not linked into the application source. Recipients of a distributed image
must retain the GPL notice and access to the corresponding Legendary source.

## Direct Runtime Dependencies

| Component | Purpose | License |
| --- | --- | --- |
| FastAPI, Pydantic | Backend API and validation | MIT |
| Uvicorn, HTTPX | HTTP server and client | BSD-3-Clause |
| SQLAlchemy, Alembic | Persistence and migrations | MIT |
| Psycopg / psycopg-binary | PostgreSQL driver | LGPL-3.0-only |
| RapidFuzz | Game-title matching | MIT |
| python-multipart | Upload parsing | Apache-2.0 |
| Vue, Vue Router, Pinia, Vuetify | Frontend | MIT |
| Material Design Icons (`@mdi/js`) | Icons | Apache-2.0 |
| nginx | Frontend and local gateway | BSD-2-Clause |
| PostgreSQL | Database server | PostgreSQL License |

Package/version/license inventories for the backend runtime, frontend and
Steam helper are stored in:

- `LICENSES/backend-dependencies.tsv`
- `LICENSES/frontend-dependencies.tsv`
- `LICENSES/steam-helper-dependencies.tsv`
- `LICENSES/backend.cdx.json`
- `LICENSES/frontend.cdx.json`
- `LICENSES/steam-helper.cdx.json`

The standard license texts referenced by those inventories are included in
the `LICENSES` directory. The inventory generator scripts additionally collect
the package-specific copyright, license, and notice files from an installed
dependency tree. Container base images also contain operating-system packages
under their respective licenses.

Backend test dependencies are locked separately as the `test` group in
`backend/uv.lock` and are not included in the production backend image or its
runtime inventory. The build uses Astral's uv 0.11.0
(https://github.com/astral-sh/uv/tree/0.11.0, MIT OR Apache-2.0).
The uv executable is confined to build stages and is not copied into the
production or test image.

## Metadata and Platform Terms

Open-source licenses do not grant access to third-party services. The
following services are additionally governed by their API or user terms:

- Steam Web API: https://steamcommunity.com/dev/apiterms
- IGDB / Twitch: https://api-docs.igdb.com/ and
  https://legal.twitch.com/en/legal/developer-agreement/
- RAWG: https://rawg.io/apidocs and https://rawg.io/tos_api
- EA: https://www.ea.com/legal/user-agreement

RAWG requires a visible active link from pages displaying RAWG-derived data.
The application therefore displays permanent IGDB and RAWG source links in
its footer. Metadata may be cached locally but must not be redistributed as a
standalone third-party database.

Direct browser-session integrations are unofficial and can be restricted or
withdrawn by their providers. They must only be used by the account owner for
the private, non-commercial purpose described by this application.

## Trademarks and Game Media

Steam, Epic Games, GOG, Xbox, Ubisoft, EA, Amazon Games, Battle.net, Humble,
Meta/Oculus, Playnite, IGDB, RAWG, and all game titles and artwork are
trademarks or content of their respective owners. Their names are used only
to identify compatible services. Game covers and descriptions remain subject
to the terms and rights of the source from which they were obtained.
