# Designanforderungen (Frontend)

## Zweck
- Codebase-Analyse des Frontends mit Fokus auf UX/Responsive/Modularität.
- Debug-Frontend wird schrittweise zum produktiven UI; Design soll bereits realistisch zum späteren Betrieb passen.
- Server gibt die Wahrheit vor (El Servador); Mock ESP richtet sich an echte El-Trabajante-Schemas aus.

## Bestehende Dokumentation (bitte verlinken, nicht duplizieren)
- `.claude/CLAUDE_FRONTEND.md`: Schnell-Orientierung zu Entry Points, Routing, Stores, API-Layer, Troubleshooting.
- `El Frontend/Docs/DEBUG_ARCHITECTURE.md`: Startbefehle, Auth/WS/Mock-Flows.
- `El Frontend/Docs/APIs.md`: Endpoint-Tabelle + DTO-Referenzen.
- `El Frontend/Docs/Admin oder user erstellen, Tokenverifizierung und Verbindungslogik.md`: Auth-/Token-/Guard-Flow.
- Server-Pendant: `.claude/CLAUDE_SERVER.md` (für Abgleich der Payloads).

## Codebasis – relevante Stellen für Design/UX
- Einstieg & Navigation: `src/main.ts`, `src/App.vue`, `src/router/index.ts` (Guards, Rollen).
- Layout/Theme: `src/components/layout/{MainLayout,AppHeader,AppSidebar}.vue`, globale Styles `src/style.css`, theming in `src/assets/styles/`.
- API/Types (Server-Truth): `src/api/index.ts`, `src/api/auth.ts`, `src/api/debug.ts`, `src/types/index.ts`.
- Feature-Views: `src/views/` (Dashboard, Sensors, Actuators, Logic, Settings, MockEsp*, MqttLog).
- UI-Bausteine: `src/components/common/*` (Buttons/Cards/Modals etc.), Feature-spezifische Unterordner `components/{sensors,actuators,logic,mock,mqtt,settings,zones}`.

## UX/Design-Leitplanken
- Responsive für Handy bis Wand-Display; Touch-first und Drag & Drop vorgesehen (künftige Implementierungen in `components/common` oder `src/composables/` verorten).
- Industrielles, modernes Layout mit klarer Informationshierarchie; Farbgebung/Aufteilung wie aktuelles Debug-UI beibehalten.
- Datenbank-/Server-zentriert: Frontend zeigt stets Server-Wahrheit, filter- und sortierbar; dynamisch konfigurierbare Panels/Listen.
- Modularität: Widgets/Listen sollen sich je nach User-Einstellung anpassen; spätere echte ESPs nutzen dieselben Strukturen wie Mock.

## Feature-Slices (Wo ansetzen, ohne Doppel-Doku)
- **Visuelles/Layout**: Layout-Komponenten + globale Styles oben; Details zu Start/Build in `DEBUG_ARCHITECTURE.md`.
- **Daten & Filter**: Views `SensorsView.vue`, `ActuatorsView.vue`, `MqttLogView.vue`, `MockEspView.vue`/`MockEspDetailView.vue`; API-Schema siehe `Docs/APIs.md`.
- **Logic (Builder-Placeholder)**: `views/LogicView.vue` (siehe Hinweise in `.claude/CLAUDE_FRONTEND.md` Section „Logic Engine“).
- **Settings/Clients/Zonen**: `SettingsView.vue`, `components/settings/*`, `components/zones/*` – hier nur ergänzen, falls neue UX-Logik hinzukommt.
- **Auth/Rollen**: Guards/Store (`router/index.ts`, `stores/auth.ts`) – für Flows immer auf bestehende Auth-Doku verweisen.

## Migration Debug → Produktion
- Mock-ESP folgt echten Server-Schemas (`src/api/debug.ts` spiegelt `/debug/mock-esp`); beim Umstieg auf echte ESPs bleiben UI/Flows identisch.
- Änderungen an Payloads/DTOs stets mit `.claude/CLAUDE_SERVER.md` und `El Frontend/Docs/APIs.md` abgleichen, nicht lokal duplizieren.