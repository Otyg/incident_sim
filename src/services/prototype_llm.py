from src.models.session import SessionState
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorInject, NarratorResponse


class PrototypeInterpreter:
    def interpret(self, participant_input: str) -> InterpretedAction:
        text = participant_input.lower()
        action_types = []
        targets = []

        if 'stäng' in text or 'block' in text or 'begräns' in text:
            action_types.append('containment')
        if 'samla' in text or 'kalla in' in text or 'sammankalla' in text:
            action_types.append('coordination')
        if 'kommun' in text or 'uttala' in text or 'press' in text:
            action_types.append('communication')
        if 'eskaler' in text or 'ledning' in text or 'chef' in text:
            action_types.append('escalation')
        if 'analys' in text or 'forens' in text or 'utreda' in text:
            action_types.append('analysis')

        if 'vpn' in text:
            targets.append('vpn')
            targets.append('external_access')
        if 'extern' in text:
            targets.append('external_access')
        if 'kommunikationschef' in text or 'informationschef' in text:
            targets.append('communications_team')
        if 'it-chef' in text or 'incidentledningsgrupp' in text:
            targets.append('incident_management_team')
            targets.append('executive_team')
        if 'forens' in text:
            targets.append('forensics')

        if not action_types:
            action_types = ['monitoring']

        # de-dup preserving order
        action_types = list(dict.fromkeys(action_types))
        targets = list(dict.fromkeys(targets))

        return InterpretedAction(
            action_summary='Automatisk prototyptolkning av deltagarnas senaste åtgärd.',
            action_types=action_types,
            targets=targets,
            intent='Begränsa påverkan och förbättra lägesuppfattningen.',
            expected_effects=['Möjlig minskning av risk beroende på utfallet.'],
            risks=['Åtgärderna kan ge sidoeffekter i verksamheten.'],
            uncertainties=['Den fulla omfattningen av incidenten är fortfarande oklar.'],
            priority='high',
            confidence=0.72,
        )


class PrototypeNarrator:
    def narrate(self, state: SessionState) -> NarratorResponse:
        key_points = [
            f'Påverkansnivå: {state.metrics.impact_level}',
            f'Medietryck: {state.metrics.media_pressure}',
        ]

        if state.flags.external_access_restricted:
            key_points.append('Extern åtkomst är begränsad.')
        if state.flags.forensic_analysis_started:
            key_points.append('Forensisk analys har påbörjats.')

        injects = []
        if 'inject-media-001' in state.active_injects:
            injects.append(
                NarratorInject(
                    type='media',
                    title='Fråga från lokalmedia',
                    message='En journalist vill ha en kommentar om störningarna inom 20 minuter.',
                )
            )
        if 'inject-ops-001' in state.active_injects and len(injects) < 2:
            injects.append(
                NarratorInject(
                    type='operations',
                    title='Verksamheten eskalerar',
                    message='En verksamhetschef rapporterar att ett kritiskt system inte längre kan användas.',
                )
            )

        return NarratorResponse(
            situation_update=(
                'Läget är fortsatt dynamiskt. Genomförda åtgärder påverkar både attackyta och '
                'verksamhetsförmåga, samtidigt som osäkerheten kring incidentens fulla omfattning kvarstår.'
            ),
            key_points=key_points[:5],
            new_consequences=state.consequences[-3:],
            injects=injects,
            decisions_to_consider=[
                'Behöver ledningen eskaleras ytterligare?',
                'Behöver extern kommunikation skickas nu?',
            ],
            facilitator_notes='Responsen bygger på aktuella metrics, flags och aktiva injects i session state.',
        )
