## Zweck
Kompletter Ablauf für Setup/Login, Token-Handling, Routing-Guards und API-Kommunikation zwischen Frontend (Vue 3) und Backend (FastAPI). Bezieht sich auf aktuellen Code in `El Frontend` und `El Servador`.

## Kern-Dateien (Frontend)
- `src/api/index.ts`: Axios-Instanz, BaseURL `/api/v1`, Request-Interceptor setzt `Authorization: Bearer <accessToken>`, Response-Interceptor führt Refresh aus.
- `src/api/auth.ts`: Auth-Endpunkte (`/auth/status`, `/auth/setup`, `/auth/login`, `/auth/refresh`, `/auth/me`, `/auth/logout`).
- `src/stores/auth.ts`: Pinia-Store (User, Tokens, Setup-Flag, Error), LocalStorage-Persistenz.
- `src/router/index.ts`: Guards für Setup-Zwang, Auth-Pflicht, Admin-Only-Routen.
- `src/types/index.ts`: Auth DTOs (LoginRequest, SetupRequest, TokenResponse, User).
- Storage-Keys: `el_frontend_access_token`, `el_frontend_refresh_token`.

## Backend-Referenz
- REST-Pfade: `El Servador/god_kaiser_server/src/api/v1/auth.py` (Login/Setup/Refresh/Me/Logout), `src/api/v1/` für weitere Ressourcen.
- DB: SQLite `god_kaiser_dev.db` via SQLAlchemy (`src/db/models/`); Details siehe `Datenbanken.md`.

## Endpunkte & Daten
- `/auth/status` → `{ setup_required: bool, user_count: int }`
- `/auth/setup` (POST SetupRequest) → TokenResponse
- `/auth/login` (POST LoginRequest) → TokenResponse
- `/auth/refresh` (POST { refresh_token }) → TokenResponse
- `/auth/me` → `{ success, data: User }`
- `/auth/logout` (POST { logout_all? })

## Setup-Flow (Erststart)
1) Beim ersten Laden ruft Router-Guard `authStore.checkAuthStatus()` → `/auth/status`.
2) Wenn `setup_required=true`, wird auf `/setup` umgeleitet.
3) `SetupView.vue` nutzt `authStore.setup()` → `/auth/setup` → speichert Tokens → `/auth/me` → `setupRequired=false`.
4) Danach regulärer Auth-Flow.

## Login-Flow (Normalbetrieb)
1) `LoginView.vue` → `authStore.login(credentials)` → `/auth/login`.
2) `setTokens()` speichert Access/Refresh in LocalStorage und State.
3) Sofort `/auth/me` zum Laden des Users.
4) `isAuthenticated` = AccessToken + User vorhanden; Guards lassen geschützte Routen zu.

## Token-Refresh & Invalidierung
- Response-Interceptor: Bei 401 + vorhandener `refreshToken` und `_retry`==false → `authStore.refreshTokens()` → `/auth/refresh`.
- Erfolgreich: Tokens ersetzt, `/auth/me` erneut.
- Fehlgeschlagen: `clearAuth()` löscht Storage, Redirect `/login`.
- Logout: `/auth/logout` (optional `logout_all`), danach `clearAuth()`.

## Routing-Logik
- `requiresAuth` (alle Kinder von `/`) → Redirect zu `/login` wenn nicht authentifiziert.
- `requiresAdmin` (Mock ESP Views) → Redirect `dashboard` wenn Rolle ≠ admin.
- `setup_required=true` → immer Redirect `/setup` (außer Setup-Route).
- Authentifizierte Nutzer dürfen nicht auf `/login` oder `/setup` (werden auf Dashboard geleitet).

## Tokens & Storage
- Persistenz: LocalStorage Schlüssel `el_frontend_access_token`, `el_frontend_refresh_token` (gesetzt in `setTokens`, gelöscht in `clearAuth`).
- Sauber-Start: LocalStorage für `http://localhost:5173` leeren oder Inkognito-Fenster.
- Fehler „Not enough segments“ / 401-Refresh-Loop: Tokens korrupt → Storage löschen, neu einloggen.

## Kommunikationspfade (vereinfachter Sequenz)
Frontend → `/auth/status` → entscheidet Setup/Login → `/auth/login` oder `/auth/setup` → speichert Tokens → `/auth/me` → Router lässt geschützte Views zu. Bei 401 → `/auth/refresh` via Interceptor → setzt Token neu oder logout.

## Tests/Fehlerbehebung
- 401 nach Login: Prüfen, ob Backend-DB frisch ist und Setup ausgeführt; evtl. alte Tokens löschen.
- Endlos Refresh: Storage löschen; sicherstellen, dass Backend läuft.
- MQTT nicht verbunden: Backend-Log meldet ConnectionRefused (Broker fehlt) – Auth-Flow nicht betroffen.
- **Detaillierte Bug-Dokumentation:** Siehe `Bugs_Found.md` für alle gefundenen Bugs mit Workflows und Lösungen.

## Verwandte Dokumentation
- **Startup-Anleitung für KI:** `DEBUG_ARCHITECTURE.md` Section 0
- **API-Referenz:** `APIs.md`
- **Bug-Tracking:** `Bugs_Found.md`