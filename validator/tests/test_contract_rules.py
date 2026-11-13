from copy import deepcopy

from meta_context_validator.contract_rules import validate_cdo_contract


CONTRACT = {
    "name": "cdo:position",
    "version": 1,
    "required_models": ["stg_team_a_positions"],
    "required_columns": {
        "position_id": "text",
        "report_date": "date",
        "profit_loss": "numeric",
        "instrument_code": "integer",
    },
}


def sample_manifest():
    return {
        "nodes": {
            "model.test.stg_team_a_positions": {
                "name": "stg_team_a_positions",
                "resource_type": "model",
                "config": {
                    "meta": {
                        "semantic_contract": {
                            "implements": "cdo:position",
                            "version": 1,
                        }
                    }
                },
                "columns": {
                    "position_id": {"data_type": "text"},
                    "report_date": {"data_type": "date"},
                    "profit_loss": {"data_type": "numeric"},
                    "instrument_code": {"data_type": "integer"},
                    "trader_name": {"data_type": "text"},
                },
            }
        }
    }


def test_valid_contract():
    errors = validate_cdo_contract(
        sample_manifest(), CONTRACT
    )
    assert errors == []


def test_missing_mandatory_column():
    manifest = sample_manifest()

    del manifest["nodes"][
        "model.test.stg_team_a_positions"
    ]["columns"]["profit_loss"]

    errors = validate_cdo_contract(manifest, CONTRACT)

    assert any("Missing mandatory column profit_loss" in e
               for e in errors)


def test_contract_version_mismatch():
    manifest = sample_manifest()

    manifest["nodes"][
        "model.test.stg_team_a_positions"
    ]["config"]["meta"]["semantic_contract"]["version"] = 2

    errors = validate_cdo_contract(manifest, CONTRACT)

    assert any("version mismatch" in e for e in errors)


def test_missing_model():
    manifest = {"nodes": {}}

    errors = validate_cdo_contract(manifest, CONTRACT)

    assert any("Model not found" in e for e in errors)