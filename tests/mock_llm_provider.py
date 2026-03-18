from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn
from src.services.llm_provider import LLMProvider


class MockLLMProvider(LLMProvider):
    def interpret_action(self, participant_input: str) -> dict:
        text = participant_input.lower()
        action_types = []
        targets = []

        if "stäng" in text or "block" in text or "begräns" in text:
            action_types.append("containment")
        if "samla" in text or "kalla in" in text or "sammankalla" in text:
            action_types.append("coordination")
        if "kommun" in text or "uttala" in text or "press" in text:
            action_types.append("communication")
        if "eskaler" in text or "ledning" in text or "chef" in text:
            action_types.append("escalation")
        if "analys" in text or "forens" in text or "utreda" in text:
            action_types.append("analysis")

        if "vpn" in text:
            targets.extend(["vpn", "external_access"])
        if "extern" in text:
            targets.append("external_access")
        if "kommunikationschef" in text or "informationschef" in text:
            targets.append("communications_team")
        if "it-chef" in text or "incidentledningsgrupp" in text:
            targets.extend(["incident_management_team", "executive_team"])
        if "forens" in text:
            targets.append("forensics")

        if not action_types:
            action_types = ["monitoring"]

        return {
            "action_summary": "Automatisk prototyptolkning av deltagarnas senaste atgard.",
            "action_types": list(dict.fromkeys(action_types)),
            "targets": list(dict.fromkeys(targets)),
            "intent": "Begransa paverkan och forbattra lagesuppfattningen.",
            "expected_effects": ["Mojlig minskning av risk beroende pa utfallet."],
            "risks": ["Atgarderna kan ge sidoeffekter i verksamheten."],
            "uncertainties": [
                "Den fulla omfattningen av incidenten ar fortfarande oklar."
            ],
            "priority": "high",
            "confidence": 0.72,
        }

    def generate_narration(self, state: SessionState) -> dict:
        key_points = [
            f"Paverkansniva: {state.metrics.impact_level}",
            f"Medietryck: {state.metrics.media_pressure}",
        ]

        if state.flags.external_access_restricted:
            key_points.append("Extern atkomst ar begransad.")
        if state.flags.forensic_analysis_started:
            key_points.append("Forensisk analys har paborjats.")

        injects = []
        if "inject-media-001" in state.active_injects:
            injects.append(
                {
                    "type": "media",
                    "title": "Fraga fran lokalmedia",
                    "message": "En journalist vill ha en kommentar om storningarna inom 20 minuter.",
                }
            )
        if "inject-ops-001" in state.active_injects and len(injects) < 2:
            injects.append(
                {
                    "type": "operations",
                    "title": "Verksamheten eskalerar",
                    "message": "En verksamhetschef rapporterar att ett kritiskt system inte langre kan anvandas.",
                }
            )

        return {
            "situation_update": (
                "Laget ar fortsatt dynamiskt. Genomforda atgarder paverkar bade attackyta och "
                "verksamhetsformaga, samtidigt som osakerheten kring incidentens fulla omfattning kvarstar."
            ),
            "key_points": key_points[:5],
            "new_consequences": state.consequences[-3:],
            "injects": injects,
            "decisions_to_consider": [
                "Behöver ledningen eskaleras ytterligare?",
                "Behöver extern kommunikation skickas nu?",
            ],
            "facilitator_notes": "Responsen bygger pa aktuella metrics, flags och aktiva injects i session state.",
        }

    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict:
        timeline_summary = [
            {
                "turn_number": turn.turn_number,
                "summary": turn.interpreted_action.action_summary,
                "outcome": turn.narrator_response.situation_update,
            }
            for turn in timeline[:8]
        ]

        return {
            "exercise_summary": (
                f"Ovningen for {scenario.title} avslutades efter {len(timeline)} turns med slutstatus {state.status}."
            ),
            "timeline_summary": timeline_summary or [
                {
                    "turn_number": 1,
                    "summary": "Ingen turn spelades",
                    "outcome": "Ingen tidslinje finns att sammanfatta.",
                }
            ],
            "strengths": [
                "Deltagarna tog incidenten pa allvar och agerade strukturerat.",
                "Ovningen skapade underlag for diskussion om prioriteringar och kommunikation.",
            ],
            "development_areas": [
                "Tydligare ansvarsfordelning kan etableras tidigare.",
                "Beslut om kommunikation och eskalering kan formaliseras snabbare.",
            ],
            "debrief_questions": [
                "Vilket beslut skapade mest effekt i ovningen?",
                "Var uppstod osakerhet eller otydligt ansvar?",
                "Vad skulle ni vilja gora annorlunda i en verklig incident?",
            ],
            "recommended_follow_ups": [
                "Ga igenom roller och kontaktvagar for ledning och drift.",
                "Verifiera hur extern kommunikation ska samordnas i ett tidigt skede.",
            ],
            "facilitator_notes": "Anvand tidslinjen som grund och borja med de viktigaste besluten innan detaljer diskuteras.",
        }
