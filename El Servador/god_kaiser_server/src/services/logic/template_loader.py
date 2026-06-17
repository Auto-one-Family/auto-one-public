"""
Logic Rule Template Loader Service

Loads, validates, and instantiates logic rule templates with parameter substitution.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional

from ...core.logging_config import get_logger

logger = get_logger(__name__)

# Templates directory relative to this module
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "logic" / "templates"


class TemplateLoadError(Exception):
    """Raised when template loading/processing fails."""

    pass


class RuleTemplate:
    """Loaded and validated rule template."""

    def __init__(self, template_data: Dict[str, Any]):
        """
        Initialize RuleTemplate.

        Args:
            template_data: Raw template dictionary from JSON
        """
        self.name = template_data.get("template_name", "Unknown")
        self.template_id = template_data.get("template_id", "unknown")
        self.description = template_data.get("template_description", "")
        self.version = template_data.get("version", "1.0")
        self.parameters = template_data.get("parameters", {})
        self.rule_template = template_data.get("rule_template", {})
        self.hysteresis = template_data.get("hysteresis", {})
        self.metadata = template_data.get("metadata", {})
        self._raw = template_data

    def instantiate(self, **kwargs) -> Dict[str, Any]:
        """
        Instantiate template with provided parameters.

        Args:
            **kwargs: Parameter values (sensor_a_id, sensor_b_id, threshold, etc.)

        Returns:
            Instantiated rule dictionary ready for CrossESPLogic creation

        Raises:
            TemplateLoadError: If required parameters missing or validation fails
        """
        # Validate required parameters
        required = self.parameters.get("required", [])
        for param in required:
            if param not in kwargs:
                raise TemplateLoadError(
                    f"Missing required parameter for template '{self.name}': {param}"
                )

        # Build parameter map with defaults and provided values
        params = {}
        configurable = self.parameters.get("configurable", {})
        for key, config in configurable.items():
            if key in kwargs:
                params[key] = kwargs[key]
            else:
                params[key] = config.get("default")

        # Add required parameters
        for key in required:
            params[key] = kwargs[key]

        # Substitute parameters in rule_template
        instantiated = self._substitute_parameters(self.rule_template, params)

        # Add metadata
        instantiated["metadata"] = {
            "template_id": self.template_id,
            "template_version": self.version,
            "instantiation_params": {k: v for k, v in kwargs.items()},
        }

        return instantiated

    def _substitute_parameters(self, obj: Any, params: Dict[str, Any]) -> Any:
        """
        Recursively substitute parameter references in template.

        Handles:
        - String templates with {param_name}
        - use_parameter directives: {"use_parameter": "param_name"}
        """
        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                # Check for use_parameter directive
                if key == "use_parameter" and isinstance(value, str):
                    # This dict is a parameter reference
                    return params.get(value, value)
                result[key] = self._substitute_parameters(value, params)
            return result

        elif isinstance(obj, list):
            return [self._substitute_parameters(item, params) for item in obj]

        elif isinstance(obj, str):
            # Simple string template substitution
            try:
                return obj.format(**params)
            except KeyError:
                # If parameter not found, return as-is
                return obj

        else:
            return obj

    @property
    def required_parameters(self) -> list[str]:
        """Get list of required parameter names."""
        return self.parameters.get("required", [])

    @property
    def optional_parameters(self) -> Dict[str, Any]:
        """Get dict of optional parameters with defaults."""
        return self.parameters.get("configurable", {})


class TemplateLoader:
    """
    Loads and manages logic rule templates.

    Templates are JSON files stored in src/logic/templates/.
    Each template defines a parameterized rule that can be instantiated.
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        """
        Initialize TemplateLoader.

        Args:
            templates_dir: Optional custom templates directory (defaults to TEMPLATES_DIR)
        """
        self.templates_dir = templates_dir or TEMPLATES_DIR
        self._cache: Dict[str, RuleTemplate] = {}

        if not self.templates_dir.exists():
            logger.warning(f"Templates directory not found: {self.templates_dir}")

    def list_templates(self) -> list[str]:
        """
        List all available template identifiers.

        Returns:
            List of template filenames (without .json)
        """
        if not self.templates_dir.exists():
            return []

        templates = []
        for file in self.templates_dir.glob("rule_template_*.json"):
            templates.append(file.stem.replace("rule_template_", ""))
        return templates

    def load(self, template_id: str) -> RuleTemplate:
        """
        Load a template by ID.

        Args:
            template_id: Template identifier (e.g., "sensor_pair_diff")

        Returns:
            RuleTemplate instance

        Raises:
            TemplateLoadError: If template not found or invalid
        """
        # Check cache
        if template_id in self._cache:
            return self._cache[template_id]

        # Load from file
        template_file = self.templates_dir / f"rule_template_{template_id}.json"

        if not template_file.exists():
            raise TemplateLoadError(f"Template not found: {template_id}")

        try:
            with open(template_file, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise TemplateLoadError(f"Failed to load template {template_id}: {e}")

        # Validate template structure
        if "template_name" not in data or "rule_template" not in data:
            raise TemplateLoadError(f"Invalid template structure: {template_id}")

        template = RuleTemplate(data)
        self._cache[template_id] = template
        logger.info(f"Loaded template: {template.name} (ID: {template_id})")
        return template

    def instantiate(self, template_id: str, **kwargs) -> Dict[str, Any]:
        """
        Load and instantiate a template in one call.

        Args:
            template_id: Template identifier
            **kwargs: Parameter values

        Returns:
            Instantiated rule dictionary

        Raises:
            TemplateLoadError: If template loading or instantiation fails
        """
        template = self.load(template_id)
        return template.instantiate(**kwargs)

    def get_template_info(self, template_id: str) -> Dict[str, Any]:
        """
        Get template metadata without full instantiation.

        Args:
            template_id: Template identifier

        Returns:
            Template info (name, description, parameters)
        """
        template = self.load(template_id)
        return {
            "template_id": template.template_id,
            "name": template.name,
            "description": template.description,
            "version": template.version,
            "required_parameters": template.required_parameters,
            "optional_parameters": {
                name: {
                    "type": config.get("type"),
                    "default": config.get("default"),
                    "description": config.get("description"),
                }
                for name, config in template.optional_parameters.items()
            },
        }


# Global instance
_loader: Optional[TemplateLoader] = None


def get_template_loader(templates_dir: Optional[Path] = None) -> TemplateLoader:
    """Get or create global TemplateLoader instance."""
    global _loader
    if _loader is None:
        _loader = TemplateLoader(templates_dir)
    return _loader
