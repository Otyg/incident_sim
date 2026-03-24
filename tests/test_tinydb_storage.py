
from tinydb import Query, TinyDB

from src.models.scenario import Scenario
from src.storage.tinydb_json import TinyDBScenarioRepository, TinyDBSessionRepository


def make_scenario() -> Scenario:
    return Scenario.model_validate(
        {
            "id": "scenario-001",
            "title": "TinyDB scenario",
            "version": "1.0",
            "description": "Scenario used to verify TinyDB round-tripping.",
            "audiences": ["krisledning"],
            "training_goals": ["Öva datadrivna regler"],
            "difficulty": "medium",
            "timebox_minutes": 90,
            "background": {
                "organization_type": "kommun",
                "context": "Testkontext",
                "threat_actor": "okänd angripare",
                "assumptions": [],
            },
            "states": [
                {
                    "id": "state-initial-detection",
                    "phase": "initial-detection",
                    "title": "Initial detection",
                    "description": "Det första state-läget för TinyDB-testet.",
                    "time": "08:15",
                    "impact_level": 2,
                    "narration": {
                        "default": {
                            "situation_update": "TinyDB-testscenariot startar med en enkel fördefinierad lägesbild.",
                            "key_points": [
                                "Scenario ska kunna sparas utan extra fältförlust.",
                                "Initialt narrativ ska följa med i valideringen.",
                            ],
                            "new_consequences": [],
                            "injects": [],
                            "decisions_to_consider": [
                                "Kan scenariot round-trippas korrekt?"
                            ],
                            "facilitator_notes": "Fördefinierat startnarrativ för TinyDB-test.",
                        }
                    },
                }
            ],
            "actors": [],
            "inject_catalog": [],
            "rules": [],
            "executable_rules": [
                {
                    "id": "rule-session-start",
                    "name": "Startregel",
                    "trigger": "session_started",
                    "effects": [
                        {
                            "type": "append_focus_item",
                            "item": "Bekräfta initial lägesbild.",
                        }
                    ],
                }
            ],
            "presentation_guidelines": {
                "krisledning": {"focus": ["beslut"], "tone": "strategisk"}
            },
        }
    )


def test_tinydb_scenario_repository_round_trips_executable_rules_without_none_fields(
    tmp_path,
):
    db_path = tmp_path / "incident_sim.json"
    repository = TinyDBScenarioRepository(db_path)

    repository.save(make_scenario())
    loaded = repository.get("scenario-001")

    assert loaded is not None
    assert loaded.executable_rules[0].effects[0].type == "append_focus_item"
    assert loaded.executable_rules[0].effects[0].item == "Bekräfta initial lägesbild."


def test_tinydb_scenario_repository_reads_legacy_rows_with_none_effect_fields(tmp_path):
    db_path = tmp_path / "incident_sim.json"
    repository = TinyDBScenarioRepository(db_path)
    repository.save(make_scenario())

    db = TinyDB(db_path)
    table = db.table("scenarios")
    query = Query()
    stored = table.get(query.id == "scenario-001")
    stored["executable_rules"][0]["effects"][0].update(
        {
            "phase": None,
            "inject_id": None,
            "metric": None,
            "amount": None,
            "flag": None,
            "value": None,
            "message": None,
            "log_type": None,
        }
    )
    table.update(stored, query.id == "scenario-001")
    db.close()

    loaded = repository.get("scenario-001")

    assert loaded is not None
    assert loaded.executable_rules[0].effects[0].type == "append_focus_item"


def test_tinydb_session_repository_round_trips_stored_markdown_report(tmp_path):
    db_path = tmp_path / "incident_sim.json"
    repository = TinyDBSessionRepository(db_path)

    repository.save_report("session-001", "# Rapport\n\nInnehall.")

    assert repository.get_report("session-001") == "# Rapport\n\nInnehall."
