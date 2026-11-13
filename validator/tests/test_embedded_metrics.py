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