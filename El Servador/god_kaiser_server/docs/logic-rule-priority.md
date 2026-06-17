# Logic-Regel `priority` (Operatoren)

Das Feld **`priority`** bei Cross-ESP-Logikregeln (REST: `LogicRuleCreate` / `LogicRuleUpdate` / `LogicRuleResponse`) hat eine feste Bedeutung:

- **Kleinere Zahl = höhere Priorität** bei **Konfliktauflösung** (welche Regel denselben Aktor zuerst/durchsetzend steuert) und bei der **typischen Ausführungsreihenfolge** (aktivierte Regeln werden aus der Datenbank mit `priority` aufsteigend gelesen).
- Üblicher Wertebereich **1–100**; das ist eine Konvention, keine harte technische Grenze über die Schema-Grenzen hinaus.

Details in Code: `ConflictManager` (`src/services/logic/safety/conflict_manager.py`), `LogicRepository.get_enabled_rules` (`src/db/repositories/logic_repo.py`), OpenAPI-Beschreibung in `src/schemas/logic.py`.
