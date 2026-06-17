"""
Rate Limiter für Logic Engine

Begrenzt die Ausführungsrate von Rules auf verschiedenen Ebenen.
Nutzt BESTEHENDES max_executions_per_hour Feld aus CrossESPLogic.

INTEGRATION: Via LogicEngine._evaluate_rule()
PATTERN: Token Bucket Algorithmus für Global/ESP-Level, DB-Query für Rule-Level
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Konfiguration für Rate-Limiting."""

    max_per_second: int = 100  # Max Executions pro Sekunde (global)
    max_per_esp_second: int = 20  # Max Executions pro ESP pro Sekunde
    # max_per_rule_hour: Wird aus DB-Feld gelesen!
    burst_allowance: float = 1.5  # Burst-Faktor (50% über Limit kurzzeitig OK)


@dataclass
class RateLimitResult:
    """Ergebnis einer Rate-Limit-Prüfung."""

    allowed: bool
    wait_seconds: float = 0.0
    reason: str = ""
    current_rate: float = 0.0
    limit: float = 0.0


class TokenBucket:
    """
    Token Bucket für Rate-Limiting.

    Tokens werden mit konstanter Rate nachgefüllt.
    Jede Execution verbraucht einen Token.
    """

    def __init__(self, rate: float, capacity: float):
        """
        Args:
            rate: Tokens pro Sekunde
            capacity: Maximale Token-Anzahl (für Bursts)
        """
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()

    async def try_consume(self, tokens: float = 1.0) -> Tuple[bool, float]:
        """
        Versucht Tokens zu verbrauchen.

        Returns:
            Tuple of (success, wait_time_if_failed)
        """
        async with self._lock:
            now = datetime.now(timezone.utc)
            elapsed = (now - self.last_update).total_seconds()

            # Tokens nachfüllen
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_update = now

            if self.tokens >= tokens:
                self.tokens -= tokens
                return True, 0.0
            else:
                # Berechne Wartezeit
                needed = tokens - self.tokens
                wait_time = needed / self.rate
                return False, wait_time


class RateLimiter:
    """
    Hierarchisches Rate-Limiting für Logic Engine.

    Ebenen:
        1. Global: Max X Executions/Sekunde über alle Rules
        2. Per-ESP: Max Y Executions/Sekunde pro ESP
        3. Per-Rule: Max Z Executions/Stunde pro Rule (DB-basiert!)

    Thread-Safety:
        - TokenBucket hat internen asyncio.Lock
        - Alle Methoden sind async

    USAGE:
        limiter = RateLimiter(logic_repo=logic_repo)
        result = await limiter.check_rate_limit(
            rule_id="...",
            rule_max_per_hour=60,
            esp_ids=["ESP_1", "ESP_2"]
        )
        if not result["allowed"]:
            logger.warning(f"Rate limited: {result['reason']}")
    """

    def __init__(self, config: Optional[RateLimitConfig] = None, logic_repo=None):
        self.config = config or RateLimitConfig()
        self.logic_repo = logic_repo  # NEU: Für DB-basiertes Hourly-Limit

        # Global Bucket
        self._global_bucket = TokenBucket(
            rate=self.config.max_per_second,
            capacity=self.config.max_per_second * self.config.burst_allowance,
        )

        # Per-ESP Buckets
        self._esp_buckets: Dict[str, TokenBucket] = {}

    def _get_esp_bucket(self, esp_id: str) -> TokenBucket:
        """Holt oder erstellt TokenBucket für ESP."""
        if esp_id not in self._esp_buckets:
            self._esp_buckets[esp_id] = TokenBucket(
                rate=self.config.max_per_esp_second,
                capacity=self.config.max_per_esp_second * self.config.burst_allowance,
            )
        return self._esp_buckets[esp_id]

    async def check_rate_limit(
        self, rule_id: str, rule_max_per_hour: Optional[int], esp_ids: list
    ) -> dict:
        """
        Prüft ob eine Rule ausgeführt werden darf.

        Args:
            rule_id: ID der Rule
            rule_max_per_hour: Max Executions pro Stunde (aus DB-Feld!)
            esp_ids: Liste der betroffenen ESP-IDs (für Actions)

        Returns:
            Dict mit {"allowed": bool, "reason": str, ...}
        """
        # 1. Global Limit
        allowed, wait = await self._global_bucket.try_consume()
        if not allowed:
            logger.warning(f"Global rate limit exceeded, wait {wait:.1f}s")
            return {
                "allowed": False,
                "reason": "Global rate limit exceeded",
                "wait_seconds": wait,
                "current_rate": self.config.max_per_second,
                "limit": self.config.max_per_second,
            }

        # 2. Per-ESP Limit
        for esp_id in esp_ids:
            esp_bucket = self._get_esp_bucket(esp_id)
            allowed, wait = await esp_bucket.try_consume()
            if not allowed:
                logger.warning(f"ESP {esp_id} rate limit exceeded, wait {wait:.1f}s")
                return {
                    "allowed": False,
                    "reason": f"ESP {esp_id} rate limit exceeded",
                    "wait_seconds": wait,
                    "current_rate": self.config.max_per_esp_second,
                    "limit": self.config.max_per_esp_second,
                }

        # 3. Per-Rule Hourly Limit (DB-basiert!)
        if rule_max_per_hour and self.logic_repo:
            try:
                # Import uuid hier um circular imports zu vermeiden
                import uuid

                rule_uuid = uuid.UUID(rule_id) if isinstance(rule_id, str) else rule_id

                hourly_count = await self.logic_repo.get_execution_count_last_hour(rule_uuid)

                if hourly_count >= rule_max_per_hour:
                    logger.warning(
                        f"Rule {rule_id} hourly limit exceeded: "
                        f"{hourly_count}/{rule_max_per_hour}"
                    )
                    return {
                        "allowed": False,
                        "reason": f"Rule exceeded {rule_max_per_hour} executions per hour",
                        "wait_seconds": 3600,  # Muss eine Stunde warten
                        "current_rate": hourly_count,
                        "limit": rule_max_per_hour,
                    }
            except Exception as e:
                logger.error(f"Error checking hourly limit for rule {rule_id}: {e}")
                # Bei Fehler: Erlauben (fail-open für Verfügbarkeit)

        return {"allowed": True, "reason": "OK"}

    def get_stats(self) -> dict:
        """Returns Rate-Limiting Statistiken für Monitoring."""
        return {
            "global_tokens": self._global_bucket.tokens,
            "global_capacity": self._global_bucket.capacity,
            "esp_buckets_count": len(self._esp_buckets),
            "config": {
                "max_per_second": self.config.max_per_second,
                "max_per_esp_second": self.config.max_per_esp_second,
                "burst_allowance": self.config.burst_allowance,
            },
        }
