from src.models.scenario import Scenario
from src.services.scenario_action_enricher import ScenarioActionEnricher
from src.schemas.interpreted_action import InterpretedAction


def make_scenario() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scenario-enricher-001",
            "title": "Scenario Enricher Test",
            "version": "1.0",
            "description": "Scenario for enrichment tests.",
            "audiences": ["krisledning"],
            "training_goals": ["Öva scenariostyrd tolkkomplettering"],
            "difficulty": "medium",
            "timebox_minutes": 60,
            "background": {
                "organization_type": "kommun",
                "context": "Testkontext",
                "threat_actor": "okänd",
                "assumptions": [],
            },
            "states": [
                {
                    "id": "state-initial-detection",
                    "phase": "initial-detection",
                    "title": "Initial detection",
                    "description": "Initial state for enricher tests.",
                    "time": "08:15",
                    "impact_level": 2,
                    "narration": {
                        "default": {
                            "situation_update": "Startläge för tolkningsstöd.",
                            "key_points": [
                                "Scenario-driven enrichment ska kunna testas.",
                                "Startstate måste vara komplett.",
                            ],
                            "new_consequences": [],
                            "injects": [],
                            "decisions_to_consider": [],
                            "facilitator_notes": "Fördefinierat narrativ för enrichmenttest.",
                        }
                    },
                }
            ],
            "actors": [],
            "inject_catalog": [],
            "text_matchers": [
                {
                    "id": "matcher-containment",
                    "field": "action.action_types",
                    "match_type": "contains_any",
                    "patterns": ["extern åtkomst", "isolera"],
                    "value": "containment",
                },
                {
                    "id": "matcher-vpn",
                    "field": "action.targets",
                    "match_type": "contains_any",
                    "patterns": ["vpn"],
                    "value": "vpn",
                },
                {
                    "id": "matcher-analysis",
                    "field": "action.action_types",
                    "match_type": "contains_any",
                    "patterns": ["forensik", "bevissäkring"],
                    "value": "analysis",
                },
            ],
            "target_aliases": [
                {
                    "id": "alias-external-access",
                    "canonical": "external_access",
                    "aliases": ["extern åtkomst", "externa anslutningar"],
                },
                {
                    "id": "alias-vpn",
                    "canonical": "vpn",
                    "aliases": ["vpn", "fjärråtkomst"],
                },
            ],
            "interpretation_hints": [
                {
                    "id": "hint-external-access",
                    "when": {
                        "action_types_contains": ["containment"],
                        "text_contains_any": ["extern åtkomst", "vpn"],
                    },
                    "add_targets": ["external_access"],
                },
                {
                    "id": "hint-forensics",
                    "when": {
                        "action_types_contains": ["analysis"],
                        "text_contains_any": ["forensik", "bevissäkring"],
                    },
                    "add_targets": ["forensics"],
                },
            ],
            "rules": [],
            "executable_rules": [],
            "presentation_guidelines": {
                "krisledning": {"focus": ["beslut"], "tone": "strategisk"}
            },
        }
    )


def make_action(action_types: list[str], targets: list[str]) -> InterpretedAction:
    return InterpretedAction(
        action_summary="Test action",
        action_types=action_types,
        targets=targets,
        intent="Test intent",
        expected_effects=[],
        risks=[],
        uncertainties=[],
        priority="high",
        confidence=0.8,
    )


def test_enricher_applies_text_matchers_and_interpretation_hints():
    result = ScenarioActionEnricher().enrich(
        make_scenario(),
        "Vi beslutar att stänga extern åtkomst omedelbart.",
        make_action(["monitoring"], []),
    )

    assert result.action.action_types == ["monitoring", "containment"]
    assert result.action.targets == ["external_access"]
    assert result.log_messages == [
        "Target normaliserad: extern åtkomst -> external_access (alias-external-access)",
        "Textmatchning träffade: matcher-containment",
    ]


def test_enricher_avoids_duplicate_values_and_logs_only_when_something_added():
    result = ScenarioActionEnricher().enrich(
        make_scenario(),
        "Vi isolerar och stänger extern åtkomst samt vpn.",
        make_action(["containment"], ["external_access"]),
    )

    assert result.action.action_types == ["containment"]
    assert result.action.targets == ["external_access", "vpn"]
    assert result.log_messages == ["Textmatchning träffade: matcher-vpn"]


def test_enricher_can_chain_vpn_and_forensics_support():
    result = ScenarioActionEnricher().enrich(
        make_scenario(),
        "Vi stänger vpn och fokuserar på forensik och bevissäkring.",
        make_action(["monitoring"], []),
    )

    assert result.action.action_types == ["monitoring", "analysis"]
    assert result.action.targets == ["vpn", "forensics"]
    assert result.log_messages == [
        "Textmatchning träffade: matcher-vpn",
        "Textmatchning träffade: matcher-analysis",
        "Interpretation hint använd: hint-forensics",
    ]


def test_enricher_normalizes_provider_targets_before_rules_and_hints():
    result = ScenarioActionEnricher().enrich(
        make_scenario(),
        "Blockera extern åtkomst.",
        make_action(["containment"], ["Externa anslutningar"]),
    )

    assert result.action.targets == ["Externa anslutningar", "external_access"]
    assert result.log_messages == [
        "Target normaliserad: Externa anslutningar -> external_access (alias-external-access)"
    ]


def test_enricher_fuzzily_normalizes_provider_target_synonyms():
    result = ScenarioActionEnricher().enrich(
        make_scenario(),
        "Blockera extern åtkomst.",
        make_action(["containment"], ["Externa nätverksanslutningar"]),
    )

    assert result.action.targets == [
        "Externa nätverksanslutningar",
        "external_access",
    ]
    assert result.log_messages == [
        "Target normaliserad: Externa nätverksanslutningar -> external_access (alias-external-access)"
    ]
