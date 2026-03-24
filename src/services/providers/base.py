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

"""Shared structured-output provider base implementation.

This module centralizes the task-level flow for structured LLM calls while
provider-specific transport details live in sibling modules such as
``ollama_provider`` and ``openai_provider``.
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from src.models.scenario import Scenario
from src.models.session import SessionState
from src.models.turn import Turn
from src.services.llm_provider import LLMProvider, load_prompt_bundle
from src.services.providers.task_shapes import (
    GENERATE_DEBRIEF_EXPECTED_SHAPE,
    GENERATE_NARRATION_EXPECTED_SHAPE,
    GENERATE_SCENARIO_DRAFT_EXPECTED_SHAPE,
    INTERPRET_ACTION_EXPECTED_SHAPE,
)


class StructuredLLMProvider(LLMProvider, ABC):
    """Base provider for shared prompt and payload-building logic.

    Subclasses only need to provide provider-specific transport in
    ``_chat_json`` together with model selection and any auth/client setup.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Load prompt configuration shared by structured-output providers."""

        self.config = config or {}
        prompts = load_prompt_bundle(self.config)
        self.interpret_prompt = prompts["interpret_prompt"]
        self.narration_prompt = prompts["narration_prompt"]
        self.debrief_prompt = prompts["debrief_prompt"]
        self.scenario_authoring_prompt = prompts["scenario_authoring_prompt"]

    @abstractmethod
    def _chat_json(
        self, model: str, system_prompt: str, user_prompt: str, provider_stage: str
    ) -> dict[str, Any]:
        """Send a provider-specific request and return a parsed JSON object."""

        raise NotImplementedError

    @staticmethod
    def _build_json_system_prompt(
        prompt: str,
        expected_shape: dict[str, Any],
        addendum: str | None = None,
    ) -> str:
        """Combine a task prompt with strict JSON output instructions."""

        addendum_block = ""
        if addendum:
            addendum_block = f"\n\nScenario-specific instructions:\n{addendum}"

        return (
            f"{prompt}\n"
            f"{addendum_block}\n"
            "Return only a single JSON object and no surrounding prose.\n"
            f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
        )

    @staticmethod
    def _resolve_prompt_addendum(scenario: Scenario | None, audience: str) -> str:
        """Resolve ordered legacy scenario instructions into a prompt addendum string."""

        if scenario is None:
            return ""

        lines = scenario.resolve_prompt_instruction_lines(audience)
        if not lines:
            return ""

        return "\n".join(f"- {line}" for line in lines)

    @staticmethod
    def _resolve_narration_prompt_addendum(
        scenario: Scenario | None, audience: str, phase: str
    ) -> str:
        """Resolve narration-specific scenario instructions into an addendum string."""

        if scenario is None:
            return ""

        lines = scenario.resolve_narration_prompt_lines(audience, phase)
        if not lines:
            return ""

        return "\n".join(f"- {line}" for line in lines)

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant text into structured action data."""

        return self._chat_json(
            model=self.interpret_model,
            system_prompt=self._build_json_system_prompt(
                self.interpret_prompt, INTERPRET_ACTION_EXPECTED_SHAPE
            ),
            user_prompt=f"Deltagaratgard:\n{participant_input}",
            provider_stage="interpret_action",
        )

    def generate_narration(
        self, state: SessionState, scenario: Scenario | None = None
    ) -> dict[str, Any]:
        """Generate a narrated situation update from the session state."""

        return self._chat_json(
            model=self.narration_model,
            system_prompt=self._build_json_system_prompt(
                self.narration_prompt,
                GENERATE_NARRATION_EXPECTED_SHAPE,
                addendum=self._resolve_narration_prompt_addendum(
                    scenario, state.audience, state.phase
                ),
            ),
            user_prompt=f"Session state:\n{state.model_dump_json()}",
            provider_stage="generate_narration",
        )

    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Generate a structured debrief from the finished session."""

        payload = {
            "scenario": scenario.model_dump(),
            "final_state": state.model_dump(),
            "timeline": [turn.model_dump() for turn in timeline],
        }
        return self._chat_json(
            model=self.narration_model,
            system_prompt=self._build_json_system_prompt(
                self.debrief_prompt,
                GENERATE_DEBRIEF_EXPECTED_SHAPE,
                addendum=self._resolve_prompt_addendum(scenario, state.audience),
            ),
            user_prompt=f"Ovningsunderlag:\n{json.dumps(payload, ensure_ascii=True)}",
            provider_stage="generate_debrief",
        )

    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Generate a scenario draft from author-provided source text."""

        return self._chat_json(
            model=self.scenario_model,
            system_prompt=self._build_json_system_prompt(
                self.scenario_authoring_prompt,
                GENERATE_SCENARIO_DRAFT_EXPECTED_SHAPE,
            ),
            user_prompt=(f"Kallformat: {source_format}\nKalltext:\n{source_text}"),
            provider_stage="generate_scenario_draft",
        )
