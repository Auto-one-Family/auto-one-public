"""
Resilience Registry (Singleton)

Central management for circuit breakers and resilience components:
- Register and retrieve circuit breakers
- Health status aggregation
- Metrics collection
- Manual reset capabilities

Usage:
    registry = ResilienceRegistry.get_instance()

    # Register breakers at startup
    registry.register_circuit_breaker("mqtt", CircuitBreaker("mqtt", ...))
    registry.register_circuit_breaker("database", CircuitBreaker("database", ...))

    # Use in code
    breaker = registry.get_circuit_breaker("mqtt")
    if breaker.allow_request():
        ...

    # Health check
    status = registry.get_health_status()
"""

import asyncio
from typing import Dict, List, Optional, Any

from ..logging_config import get_logger
from .circuit_breaker import CircuitBreaker, CircuitState

logger = get_logger(__name__)


class ResilienceRegistry:
    """
    Singleton registry for managing resilience components.

    Provides centralized access to:
    - Circuit breakers for different services
    - Aggregated health status
    - Metrics for monitoring
    """

    _instance: Optional["ResilienceRegistry"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the registry (only once due to singleton)."""
        if self._initialized:
            return

        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

        self._initialized = True
        logger.info("[resilience] ResilienceRegistry initialized")

    @classmethod
    def get_instance(cls) -> "ResilienceRegistry":
        """
        Get singleton instance.

        Returns:
            ResilienceRegistry instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """
        Reset the singleton instance (for testing).

        Warning: This should only be used in tests!
        """
        cls._instance = None
        cls._initialized = False

    def register_circuit_breaker(
        self,
        name: str,
        breaker: CircuitBreaker,
    ) -> None:
        """
        Register a circuit breaker.

        Args:
            name: Unique name for the breaker
            breaker: CircuitBreaker instance

        Raises:
            ValueError: If breaker with same name already exists
        """
        if name in self._breakers:
            logger.warning(f"[resilience] CircuitBreaker[{name}] already registered, replacing")

        self._breakers[name] = breaker
        logger.info(f"[resilience] Registered CircuitBreaker[{name}]")

    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """
        Get a circuit breaker by name.

        Args:
            name: Name of the circuit breaker

        Returns:
            CircuitBreaker instance or None if not found
        """
        return self._breakers.get(name)

    def get_all_breakers(self) -> Dict[str, CircuitBreaker]:
        """
        Get all registered circuit breakers.

        Returns:
            Dictionary of name -> CircuitBreaker
        """
        return self._breakers.copy()

    def get_breaker_names(self) -> List[str]:
        """
        Get names of all registered circuit breakers.

        Returns:
            List of breaker names
        """
        return list(self._breakers.keys())

    def get_health_status(self) -> Dict[str, Any]:
        """
        Get aggregated health status of all circuit breakers.

        Returns:
            Dictionary with:
            - healthy: bool (True if all breakers are not OPEN)
            - breakers: dict of individual breaker states
            - summary: counts of breakers in each state
        """
        breaker_states = {}
        state_counts = {
            CircuitState.CLOSED.value: 0,
            CircuitState.OPEN.value: 0,
            CircuitState.HALF_OPEN.value: 0,
        }

        for name, breaker in self._breakers.items():
            state = breaker.get_state()
            state_counts[state.value] += 1

            breaker_states[name] = {
                "state": state.value,
                "failures": breaker.failure_count,
                "failure_threshold": breaker.config.failure_threshold,
                "last_failure": breaker.last_failure_time,
                "forced_open": breaker._forced_open,
            }

        # System is healthy if no breakers are OPEN
        is_healthy = state_counts[CircuitState.OPEN.value] == 0

        return {
            "healthy": is_healthy,
            "breakers": breaker_states,
            "summary": {
                "total": len(self._breakers),
                **state_counts,
            },
        }

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get detailed metrics from all circuit breakers.

        Returns:
            Dictionary with metrics from each breaker
        """
        metrics = {}
        for name, breaker in self._breakers.items():
            metrics[name] = breaker.get_metrics()
        return metrics

    def reset(self, name: str) -> bool:
        """
        Reset a specific circuit breaker to CLOSED state.

        Args:
            name: Name of the circuit breaker

        Returns:
            True if reset successful, False if breaker not found
        """
        breaker = self._breakers.get(name)
        if breaker is None:
            logger.warning(f"[resilience] Cannot reset: CircuitBreaker[{name}] not found")
            return False

        breaker.reset()
        return True

    async def reset_async(self, name: str) -> bool:
        """Reset a specific circuit breaker (async version)."""
        breaker = self._breakers.get(name)
        if breaker is None:
            logger.warning(f"[resilience] Cannot reset: CircuitBreaker[{name}] not found")
            return False

        await breaker.reset_async()
        return True

    def reset_all(self) -> int:
        """
        Reset all circuit breakers to CLOSED state.

        Returns:
            Number of breakers reset
        """
        count = 0
        for name, breaker in self._breakers.items():
            breaker.reset()
            count += 1

        logger.info(f"[resilience] Reset all {count} circuit breakers")
        return count

    async def reset_all_async(self) -> int:
        """Reset all circuit breakers (async version)."""
        count = 0
        for name, breaker in self._breakers.items():
            await breaker.reset_async()
            count += 1

        logger.info(f"[resilience] Reset all {count} circuit breakers")
        return count

    def force_open(self, name: str) -> bool:
        """
        Force a circuit breaker to OPEN state (for testing).

        Args:
            name: Name of the circuit breaker

        Returns:
            True if successful, False if breaker not found
        """
        breaker = self._breakers.get(name)
        if breaker is None:
            logger.warning(f"[resilience] Cannot force open: CircuitBreaker[{name}] not found")
            return False

        breaker.force_open()
        return True

    async def force_open_async(self, name: str) -> bool:
        """Force a circuit breaker to OPEN state (async version)."""
        breaker = self._breakers.get(name)
        if breaker is None:
            logger.warning(f"[resilience] Cannot force open: CircuitBreaker[{name}] not found")
            return False

        await breaker.force_open_async()
        return True

    def unregister(self, name: str) -> bool:
        """
        Unregister a circuit breaker.

        Args:
            name: Name of the circuit breaker

        Returns:
            True if unregistered, False if not found
        """
        if name in self._breakers:
            del self._breakers[name]
            logger.info(f"[resilience] Unregistered CircuitBreaker[{name}]")
            return True
        return False

    def __repr__(self) -> str:
        breaker_info = ", ".join(
            f"{name}={b.get_state().value}" for name, b in self._breakers.items()
        )
        return f"ResilienceRegistry(breakers=[{breaker_info}])"


# Convenience functions for global access
def get_registry() -> ResilienceRegistry:
    """Get the global ResilienceRegistry instance."""
    return ResilienceRegistry.get_instance()


def get_circuit_breaker(name: str) -> Optional[CircuitBreaker]:
    """Get a circuit breaker by name from the global registry."""
    return get_registry().get_circuit_breaker(name)


def get_health_status() -> Dict[str, Any]:
    """Get aggregated health status from the global registry."""
    return get_registry().get_health_status()
