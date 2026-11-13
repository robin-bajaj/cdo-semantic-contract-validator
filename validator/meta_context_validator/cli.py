"""CLI for dbt-meta-context-validator."""

import json
import sys
from pathlib import Path

import click
import yaml

from .rules import validate_metric
from .contract_rules import validate_cdo_contract


def _find_yaml_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    return sorted(path.rglob("*.yml")) + sorted(path.rglob("*.yaml"))


def _extract_metrics(yaml_content: dict) -> list[tuple[str, dict]]:
    """Extract (metric_name, meta_dict) pairs from a parsed YAML file."""
    results = []
    models = yaml_content.get("models", [])
    for model in models:
        semantic = model.get("semantic_model", {})
        model_level_meta = semantic.get("meta", {})
        for metric in semantic.get("metrics", []):
            name = metric.get("name", "unknown")
            metric_meta = metric.get("meta", {})
            # Merge model-level meta under metric-level (metric wins on conflict)
            merged = {}
            for layer in ("context", "expectations", "investigation", "relationships", "decisions"):
                model_layer = model_level_meta.get(layer, {})
                metric_layer = metric_meta.get(layer, {})
                merged[layer] = {**model_layer, **metric_layer}
            if model_level_meta.get("last_validated") and not metric_meta.get("last_validated"):
                merged["last_validated"] = model_level_meta["last_validated"]
            elif metric_meta.get("last_validated"):
                merged["last_validated"] = metric_meta["last_validated"]
            results.append((name, merged))

    # Support embedded dbt metrics: models[].metrics[]
    for model in models:
        for metric in model.get("metrics", []):
            name = metric.get("name", "unknown")

            meta = (
                metric.get("config", {}).get("meta")
                or metric.get("meta", {})
            )

            results.append((name, meta))

    # Also handle top-level metrics blocks
    for metric in yaml_content.get("metrics", []):
        name = metric.get("name", "unknown")
        # Current dbt stores custom metric metadata under config.meta.
        meta = metric.get("config", {}).get("meta") or metric.get("meta", {})
        results.append((name, meta))
    return results


@click.group()
def main():
    """dbt-meta-context validator."""


@main.command()
@click.argument("path", type=click.Path(exists=True))
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
)
@click.option(
    "--errors-only",
    is_flag=True,
    help="Only show errors and false-confidence risks",
)
@click.option(
    "--contracts",
    "contracts_path",
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
    default=None,
    help="Path to the CDO semantic contract YAML.",
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(
        exists=True,
        dir_okay=False,
        path_type=Path,
    ),
    default=None,
    help="Path to dbt manifest.json.",
)
def validate(
    path,
    output_format,
    errors_only,
    contracts_path,
    manifest_path,
):
    """Validate Meta:Context and optional CDO contracts."""
    target = Path(path)
    yaml_files = _find_yaml_files(target)

    all_results = []
    exit_code = 0

    contract_errors = []
    contract_name = None

    if (contracts_path is None) != (manifest_path is None):
        raise click.UsageError(
            "--contracts and --manifest must be provided together."
        )

    if contracts_path is not None:
        try:
            contract = yaml.safe_load(
                contracts_path.read_text()
            )

            manifest = json.loads(
                manifest_path.read_text()
            )

            if not isinstance(contract, dict):
                raise ValueError(
                    "CDO contract must be a YAML mapping"
                )

            if not isinstance(manifest, dict):
                raise ValueError(
                    "Manifest must be a JSON object"
                )

            contract_name = contract.get("name", "unknown")

            contract_errors = validate_cdo_contract(
                manifest,
                contract,
            )

        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            yaml.YAMLError,
        ) as exc:
            raise click.ClickException(
                f"CDO validation failed: {exc}"
            ) from exc

        if contract_errors:
            exit_code = max(exit_code, 1)

    for yaml_file in yaml_files:
        try:
            content = yaml.safe_load(yaml_file.read_text())
        except yaml.YAMLError as e:
            click.echo(f"Error parsing {yaml_file}: {e}", err=True)
            continue

        if not content:
            continue

        metrics = _extract_metrics(content)
        if not metrics:
            continue

        file_results = []
        for metric_name, meta in metrics:
            result = validate_metric(metric_name, meta)
            file_results.append(result)
            if result.errors:
                exit_code = max(exit_code, 1)
            if result.has_false_confidence_risk:
                exit_code = max(exit_code, 2)

        all_results.append({"file": str(yaml_file), "metrics": file_results})

    if output_format == "json":
        output = []
        for file_data in all_results:
            file_json = {"file": file_data["file"], "metrics": []}
            for r in file_data["metrics"]:
                file_json["metrics"].append({
                    "name": r.metric_name,
                    "tier": r.tier,
                    "findings": [
                        {"level": f.level, "rule": f.rule, "message": f.message}
                        for f in r.findings
                    ],
                })
            output.append(file_json)
        if contract_name is not None:
            output.append({
                "cdo_contract": {
                    "name": contract_name,
                    "status": "FAIL" if contract_errors else "PASS",
                    "errors": contract_errors,
                }
            })
        click.echo(json.dumps(output, indent=2))
    else:
        for file_data in all_results:
            click.echo(f"\n{file_data['file']}")
            for r in file_data["metrics"]:
                click.echo(f"  metric: {r.metric_name}")
                tier_symbol = {"none": "✗", "bronze": "✓", "silver": "✓", "gold": "✓"}
                tier_label = r.tier.capitalize()
                click.echo(f"    {tier_symbol.get(r.tier, '?')} {tier_label} tier")

                for finding in r.findings:
                    if errors_only and finding.level == "info":
                        continue
                    symbol = {"error": "✗", "warning": "⚠", "info": "·"}.get(finding.level, " ")
                    click.echo(f"    {symbol} {finding.message}")

        if contract_name is not None:
            click.echo("\nCDO SEMANTIC CONTRACT VALIDATION")
            click.echo(f"  Contract: {contract_name}")

            if contract_errors:
                click.echo("  FAIL")
                for error in contract_errors:
                    click.echo(f"    ✗ {error}")
            else:
                click.echo("  PASS")

        # Summary
        total = sum(len(fd["metrics"]) for fd in all_results)
        by_tier = {"none": 0, "bronze": 0, "silver": 0, "gold": 0}
        false_confidence = 0
        for fd in all_results:
            for r in fd["metrics"]:
                by_tier[r.tier] = by_tier.get(r.tier, 0) + 1
                if r.has_false_confidence_risk:
                    false_confidence += 1
        click.echo(
            f"\nSummary: {total} metrics | "
            f"{by_tier['bronze']} Bronze | {by_tier['silver']} Silver | {by_tier['gold']} Gold | "
            f"{by_tier['none']} below Bronze | "
            f"{false_confidence} false-confidence risk"
        )

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
