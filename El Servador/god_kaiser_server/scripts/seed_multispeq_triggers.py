"""
MultispeQ Plant Trigger Seed Script (AUT-219).

Seeds 7 disabled CrossESPLogic rules covering the plant-specialised
trigger set documented in Linear AUT-219:

* LPAP-01 — Cutting Phi2 vitality (pre-shipment guard).
* LPAP-02 — Mother-plant PPFD (under-light alarm).
* CSC-01  — Bloom-room PPFD undershoot (Kim 2025 reference).
* CSC-02  — Bloom-bulk Phi2 + NPQt combination stress.
* GO-01   — Grow-Off measurement without external PAR cross-cal.
* GO-02   — Grow-Off Phi2 outlier (clean QA only).
* GO-03   — Grow-Off lamp metadata missing.

All rules are inserted with ``enabled=False`` so operators can review and
activate them per facility. Seeding is idempotent: existing rule_names
are skipped (Postgres ``ON CONFLICT (rule_name) DO NOTHING`` semantics
implemented application-side via existence check).

Pattern reference: ``scripts/seed_wokwi_esp.py``.

Schema notes
------------

The runtime engine (``services/logic_engine.py``) dispatches on
``condition.get("type")`` / ``action.get("type")``. The Linear issue
specifies ``condition_type`` / ``action_type`` which are kept verbatim
as additional fields, while the canonical ``type`` key is mirrored so
that the existing Pydantic validators in
``db/models/logic_validation.py`` accept the seeds and the LogicEngine
can route them once the rules are enabled.

The notification action additionally carries ``channel`` /
``message_template`` so the existing ``NotificationActionExecutor`` can
deliver the message; ``severity`` and ``message`` from the spec are
retained as extra fields for future Plants-specialised executors.

Usage
-----

::

    poetry run python scripts/seed_multispeq_triggers.py

Prerequisites
-------------

* Database must exist (run ``alembic upgrade head`` first).
* ``MetadataFilterEvaluator`` is registered in the Logic Engine
  (AUT-214, already merged on the multispeq waves).
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add project root to path so ``src.*`` imports resolve when invoked via
# ``python scripts/seed_multispeq_triggers.py`` (mirrors seed_wokwi_esp.py).
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select  # noqa: E402

from src.core.config import get_settings  # noqa: E402
from src.core.logging_config import get_logger  # noqa: E402
from src.db.models.logic import CrossESPLogic  # noqa: E402
from src.db.repositories.logic_repo import LogicRepository  # noqa: E402
from src.db.session import get_session  # noqa: E402

logger = get_logger(__name__)


# =============================================================================
# Trigger Definitions (AUT-219)
# =============================================================================

# Notification channel/target defaults — kept identical for every seeded
# trigger so operators can override per-rule via the standard logic API.
_DEFAULT_NOTIF_CHANNEL = "websocket"
_DEFAULT_NOTIF_TARGET = "broadcast"


def _notif(severity: str, message: str) -> dict[str, Any]:
    """
    Build a notification action dict that satisfies both the Linear spec
    (``action_type`` / ``severity`` / ``message``) and the existing
    Pydantic validator + ``NotificationActionExecutor`` contract
    (``type`` / ``channel`` / ``target`` / ``message_template``).
    """
    return {
        "type": "notification",
        "action_type": "notification",
        "channel": _DEFAULT_NOTIF_CHANNEL,
        "target": _DEFAULT_NOTIF_TARGET,
        "message_template": message,
        "severity": severity,
        "message": message,
    }


def _meta_filter(field: str, operator: str, value: Any = None) -> dict[str, Any]:
    """
    Build a metadata_filter condition dict (AUT-214) that satisfies both
    the Linear spec (``condition_type``) and the engine dispatch
    (``type``). ``value`` is omitted for nullary operators.
    """
    cond: dict[str, Any] = {
        "type": "metadata_filter",
        "condition_type": "metadata_filter",
        "field": field,
        "operator": operator,
    }
    if operator not in ("is_null", "is_not_null"):
        cond["value"] = value
    return cond


def _sensor_threshold(sensor_type: str, operator: str, value: float) -> dict[str, Any]:
    """
    Build a sensor_threshold condition dict for MultispeQ measurements.

    MultispeQ values arrive via the ingress endpoint (AUT-217) and are
    matched by ``sensor_type`` only; ``esp_id`` and ``gpio`` are set to
    the virtual MultispeQ device markers introduced in AUT-211. They are
    placeholders that the LogicEngine routing relies on once enabled.
    """
    return {
        "type": "sensor_threshold",
        "condition_type": "sensor_threshold",
        "esp_id": "MOCK_MULTISPEQ",
        "gpio": 0,
        "sensor_type": sensor_type,
        "operator": operator,
        "value": value,
    }


# Trigger specs follow the order documented in AUT-219.
TRIGGER_SPECS: list[dict[str, Any]] = [
    # -------------------------------------------------------------------
    # LPAP-01 — Stecklings-Phi2-Vitalitaet
    # -------------------------------------------------------------------
    {
        "rule_name": "LPAP-01-phi2-steckling",
        "description": (
            "LPAP-01: Steckling Phi2 < 0.50 mit phase=steckling_vor_versand und "
            "qa_flag=clean. Versand-Stopp pruefen."
        ),
        "logic_operator": "AND",
        "trigger_conditions": [
            _sensor_threshold("phi2", "<", 0.50),
            _meta_filter("sensor_metadata.phase", "eq", "steckling_vor_versand"),
            _meta_filter("sensor_metadata.qa_flag", "eq", "clean"),
        ],
        "actions": [
            _notif(
                severity="warning",
                message=(
                    "Steckling {plant_id} Phi2 = {value}. Unter Versand-Schwelle "
                    "0,50. Versand-Stopp pruefen."
                ),
            )
        ],
    },
    # -------------------------------------------------------------------
    # LPAP-02 — Mutterpflanzen-PPFD
    # -------------------------------------------------------------------
    {
        "rule_name": "LPAP-02-ppfd-mutter",
        "description": (
            "LPAP-02: PPFD < 300 in Mutter/Steckling-Wurzelung-Raum nach >60 min "
            "Licht-an. LED-Abstand pruefen."
        ),
        "logic_operator": "AND",
        "trigger_conditions": [
            _sensor_threshold("ppfd", "<", 300),
            _meta_filter(
                "sensor_metadata.phase",
                "in",
                ["mutter", "steckling_wurzelung"],
            ),
            _meta_filter("sensor_metadata.time_since_light_on_min", "gt", 60),
        ],
        "actions": [
            _notif(
                severity="warning",
                message=(
                    "Mutterpflanzenraum PPFD = {value} umol/m2/s — unter 300. LED-Abstand pruefen."
                ),
            )
        ],
    },
    # -------------------------------------------------------------------
    # CSC-01 — Bluetenraum-PPFD-Unterschreitung
    # -------------------------------------------------------------------
    {
        "rule_name": "CSC-01-ppfd-bluete",
        "description": (
            "CSC-01: PPFD < 600 in Bluete-Stretch/Bulk nach >120 min Licht-an. Kim 2025 Referenz."
        ),
        "logic_operator": "AND",
        "trigger_conditions": [
            _sensor_threshold("ppfd", "<", 600),
            _meta_filter(
                "sensor_metadata.phase",
                "in",
                ["bluete-stretch", "bluete-bulk"],
            ),
            _meta_filter("sensor_metadata.time_since_light_on_min", "gt", 120),
        ],
        "actions": [
            _notif(
                severity="warning",
                message=(
                    "Bluetenraum PPFD = {value}. Kim 2025: unter 600 umol "
                    "reduzierte CBD-Biosynthese. LED-Abstand pruefen."
                ),
            )
        ],
    },
    # -------------------------------------------------------------------
    # CSC-02 — Phi2 + NPQt Kombinations-Stress
    # -------------------------------------------------------------------
    {
        "rule_name": "CSC-02-phi2-npqt-kombistress",
        "description": (
            "CSC-02: Phi2 < 0.50 UND NPQt > 3.5 in Bluete-Bulk mit qa_flag=clean. "
            "Kombinations-Stress."
        ),
        "logic_operator": "AND",
        "trigger_conditions": [
            _sensor_threshold("phi2", "<", 0.50),
            _sensor_threshold("npqt", ">", 3.5),
            _meta_filter("sensor_metadata.phase", "eq", "bluete-bulk"),
            _meta_filter("sensor_metadata.qa_flag", "eq", "clean"),
        ],
        "actions": [
            _notif(
                severity="alarm",
                message=(
                    "Pflanze {plant_id} Bluete-Bulk: Phi2={phi2}, NPQt={npqt}. "
                    "Kombinations-Stress. Licht, Naehrstoffe, VPD pruefen."
                ),
            )
        ],
    },
    # -------------------------------------------------------------------
    # GO-01 — Grow-Off DLI ohne Cross-Cal
    # -------------------------------------------------------------------
    {
        "rule_name": "GO-01-growoff-no-crosscal",
        "description": (
            "GO-01: Grow-Off-Messung in Bluete ohne par_external_apogee Cross-Cal. "
            "Apogee MQ-500 dokumentieren."
        ),
        "logic_operator": "AND",
        "trigger_conditions": [
            _meta_filter("sensor_metadata.par_external_apogee", "is_null"),
            _meta_filter(
                "sensor_metadata.phase",
                "in",
                ["bluete-stretch", "bluete-bulk"],
            ),
            _meta_filter("sensor_metadata.measurement_context", "eq", "grow-off"),
        ],
        "actions": [
            _notif(
                severity="info",
                message=(
                    "Messung {timestamp} ohne externe PAR Cross-Cal. Fuer Grow-Off: "
                    "Apogee MQ-500-Wert parallel dokumentieren."
                ),
            )
        ],
    },
    # -------------------------------------------------------------------
    # GO-02 — Grow-Off Phi2 Outlier
    # -------------------------------------------------------------------
    {
        "rule_name": "GO-02-growoff-phi2-outlier",
        "description": (
            "GO-02: Grow-Off Bluete-Bulk Phi2 < 0.45 mit qa_flag=clean. "
            "Outlier-Event fuer Grow-Log."
        ),
        "logic_operator": "AND",
        "trigger_conditions": [
            _sensor_threshold("phi2", "<", 0.45),
            _meta_filter("sensor_metadata.phase", "eq", "bluete-bulk"),
            _meta_filter("sensor_metadata.measurement_context", "eq", "grow-off"),
            _meta_filter("sensor_metadata.qa_flag", "eq", "clean"),
        ],
        "actions": [
            _notif(
                severity="info",
                message=(
                    "Standort {plant_id} Phi2 = {value} — unter 0,45. "
                    "Outlier-Event. Grow-Log-Kommentar erganzen."
                ),
            )
        ],
    },
    # -------------------------------------------------------------------
    # GO-03 — Grow-Off LED-Metadaten fehlen
    # -------------------------------------------------------------------
    {
        "rule_name": "GO-03-growoff-led-metadata",
        "description": (
            "GO-03: Grow-Off-Messung ohne lamp_model ODER lamp_dimmer_pct. "
            "Lampen-Metadaten erganzen."
        ),
        "logic_operator": "OR",
        "trigger_conditions": [
            _meta_filter("sensor_metadata.lamp_model", "is_null"),
            _meta_filter("sensor_metadata.lamp_dimmer_pct", "is_null"),
        ],
        "actions": [
            _notif(
                severity="info",
                message=(
                    "Messung {timestamp} ohne Lampen-Metadaten. Lampenmodell + Dimmer-% erganzen."
                ),
            )
        ],
    },
]


# =============================================================================
# Seeding logic
# =============================================================================


async def seed_multispeq_triggers() -> dict[str, int]:
    """
    Insert all 7 plant triggers as ``CrossESPLogic`` rules with
    ``enabled=False``. Existing ``rule_name`` rows are left untouched
    (idempotent).

    Returns:
        Dictionary with counts:
        ``{"created": N, "existing": K, "failed": X}``.
    """
    results = {"created": 0, "existing": 0, "failed": 0}

    session_gen = get_session()
    session = await anext(session_gen)
    try:
        repo = LogicRepository(session)

        for spec in TRIGGER_SPECS:
            rule_name = spec["rule_name"]
            try:
                # ON CONFLICT (rule_name) DO NOTHING — application-side check
                # against the UNIQUE index on cross_esp_logic.rule_name.
                stmt = select(CrossESPLogic).where(CrossESPLogic.rule_name == rule_name)
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    logger.info("[OK] Trigger '%s' already exists — skipping", rule_name)
                    results["existing"] += 1
                    continue

                rule = CrossESPLogic(
                    rule_name=rule_name,
                    description=spec["description"],
                    enabled=False,  # AUT-219: ship disabled, operator activates
                    trigger_conditions=spec["trigger_conditions"],
                    logic_operator=spec["logic_operator"],
                    actions=spec["actions"],
                    priority=100,
                    cooldown_seconds=300,  # 5 min default for plant triggers
                    rule_metadata={
                        "category": "plants_multispeq",
                        "source": "AUT-219",
                        "seeded_by": "seed_multispeq_triggers",
                    },
                )
                await repo.create(rule)
                await session.commit()
                logger.info("[OK] Created trigger '%s' (enabled=False)", rule_name)
                results["created"] += 1

            except Exception as exc:  # noqa: BLE001 — report-and-continue
                logger.error("Failed to seed trigger '%s': %s", rule_name, exc, exc_info=True)
                await session.rollback()
                results["failed"] += 1
    except Exception:
        logger.error("Fatal error during MultispeQ trigger seed", exc_info=True)
        raise
    finally:
        await session_gen.aclose()

    return results


async def main() -> None:
    """CLI entry point — mirrors the layout of ``seed_wokwi_esp.py``."""
    print("=" * 60)
    print("MultispeQ Plant Trigger Seed Script (AUT-219)")
    print("=" * 60)
    print()

    db_url = get_settings().database.url
    print(f"Database URL: {db_url}")
    if db_url.startswith("sqlite"):
        print(
            "WARNING: SQLite is active. This does NOT seed the Docker/PostgreSQL "
            "stack. Set DATABASE_URL to PostgreSQL before running this script for "
            "the Docker setup."
        )
        print()

    print(f"Seeding {len(TRIGGER_SPECS)} plant triggers (enabled=False):")
    for i, spec in enumerate(TRIGGER_SPECS, start=1):
        print(f"  {i}. {spec['rule_name']}")
    print()

    try:
        results = await seed_multispeq_triggers()

        print()
        print("Results:")
        print(f"  Created:       {results['created']}")
        print(f"  Already exist: {results['existing']}")
        if results["failed"] > 0:
            print(f"  Failed:        {results['failed']}")
        print()

        if results["created"] > 0:
            print("Next steps:")
            print("  1. Operator: GET /v1/logic/rules — review the seeded triggers.")
            print("  2. Operator: PATCH /v1/logic/rules/{id} { enabled: true }")
            print("     to activate a trigger after facility-specific tuning.")
            print(
                "  3. AUT-217 ingress already routes MultispeQ measurements through "
                "LogicEngine.evaluate_sensor_data."
            )

        print()
        print("=" * 60)

        if results["failed"] > 0:
            sys.exit(1)

    except Exception as exc:  # noqa: BLE001 — top-level CLI handler
        print(f"\n[ERROR] {exc}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
