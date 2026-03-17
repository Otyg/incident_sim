from copy import deepcopy

from src.models.session import ExerciseLogItem, ParticipantActionLog, SessionState
from src.schemas.interpreted_action import InterpretedAction


class RulesEngine:
    @staticmethod
    def _add_focus_item(state: SessionState, item: str) -> None:
        if item not in state.focus_items:
            state.focus_items.append(item)

    def apply(self, state: SessionState, interpreted_action: InterpretedAction, raw_input: str) -> SessionState:
        updated = deepcopy(state)
        updated.turn_number += 1

        updated.participant_actions.append(
            ParticipantActionLog(turn=updated.turn_number, summary=interpreted_action.action_summary)
        )
        updated.exercise_log.append(
            ExerciseLogItem(turn=updated.turn_number, type='participant_action', text=raw_input)
        )

        action_types = set(interpreted_action.action_types)
        targets = set(interpreted_action.targets)

        if 'containment' in action_types and ('external_access' in targets or 'vpn' in targets):
            updated.metrics.attack_surface = max(0, updated.metrics.attack_surface - 1)
            updated.metrics.service_disruption += 1
            updated.flags.external_access_restricted = True
            updated.consequences.append(
                'Begränsad extern åtkomst minskar attackytan men påverkar externa tjänster.'
            )
            self._add_focus_item(updated, 'Hantera påverkan på externa tjänster.')
            updated.exercise_log.append(
                ExerciseLogItem(
                    turn=updated.turn_number,
                    type='system_consequence',
                    text='Extern attackyta minskar, men tjänstepåverkan ökar externt.',
                )
            )

        if 'analysis' in action_types or 'forensics' in targets:
            updated.flags.forensic_analysis_started = True

        if 'escalation' in action_types or 'executive_team' in targets:
            updated.flags.executive_escalation = True
            self._add_focus_item(updated, 'Förbered ledningsbeslut och eskalering.')

        if 'communication' in action_types:
            updated.flags.external_comms_sent = True
            updated.no_communication_turns = 0
            self._add_focus_item(updated, 'Samordna fortsatt extern kommunikation.')
        else:
            updated.no_communication_turns += 1
            if updated.no_communication_turns >= 2:
                updated.metrics.media_pressure += 1
                updated.metrics.public_confusion += 1
                updated.consequences.append('Fördröjd kommunikation ökar medietrycket.')
                self._add_focus_item(updated, 'Ta fram ett första externt budskap.')

        if updated.metrics.service_disruption >= 2 and 'inject-ops-001' not in updated.active_injects:
            updated.active_injects.append('inject-ops-001')

        if updated.metrics.media_pressure >= 2 and 'inject-media-001' not in updated.active_injects:
            updated.active_injects.append('inject-media-001')

        if updated.metrics.impact_level >= 3 and not updated.flags.executive_escalation:
            updated.metrics.leadership_pressure += 1

        return updated
