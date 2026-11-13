"""Validate dbt models against CDO-owned, reusable semantic contracts.

Independent dbt projects may use different model names. In the preferred mode,
the contract contains required_columns but no required_models; the validator
discovers implementations via config.meta.semantic_contract.implements.
Legacy required_models contracts are still supported for compatibility.
"""

import re


def normalize_type(value):
    """Normalize formatting for strict declared-type comparison."""
    return re.sub(r"\s+", "", str(value or "").lower())


def _implementation(node: dict) -> dict:
    """Return declared contract metadata from a dbt manifest model node."""
    config = node.get("config") or {}
    meta = config.get("meta") or node.get("meta") or {}
    return meta.get("semantic_contract") or {}


def validate_cdo_contract(manifest: dict, contract: dict) -> list[str]:
    """Return contract violations (an empty list means validation passed).

    Preferred independent-project mode:
        Contract specifies name/version/required_columns, not required_models.
        Validate all models in this manifest declaring implements == name.
        Fail when none declares it, so deleting declarations cannot silently pass.

    Legacy single-project mode:
        If required_models is explicitly present, validate those named models.
    """
    name = contract["name"]
    version = str(contract["version"])
    columns_required = contract["required_columns"]
    if not isinstance(columns_required, dict) or not columns_required:
        raise ValueError("CDO contract requires a non-empty required_columns mapping")

    nodes = manifest.get("nodes") or {}
    models = [
        node for node in nodes.values()
        if node.get("resource_type") == "model"
    ]
    errors = []

    if "required_models" in contract:
        # Backward compatibility for POCs which listed all models centrally.
        required_models = contract["required_models"]
        if not isinstance(required_models, list) or not required_models:
            raise ValueError("required_models must be a non-empty list")
        selected = []
        for model_name in required_models:
            matches = [m for m in models if m.get("name") == model_name]
            if not matches:
                errors.append(f"{model_name}: Model not found")
            elif len(matches) > 1:
                errors.append(f"{model_name}: Multiple models found with this name")
            else:
                selected.append(matches[0])
    else:
        # No globally prescribed physical model names; each team owns its own.
        selected = [m for m in models if _implementation(m).get("implements") == name]
        if not selected:
            return [
                f"No models in this dbt manifest declare "
                f"config.meta.semantic_contract.implements: {name}"
            ]

    for model in selected:
        model_name = model.get("name") or "<unnamed model>"
        implementation = _implementation(model)

        if implementation.get("implements") != name:
            errors.append(f"{model_name}: Does not implement {name}")

        if str(implementation.get("version")) != version:
            errors.append(
                f"{model_name}: Contract version mismatch. "
                f"Expected {version}, got {implementation.get('version')}"
            )

        columns = model.get("columns") or {}
        for column_name, expected_type in columns_required.items():
            column = columns.get(column_name)
            if column is None:
                errors.append(
                    f"{model_name}: Missing mandatory column {column_name}"
                )
                continue

            actual_type = column.get("data_type")
            if normalize_type(actual_type) != normalize_type(expected_type):
                errors.append(
                    f"{model_name}: Incorrect type for {column_name}. "
                    f"Expected {expected_type}, got {actual_type}"
                )

        if contract.get("require_native_contract", False):
            config = model.get("config") or {}
            native_contract = config.get("contract") or {}
            if not native_contract.get("enforced", False):
                errors.append(
                    f"{model_name}: Native dbt contract is not enforced"
                )

    return errors
