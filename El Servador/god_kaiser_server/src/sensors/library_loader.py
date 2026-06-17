"""
Dynamic Library Loader - Loads sensor processing libraries at runtime

Dynamically imports sensor processor modules from sensor_libraries/active/
and provides a registry for accessing processor instances.

Usage:
    loader = LibraryLoader.get_instance()
    ph_processor = loader.get_processor("ph")
    result = ph_processor.process(raw_value=2150, ...)
"""

import importlib
import inspect
from pathlib import Path
from typing import Dict, Optional

from ..core.logging_config import get_logger
from .base_processor import BaseSensorProcessor
from .sensor_type_registry import normalize_sensor_type

logger = get_logger(__name__)


class LibraryLoader:
    """
    Singleton library loader for sensor processors.

    Automatically discovers and loads sensor processor classes from
    sensor_libraries/active/ directory.

    Features:
    - Dynamic module import using importlib
    - Processor instance caching (one instance per sensor type)
    - Automatic discovery of new processors
    - Type validation (all processors must extend BaseSensorProcessor)
    """

    _instance: Optional["LibraryLoader"] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize library loader (called only once due to singleton)."""
        if self._initialized:
            return

        self.processors: Dict[str, BaseSensorProcessor] = {}
        self.library_path = Path(__file__).parent / "sensor_libraries" / "active"

        # Discover and load all processors
        self._discover_libraries()

        self._initialized = True
        # DEBUG: Log all available processors for debugging
        processor_list = ", ".join(sorted(self.processors.keys()))
        logger.info(
            f"LibraryLoader initialized with {len(self.processors)} processors: [{processor_list}]"
        )

    @classmethod
    def get_instance(cls) -> "LibraryLoader":
        """
        Get singleton library loader instance.

        Returns:
            LibraryLoader instance
        """
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_processor(self, sensor_type: str) -> Optional[BaseSensorProcessor]:
        """
        Get processor instance for sensor type.

        Automatically normalizes sensor type from ESP32 format to server processor format
        using the sensor type registry.

        Args:
            sensor_type: Sensor type identifier (e.g., "ph", "temperature_sht31", "sht31_temp")

        Returns:
            BaseSensorProcessor instance or None if not found

        Example:
            processor = loader.get_processor("temperature_sht31")  # Auto-normalized to "sht31_temp"
            if processor:
                result = processor.process(raw_value=2150, ...)
        """
        # Normalize sensor type (ESP32 → Server Processor)
        normalized_type = normalize_sensor_type(sensor_type)

        processor = self.processors.get(normalized_type)

        if processor is None:
            logger.warning(
                f"No processor found for sensor type: {sensor_type} "
                f"(normalized: {normalized_type}). "
                f"Available processors: {list(self.processors.keys())}"
            )

        return processor

    def reload_libraries(self):
        """
        Reload all sensor libraries.

        Useful for development/hot-reload scenarios.
        Clears processor cache and re-discovers all libraries.
        """
        logger.info("Reloading sensor libraries...")
        self.processors.clear()
        self._discover_libraries()
        logger.info(f"Libraries reloaded. {len(self.processors)} processors available.")

    def get_available_sensors(self) -> list[str]:
        """
        Get list of available sensor types.

        Returns:
            List of sensor type identifiers

        Example:
            ["ph", "temperature", "humidity", "ec_sensor", ...]
        """
        return list(self.processors.keys())

    def get_all_processor_classes(self) -> Dict[str, type]:
        """
        Get all loaded processor classes (for auto-registration).

        Returns a mapping from sensor_type to the processor CLASS (not instance).
        This is used by SensorTypeRegistrationService to read class attributes
        like RECOMMENDED_MODE, RECOMMENDED_TIMEOUT_SECONDS, etc.

        Returns:
            Dict mapping sensor_type (str) to processor class (type)

        Example:
            {
                "ph": PHSensorProcessor,
                "temperature": TemperatureProcessor,
                "humidity": HumidityProcessor,
                ...
            }
        """
        return {
            sensor_type: instance.__class__ for sensor_type, instance in self.processors.items()
        }

    def _discover_libraries(self):
        """
        Discover and load all sensor processor libraries.

        Scans sensor_libraries/active/ directory for Python modules,
        imports them, and extracts BaseSensorProcessor subclasses.
        """
        if not self.library_path.exists():
            logger.error(
                f"Sensor libraries path not found: {self.library_path}. " "No processors loaded."
            )
            return

        logger.debug(f"Discovering libraries in: {self.library_path}")

        # Scan for Python files
        for file_path in self.library_path.glob("*.py"):
            # Skip __init__.py
            if file_path.name.startswith("__"):
                continue

            module_name = file_path.stem  # e.g., "ph_sensor"

            try:
                # Import module dynamically - returns list of ALL processors
                processor_instances = self._load_library(module_name)

                for processor_instance in processor_instances:
                    sensor_type = processor_instance.get_sensor_type()
                    self.processors[sensor_type] = processor_instance
                    logger.debug(
                        f"Loaded processor: {sensor_type} "
                        f"({processor_instance.__class__.__name__})"
                    )

            except Exception as e:
                logger.error(
                    f"Failed to load library '{module_name}': {e}",
                    exc_info=True,
                )

    def _load_library(self, module_name: str) -> list[BaseSensorProcessor]:
        """
        Load all sensor processor classes from a library module.

        Args:
            module_name: Module name (e.g., "ph_sensor", "temperature")

        Returns:
            List of BaseSensorProcessor instances (empty list if loading failed)

        Example:
            processors = self._load_library("temperature")
            # Returns: [DS18B20Processor(), SHT31TemperatureProcessor()]
        """
        try:
            # Try multiple import paths for flexibility
            # This supports both installed package and direct execution
            import_paths = [
                f"src.sensors.sensor_libraries.active.{module_name}",
                f"sensors.sensor_libraries.active.{module_name}",
                f"god_kaiser_server.src.sensors.sensor_libraries.active.{module_name}",
            ]

            module = None
            last_error = None

            for full_module_path in import_paths:
                try:
                    module = importlib.import_module(full_module_path)
                    break  # Success - exit loop
                except ImportError as e:
                    last_error = e
                    continue

            if module is None:
                raise ImportError(
                    f"Could not import {module_name} from any path. Last error: {last_error}"
                )

            # Find all classes in module that extend BaseSensorProcessor
            processor_classes = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Check if class is a subclass of BaseSensorProcessor
                # but NOT BaseSensorProcessor itself
                # Also check that the class is defined in THIS module (not imported)
                if (
                    issubclass(obj, BaseSensorProcessor)
                    and obj is not BaseSensorProcessor
                    and obj.__module__ == module.__name__
                ):
                    processor_classes.append(obj)

            if not processor_classes:
                logger.warning(
                    f"Module '{module_name}' has no BaseSensorProcessor subclass. " "Skipping."
                )
                return []

            # Instantiate ALL processor classes from this module
            processor_instances = []
            for processor_class in processor_classes:
                try:
                    processor_instance = processor_class()
                    processor_instances.append(processor_instance)
                    logger.debug(
                        f"Successfully loaded: {processor_class.__name__} from {module_name}"
                    )
                except Exception as e:
                    logger.error(f"Failed to instantiate {processor_class.__name__}: {e}")

            if len(processor_classes) > 1:
                logger.info(
                    f"Module '{module_name}' loaded {len(processor_instances)} processors: "
                    f"{[inst.__class__.__name__ for inst in processor_instances]}"
                )

            return processor_instances

        except ImportError as e:
            logger.error(
                f"Failed to import module '{module_name}': {e}",
                exc_info=True,
            )
            return []

        except Exception as e:
            logger.error(
                f"Failed to load processors from '{module_name}': {e}",
                exc_info=True,
            )
            return []


# Global loader instance
_loader_instance: Optional[LibraryLoader] = None


def get_library_loader() -> LibraryLoader:
    """
    Get singleton library loader instance (convenience function).

    Returns:
        LibraryLoader instance
    """
    global _loader_instance
    if _loader_instance is None:
        _loader_instance = LibraryLoader.get_instance()
    return _loader_instance
