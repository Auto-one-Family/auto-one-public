# Google Sheets Integration — Auth Bootstrap (S1)

Stand: 2026-05-23 — Linear AUT-443 (Parent AUT-442).

Dieses Modul kapselt das **Service-Account-basierte Auth-Setup** fuer den
geplanten Sheets-Export. Es liefert ausschliesslich:

1. eine `SheetsExportSettings`-Konfiguration in `src/core/config.py`,
2. eine Startup-Validierung (`validate_credentials_config`) im FastAPI-Lifespan,
3. einen Lazy-Loader (`load_service_account_credentials`) fuer S2+.

Die eigentliche Export-Pipeline (Scheduler, Tab-Rotation, Cursor) ist
**explizit nicht Teil von S1** und folgt in den Sub-Issues S2-S5.

## Architektur-Entscheidungen (von Robin/TM fixiert)

| Frage | Entscheidung |
|-------|-------------|
| E1 Auth | Service-Account + Sheet-Share (kein DWD) |
| E2 Service | Eigenstaendiger `SheetsExportService` (kommt in S2) |
| E3 Rotation | Monatliche Tab-Rotation (kommt in S2/S3) |
| E4 Idempotenz | Cursor in `system_config` (kommt in S2/S4) |

## Provisionierung (Operator-Runbook)

1. **Google Cloud Project** im `11grower`-Workspace anlegen oder
   wiederverwenden (`gcloud projects create autoone-sheets` o. ae.).
2. **Sheets API + Drive API aktivieren** (UI: APIs & Services → Library).
3. **Service-Account erstellen**:
   - Name: `autoone-sheets-exporter`
   - Role: keine projektweiten Rollen noetig (Sheet-Share reicht).
4. **JSON-Key generieren** und auf das Zielsystem laden, z. B. nach
   `/secrets/sheets_sa.json`. Datei-Permission auf `0600` setzen:

   ```bash
   sudo install -m 0600 -o root -g root sheets_sa.json /secrets/sheets_sa.json
   ```

5. **Spreadsheet im 11grower-Workspace** anlegen (Owner: Robin) und teilen:
   - `christoph@…` als **Editor**
   - `autoone-sheets-exporter@<projekt>.iam.gserviceaccount.com` als
     **Editor** (Mail steht im JSON-Feld `client_email`).
6. **Spreadsheet-ID** aus der URL extrahieren (Teil zwischen `/d/` und `/edit`).

## ENV-Variablen

```bash
# Master-Switch, Default false. Erst aktivieren wenn JSON-Datei vorhanden ist.
SHEETS_EXPORT_ENABLED=true

# Absoluter Pfad zur SA-JSON. Niemals committen.
SHEETS_SA_CREDENTIALS_PATH=/secrets/sheets_sa.json

# Optional in S1, Pflicht ab S2.
SHEETS_SPREADSHEET_ID=1AbC...xyz
```

In Docker setzt man die JSON-Datei am besten als Bind-Mount oder Docker-Secret:

```yaml
# docker-compose override (Beispiel — NICHT in repo committen)
services:
  el-servador:
    environment:
      SHEETS_EXPORT_ENABLED: "true"
      SHEETS_SA_CREDENTIALS_PATH: /run/secrets/sheets_sa.json
      SHEETS_SPREADSHEET_ID: ${SHEETS_SPREADSHEET_ID}
    secrets:
      - sheets_sa.json

secrets:
  sheets_sa.json:
    file: ./secrets/sheets_sa.json   # ausserhalb Git
```

## Startup-Verhalten

- `SHEETS_EXPORT_ENABLED=false` (Default): `validate_credentials_config()`
  ist ein No-Op und loggt nur `debug`. Der Server startet wie bisher.
- `SHEETS_EXPORT_ENABLED=true`:
  - Pfad muss absolut sein und auf eine existierende Datei zeigen.
  - JSON muss valide sein und die Felder `type=service_account`,
    `project_id`, `private_key`, `client_email`, `token_uri` besitzen.
  - Bei Verletzung: `SheetsAuthError` (`ConfigErrorCode.SHEETS_*`,
    Bereich 5050-5054). Server bricht im FastAPI-Lifespan ab — bewusst
    fail-fast, damit kein "broken-by-config"-Service hochkommt.
- Erfolg: ein einzelner `INFO`-Log mit `project_id` und `client_email`
  (kein Private-Key, kein Token).

## Verwendung in S2+

```python
from src.integrations.sheets import load_service_account_credentials

creds = load_service_account_credentials()
import gspread
client = gspread.authorize(creds)
```

`load_service_account_credentials()` importiert `google-auth` lazy. Wenn
das Paket fehlt, gibt es einen klaren `SheetsAuthError` mit Code
`5054 (SHEETS_DEPENDENCY_MISSING)` statt `ImportError` beim Start.

## Sicherheits-Regeln

- **Niemals** Service-Account-JSON in Git einchecken — `.gitignore` deckt
  `**/secrets/`, `*.sa.json`, `**/sheets_sa*.json` ab.
- **Niemals** den Pfad oder den Inhalt der JSON in API-Responses leaken.
- **Bei Schluessel-Rotation** (E3): neuen Key in `/secrets/` ablegen,
  alten Key in Google Cloud disablen, Server neu starten — kein Code-Change
  noetig.

## Verifikation

```bash
cd "/home/robin/autoone/El Servador/god_kaiser_server"
poetry run pytest tests/unit/integrations/test_sheets_auth.py -v
poetry run ruff check src/integrations/sheets/ src/core/config.py
```
