import json

import yaml
from click.testing import CliRunner

from meta_context_validator.cli import main


def run_validation(
    tmp_path,
    include_profit=True,
    include_context=False,
    include_business_rules=True,
):
    models_dir = tmp_path / "models"
    models_dir.mkdir()

    if include_context:
        meta = {
            "context": {
                "purpose": "Enterprise profit across EQ and FI",
                "business_question": "What is total enterprise profit?",
                "owner": "CDO",
            },
            "expectations": {
                "healthy_range": [0, 1000],
                "warning_threshold": 100,
                "critical_threshold": 0,
                "seasonality": "Synthetic test fixture",
            },
            "investigation": {
                "causal_dimensions": [
                    {
                        "name": "source_team",
                        "why": "Separates EQ and FI contributions",
                        "priority": 1,
                    }
                ],
                "investigation_path":
                    "IF profit changes, investigate source_team.",
            },
            "relationships": {
                "correlates_with": [
                    {
                        "metric": "market_volatility",
                        "relationship": "May influence enterprise profit",
                    }
                ],
                "affected_by": [
                    "Position valuations",
                    "Market movements",
                ],
            },
            "decisions": {
                "when_this_drops": [
                    {
                        "threshold": 0,
                        "action": "Investigate EQ and FI profit",
                    }
                ],
                "business_rules": (
                    ["Include certified EQ and FI positions"]
                    if include_business_rules else []
                ),
            },
        }

        metric_yaml = {
            "version": 2,
            "models": [
                {
                    "name": "fct_cdo_positions",
                    "metrics": [
                        {
                            "name": "enterprise_total_profit",
                            "config": {"meta": meta},
                        }
                    ],
                }
            ],
        }

        (models_dir / "cdo_metrics.yml").write_text(
            yaml.safe_dump(metric_yaml)
        )

    contract = {
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

    columns = {
        name: {"data_type": dtype}
        for name, dtype in contract["required_columns"].items()
    }

    if not include_profit:
        del columns["profit_loss"]

    manifest = {
        "nodes": {
            "model.poc.stg_team_a_positions": {
                "resource_type": "model",
                "name": "stg_team_a_positions",
                "config": {
                    "meta": {
                        "semantic_contract": {
                            "implements": "cdo:position",
                            "version": 1,
                        }
                    }
                },
                "columns": columns,
            }
        }
    }

    contract_path = tmp_path / "contract.yml"
    manifest_path = tmp_path / "manifest.json"

    contract_path.write_text(yaml.safe_dump(contract))
    manifest_path.write_text(json.dumps(manifest))

    return CliRunner().invoke(
        main,
        [
            "validate",
            str(models_dir),
            "--contracts",
            str(contract_path),
            "--manifest",
            str(manifest_path),
        ],
    )


def test_combined_cli_passes(tmp_path):
    result = run_validation(tmp_path)

    assert result.exit_code == 0, result.output
    assert "CDO SEMANTIC CONTRACT VALIDATION" in result.output
    assert "PASS" in result.output


def test_combined_cli_fails_missing_profit(tmp_path):
    result = run_validation(
        tmp_path,
        include_profit=False,
    )

    assert result.exit_code == 1, result.output
    assert "Missing mandatory column profit_loss" in result.output


def test_both_validators_pass(tmp_path):
    result = run_validation(
        tmp_path,
        include_context=True,
    )

    assert result.exit_code == 0, result.output
    assert "enterprise_total_profit" in result.output
    assert "CDO SEMANTIC CONTRACT VALIDATION" in result.output
    assert "PASS" in result.output

def test_context_fails_but_contract_passes(tmp_path):
    result = run_validation(
        tmp_path,
        include_context=True,
        include_business_rules=False,
    )

    assert result.exit_code == 2, result.output
    assert "FALSE CONFIDENCE RISK" in result.output
    assert "CDO SEMANTIC CONTRACT VALIDATION" in result.output
    assert "PASS" in result.output