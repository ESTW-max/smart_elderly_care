"""
Schema validator - Validates tool arguments against ToolSchema definitions.

Single Responsibility: pure validation with no execution side-effects.
Separated from ITool so the validation strategy can be swapped independently.
"""

from __future__ import annotations

from typing import Any

from app.kernel.interfaces.tool import IToolValidator, ToolSchema


class SchemaValidator(IToolValidator):
    """
    Lightweight JSON-Schema-compatible validator.

    Checks required fields and type conformance without pulling in a
    heavy dependency. For strict JSON Schema compliance, swap this
    implementation for one backed by jsonschema or pydantic.
    """

    # Mapping from JSON Schema type strings to Python types
    _TYPE_MAP: dict[str, type | tuple[type, ...]] = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "array": list,
        "object": dict,
        "null": type(None),
    }

    def validate(self, schema: ToolSchema, arguments: dict[str, Any]) -> list[str]:
        """
        Return validation error messages, or an empty list when valid.

        Checks:
        1. All required parameters are present.
        2. Each present parameter matches the declared type.
        3. If an enum is declared, the value must be in it.
        """
        errors: list[str] = []
        param_map = {p.name: p for p in schema.parameters}

        # 1. Required parameter presence
        for param in schema.parameters:
            if param.required and param.name not in arguments:
                errors.append(
                    f"Missing required parameter '{param.name}' "
                    f"(expected type: {param.type})."
                )

        # 2. Type and enum checks for supplied values
        for name, value in arguments.items():
            if name not in param_map:
                # Unknown parameter — warn but don't hard-fail
                errors.append(
                    f"Unknown parameter '{name}'. "
                    f"Accepted parameters: {list(param_map.keys())}."
                )
                continue

            param = param_map[name]
            expected = self._TYPE_MAP.get(param.type)
            if expected is not None and not isinstance(value, expected):
                errors.append(
                    f"Parameter '{name}' must be of type '{param.type}', "
                    f"got {type(value).__name__}."
                )

            if param.enum and value not in param.enum:
                errors.append(
                    f"Parameter '{name}' must be one of {list(param.enum)}, "
                    f"got {value!r}."
                )

        return errors
