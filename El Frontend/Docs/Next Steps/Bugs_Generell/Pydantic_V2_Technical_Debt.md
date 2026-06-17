# Bug Report: Technical Debt - Pydantic V2 Deprecation Warnings

**Erstellt:** 2026-01-29
**Priorität:** LOW (nicht blockierend)
**Status:** OPEN
**Kategorie:** Technical Debt / Refactoring

---

## 1. Zusammenfassung

Bei Test-Ausführungen erscheinen 7 Pydantic Deprecation Warnings:

```
PydanticDeprecatedSince20: Support for class-based `config` is deprecated,
use ConfigDict instead. Deprecated in Pydantic V2.0 to be removed in V3.0.
```

---

## 2. Betroffene Dateien

| Datei | Zeile | Klasse |
|-------|-------|--------|
| `src/api/schemas.py` | 15 | `SensorProcessRequest` |
| `src/api/schemas.py` | 98 | `SensorProcessResponse` |
| `src/api/schemas.py` | 156 | `ErrorResponse` |
| `src/api/schemas.py` | 204 | `SensorCalibrateRequest` |
| `src/api/schemas.py` | 277 | `SensorCalibrateResponse` |
| `src/api/v1/audit.py` | 38 | `AuditLogResponse` |
| `src/schemas/sequence.py` | 111 | `SequenceProgressSchema` |

---

## 3. Technischer Hintergrund

### Aktuelles Pattern (deprecated):
```python
class SensorProcessRequest(BaseModel):
    field: str

    class Config:
        from_attributes = True
```

### Neues Pattern (Pydantic V2):
```python
from pydantic import ConfigDict

class SensorProcessRequest(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    field: str
```

---

## 4. Auswirkung

| Aspekt | Bewertung |
|--------|-----------|
| **Funktionalität** | Keine - Code funktioniert |
| **Tests** | Keine - Tests laufen durch |
| **Zukunftssicherheit** | Wird in Pydantic V3 brechen |
| **Dringlichkeit** | Niedrig - Pydantic V3 noch nicht released |

---

## 5. Empfohlene Aktion

**Wann:** Bei nächster geplanter Code-Cleanup-Runde oder Pydantic V3 Migration

**Aufwand:** ~30 Minuten (7 Klassen umstellen)

**Vorgehen:**
1. Alle betroffenen Dateien öffnen
2. `class Config:` durch `model_config = ConfigDict(...)` ersetzen
3. `from pydantic import ConfigDict` importieren
4. Tests ausführen zur Verifikation

---

## 6. Referenz

- [Pydantic V2 Migration Guide](https://docs.pydantic.dev/2.0/migration/)
- Test-Output: `poetry run python -m pytest tests/esp32/test_communication.py -v`

---

**Erstellt von:** Claude Opus 4.5
**Co-Authored-By:** Claude Opus 4.5 <noreply@anthropic.com>
