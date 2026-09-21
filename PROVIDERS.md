# Provider integration status

The project is not affiliated with or endorsed by any game platform. API and
account terms remain binding independently of this project's MIT license.

`UNOFFICIAL_PROVIDER_INTEGRATIONS_ENABLED` is `false` by default. Setting it to
`true` enables all experimental direct integrations listed below. Playnite and
GOG Galaxy imports remain available without that switch.

| Source | Method | Default | Notes |
| --- | --- | --- | --- |
| Steam | Official Web API, OpenID; optional Steam client protocol through open-source Node libraries | Enabled | Each operator needs their own confidential Web API key. QR login stores a renewable token; OpenID and Community ID do not. |
| Xbox PC | Microsoft OAuth device-code login and Xbox title history | Enabled when a client ID is configured | May omit unplayed Microsoft Store purchases and intentionally filters console-only titles. |
| Playnite | Local backup import | Enabled | Preferred broad compatibility path. Uploads can contain personal library and playtime data. |
| GOG Galaxy | Local database import | Enabled | Reads local library data only; plugin login caches are not imported. |
| Epic | Legendary command-line client | Experimental | Unofficial integration; Legendary is a separate GPL-licensed program. |
| GOG direct | GOG Galaxy-compatible OAuth and web APIs | Experimental | Unofficial and subject to change or revocation. |
| Ubisoft | Ubisoft web-service session and library calls | Experimental | The server temporarily receives login credentials during setup and stores the resulting session, not the password. Prefer local imports when possible. |
| EA | Browser-captured bearer token and undocumented GraphQL calls | Experimental | High terms and stability risk; prefer Playnite or GOG Galaxy. |
| Amazon Games | Launcher-compatible authentication and entitlement calls | Experimental | Unofficial and subject to change. |
| Battle.net | User-approved browser-session request | Experimental | Uses a copied session request; revoke the provider session after suspected exposure. |
| Humble | User-approved browser-session request | Experimental | Reads library and unredeemed key information. |
| Meta/Oculus | User-approved browser-session request | Experimental | Stores the token needed for the library request. |

The `GOG_CLIENT_ID` and `GOG_CLIENT_SECRET` values used by the optional direct
GOG flow are public installed-client protocol identifiers, not confidential
operator credentials. They are included for compatibility with the Galaxy
OAuth flow and can still be changed or revoked by GOG without notice.

Experimental integrations can fail without notice, be rate-limited, or be
blocked by the provider. Operators should review current terms before enabling
them and must obtain the account owner's informed agreement.

Provider credentials are written atomically with owner-only filesystem modes.
Deleting or disconnecting an account removes its local provider credentials;
operators should also revoke sessions at the provider when appropriate.
