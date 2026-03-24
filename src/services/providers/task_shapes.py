# LICENSE HEADER MANAGED BY add-license-header
#
# BSD 3-Clause License
#
# Copyright (c) 2026, Martin Vesterlund
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""Shared expected response shapes for structured LLM tasks."""

INTERPRET_ACTION_EXPECTED_SHAPE = {
    "action_summary": "string",
    "action_types": [
        "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
    ],
    "targets": ["string"],
    "intent": "string",
    "expected_effects": ["string"],
    "risks": ["string"],
    "uncertainties": ["string"],
    "priority": "low|medium|high",
    "confidence": "number between 0 and 1",
}

GENERATE_NARRATION_EXPECTED_SHAPE = {
    "situation_update": "string",
    "key_points": ["string"],
    "new_consequences": ["string"],
    "injects": [
        {
            "type": "media|executive|operations|technical|stakeholder",
            "title": "string",
            "message": "string",
        }
    ],
    "decisions_to_consider": ["string"],
    "facilitator_notes": "string",
}

GENERATE_DEBRIEF_EXPECTED_SHAPE = {
    "exercise_summary": "string",
    "timeline_summary": [
        {
            "turn_number": "integer >= 1",
            "summary": "string",
            "outcome": "string",
        }
    ],
    "strengths": ["string"],
    "development_areas": ["string"],
    "debrief_questions": ["string"],
    "recommended_follow_ups": ["string"],
    "facilitator_notes": "string",
}

GENERATE_SCENARIO_DRAFT_EXPECTED_SHAPE = {
    "id": "string",
    "title": "string",
    "version": "string",
    "description": "string",
    "audiences": ["krisledning|it-ledning|kommunikation"],
    "training_goals": ["string"],
    "difficulty": "low|medium|high",
    "timebox_minutes": "integer",
    "background": {
        "organization_type": "string",
        "context": "string",
        "threat_actor": "string",
        "assumptions": ["string"],
    },
    "states": [
        {
            "id": "string",
            "phase": "string",
            "title": "string",
            "description": "string",
        }
    ],
    "actors": [{"id": "string", "name": "string", "role": "string"}],
    "inject_catalog": [
        {
            "id": "string",
            "type": "media|executive|operations|technical|stakeholder",
            "title": "string",
            "description": "string",
            "trigger_conditions": ["string"],
            "audience_relevance": ["krisledning|it-ledning|kommunikation"],
            "severity": "integer 1-5",
        }
    ],
    "text_matchers": [
        {
            "id": "string",
            "field": "action.action_types|action.targets",
            "match_type": "contains_any|contains_all",
            "patterns": ["string"],
            "value": "string",
        }
    ],
    "target_aliases": [{"id": "string", "canonical": "string", "aliases": ["string"]}],
    "interpretation_hints": [
        {
            "id": "string",
            "when": {
                "text_contains_any": ["string"],
                "action_types_contains": [
                    "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
                ],
                "targets_contains": ["string"],
            },
            "add_action_types": [
                "containment|coordination|communication|escalation|analysis|recovery|monitoring|legal|business_continuity"
            ],
            "add_targets": ["string"],
        }
    ],
    "rules": [{"id": "string", "name": "string"}],
    "executable_rules": [
        {
            "id": "string",
            "name": "string",
            "trigger": "session_started|turn_processed",
            "conditions": [
                {
                    "fact": "state.phase|state.no_communication_turns|state.metrics.impact_level|state.metrics.media_pressure|state.metrics.service_disruption|state.metrics.leadership_pressure|state.metrics.public_confusion|state.metrics.attack_surface|state.flags.executive_escalation|state.flags.external_comms_sent|state.flags.forensic_analysis_started|state.flags.external_access_restricted|session.turn_number|action.action_types|action.targets",
                    "operator": "equals|not_equals|gte|lte|contains|not_contains",
                    "value": "string|integer|boolean",
                }
            ],
            "effects": [
                {
                    "type": "set_phase|add_active_inject|resolve_inject|append_focus_item|append_consequence|increment_metric|set_flag|append_exercise_log"
                }
            ],
            "priority": "low|medium|high",
            "once": "boolean",
        }
    ],
    "presentation_guidelines": {"krisledning": {"focus": ["string"], "tone": "string"}},
    "prompt_profiles": {
        "narration": {
            "base": {"text": "string", "items": ["string"]},
            "by_phase": {
                "initial-detection": {"text": "string", "items": ["string"]},
                "containment": {"text": "string", "items": ["string"]},
            },
        }
    },
}
