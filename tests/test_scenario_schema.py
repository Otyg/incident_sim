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

    impact_level_description = schema["$defs"]["ScenarioStateDefinition"]["properties"][
        "impact_level"
    ]["description"]
    severity_description = schema["$defs"]["InjectDefinition"]["properties"][
        "severity"
    ]["description"]

    assert "femgradig skala" in impact_level_description
    assert "femgradig skala" in severity_description


def test_scenario_schema_includes_original_text_field():
    schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    original_text_schema = schema["properties"]["original_text"]

    assert "string" in original_text_schema["type"]
    assert "ursprungstext" in original_text_schema["description"]


def test_scenario_schema_includes_executable_rule_definition():
    schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    executable_rule_description = schema["properties"]["executable_rules"][
        "description"
    ]

    assert "datadrivna scenariomotorn" in executable_rule_description


def test_scenario_schema_includes_interpretation_support_definitions():
    schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    text_matchers_description = schema["properties"]["text_matchers"]["description"]
    target_aliases_description = schema["properties"]["target_aliases"]["description"]
    interpretation_hints_description = schema["properties"]["interpretation_hints"][
        "description"
    ]

    assert "rå deltagartext" in text_matchers_description
    assert "kanoniska target-värden" in target_aliases_description
    assert "LLM-tolkningen" in interpretation_hints_description


def test_scenario_schema_includes_no_communication_turns_fact():
    schema = json.loads(SCENARIO_SCHEMA_PATH.read_text(encoding="utf-8"))

    fact_enum = schema["$defs"]["ExecutableRuleCondition"]["properties"]["fact"]["enum"]

    assert "state.no_communication_turns" in fact_enum
