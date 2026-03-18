import json
from pathlib import Path

from src.models.scenario import Scenario


SCENARIO_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "scenarios" / "scenario.schema.json"
)


def test_checked_in_scenario_schema_matches_model_schema():
    checked_in_schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    assert checked_in_schema == Scenario.model_json_schema()


def test_scenario_schema_includes_level_descriptions():
    schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    impact_level_description = schema["$defs"]["InitialState"]["properties"][
        "impact_level"
    ]["description"]
    severity_description = schema["$defs"]["InjectDefinition"]["properties"][
        "severity"
    ]["description"]

    assert "femgradig skala" in impact_level_description
    assert "femgradig skala" in severity_description


def test_scenario_schema_includes_executable_rule_definition():
    schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    executable_rule_description = schema["properties"]["executable_rules"][
        "description"
    ]

    assert "datadrivna scenariomotorn" in executable_rule_description
