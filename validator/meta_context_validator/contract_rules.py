"""Validate dbt models against centrally defined CDO contracts."""

import re


def normalize_type(value):
    """Normalize formatting for strict type comparison."""
    return re.sub(r"\s+", "", str(value or "").lower())


def validate_cdo_contract(manifest: dict, contract: dict) -> list[str]:
    """
    Validate required dbt models against a CDO semantic contract.

    Returns a list of errors.
    An empty list means validation passed.
    """

    errors = []

    contract_name = contract["name"]
    contract_version = str(contract["version"])
    required_models = contract["required_models"]
    required_columns = contract["required_columns"]

    if not required_models:
        raise ValueError("CDO contract has no required models")

    nodes = manifest.get("nodes", {})

    for model_name in required_models:

        # Find the model in dbt's parsed manifest
        matches = [
            node for node in nodes.values()
            if node.get("resource_type") == "model"
            and node.get("name") == model_name
        ]

        if not matches:
            errors.append(f"{model_name}: Model not found")
            continue

        if len(matches) > 1:
            errors.append(
                f"{model_name}: Multiple models found with this name"
            )
            continue

        model = matches[0]
        config = model.get("config") or {}

        # Read custom semantic-contract metadata
        meta = config.get("meta") or model.get("meta") or {}
        implementation = meta.get("semantic_contract") or {}

        if implementation.get("implements") != contract_name:
            errors.append(
                f"{model_name}: Does not implement {contract_name}"
            )

        if str(implementation.get("version")) != contract_version:
            errors.append(
                f"{model_name}: Contract version mismatch"
            )

        # Check mandatory columns
        columns = model.get("columns") or {}

        for column_name, expected_type in required_columns.items():

            column = columns.get(column_name)

            if column is None:
                errors.append(
                    f"{model_name}: Missing mandatory column "
                    f"{column_name}"
                )
                continue

            actual_type = column.get("data_type")

            if normalize_type(actual_type) != normalize_type(expected_type):
                errors.append(
                    f"{model_name}: Incorrect type for {column_name}. "
                    f"Expected {expected_type}, got {actual_type}"
                )

        # Optional: require native dbt model contract enforcement
        if contract.get("require_native_contract", False):
            native_contract = config.get("contract") or {}

            if not native_contract.get("enforced", False):
                errors.append(
                    f"{model_name}: Native dbt contract is not enforced"
                )

    return errors