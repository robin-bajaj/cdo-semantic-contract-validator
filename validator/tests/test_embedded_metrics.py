from meta_context_validator.cli import _extract_metrics


def test_embedded_metric_extraction():
    yaml_content = {
        "version": 2,
        "models": [
            {
                "name": "fct_cdo_positions",
                "metrics": [
                    {
                        "name": "enterprise_total_profit",
                        "config": {
                            "meta": {
                                "context": {
                                    "purpose": "Enterprise profit",
                                    "owner": "CDO"
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }

    metrics = _extract_metrics(yaml_content)

    assert len(metrics) == 1

    name, meta = metrics[0]

    assert name == "enterprise_total_profit"
    assert meta["context"]["owner"] == "CDO"

def test_top_level_metric_config_meta_extraction():
    yaml_content = {
        "version": 2,
        "metrics": [
            {
                "name": "enterprise_total_profit_loss",
                "config": {
                    "meta": {
                        "context": {
                            "owner": "CDO",
                            "purpose": "Governed enterprise profit",
                        }
                    }
                },
            }
        ],
    }
    metrics = _extract_metrics(yaml_content)
    assert len(metrics) == 1
    assert metrics[0][0] == "enterprise_total_profit_loss"
    assert metrics[0][1]["context"]["owner"] == "CDO"
