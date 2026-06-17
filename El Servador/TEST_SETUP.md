# Test Setup Guide - Repository Tests

## Voraussetzungen

Die Repository-Tests benötigen folgende Dependencies:

- pytest >= 8.0.0
- pytest-asyncio >= 0.23.3
- pytest-cov >= 4.1.0
- sqlalchemy >= 2.0.25
- aiosqlite (für SQLite in-memory Tests)
- pydantic >= 2.5.3
- passlib[bcrypt]
- python-jose[cryptography]

## Option 1: Mit Poetry (Empfohlen)

```bash
# Poetry installieren (falls nicht vorhanden)
# Windows PowerShell:
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | python -

# Poetry zum PATH hinzufügen (siehe Poetry-Dokumentation)

# Dependencies installieren
cd "El Servador"
poetry install

# Tests ausführen
poetry run pytest god_kaiser_server/tests/unit/test_repositories_*.py -v

# Mit Coverage
poetry run pytest god_kaiser_server/tests/unit/test_repositories_*.py --cov=god_kaiser_server.src.db.repositories --cov-report=html
```

## Option 2: Mit pip und virtuellem Environment

```bash
cd "El Servador"

# Virtuelles Environment erstellen
python -m venv venv

# Aktivieren (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Dependencies installieren
pip install pytest pytest-asyncio pytest-cov aiosqlite sqlalchemy pydantic "passlib[bcrypt]" "python-jose[cryptography]"

# PYTHONPATH setzen
$env:PYTHONPATH = "god_kaiser_server\src"

# Tests ausführen
pytest god_kaiser_server/tests/unit/test_repositories_*.py -v

# Mit Coverage
pytest god_kaiser_server/tests/unit/test_repositories_*.py --cov=god_kaiser_server.src.db.repositories --cov-report=html
```

## Option 3: Direkt mit pip (ohne venv)

```bash
cd "El Servador"

# Dependencies installieren
pip install pytest pytest-asyncio pytest-cov aiosqlite sqlalchemy pydantic "passlib[bcrypt]" "python-jose[cryptography]"

# PYTHONPATH setzen
$env:PYTHONPATH = "god_kaiser_server\src"

# Tests ausführen
python -m pytest god_kaiser_server/tests/unit/test_repositories_*.py -v
```

## Test-Dateien

Die folgenden Test-Dateien wurden erstellt:

- `god_kaiser_server/tests/conftest.py` - Test-Fixtures (DB-Session, Repositories)
- `god_kaiser_server/tests/unit/test_repositories_base.py` - BaseRepository Tests
- `god_kaiser_server/tests/unit/test_repositories_esp.py` - ESPRepository Tests
- `god_kaiser_server/tests/unit/test_repositories_sensor.py` - SensorRepository Tests
- `god_kaiser_server/tests/unit/test_repositories_actuator.py` - ActuatorRepository Tests
- `god_kaiser_server/tests/unit/test_repositories_user.py` - UserRepository Tests

## Erwartete Ergebnisse

Alle Tests sollten erfolgreich durchlaufen. Die Tests verwenden SQLite in-memory Database für schnelle, isolierte Tests.

**Test-Coverage Ziel:** >80% für alle Repository-Module (Phase 2 Anforderung)



























