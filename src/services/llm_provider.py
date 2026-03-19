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

"""Provider abstractions and schema validation helpers for LLM output.

The module is the central integration point for runtime LLM access. It defines:
- the provider interface used by the API layer
- configuration loading from ``config.yaml``
- concrete runtime providers such as Ollama
- validation wrappers that convert raw provider payloads into typed Pydantic
  models

To add a new provider, a developer typically needs to:
1. implement ``LLMProvider``
2. add a configuration section under ``llm_provider`` in ``config.yaml``
3. extend ``get_llm_provider()`` so the new provider can be selected
4. keep provider output schema-compatible so existing validation still works
"""

import json
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from src.logging_utils import get_logger
from src.models.session import SessionState
from src.models.turn import Turn
from src.models.scenario import Scenario
from src.schemas.debrief_response import DebriefResponse
from src.schemas.interpreted_action import InterpretedAction
from src.schemas.narrator_response import NarratorResponse
from src.services.scenario_draft_normalizer import normalize_scenario_payload


PROMPTS_DIR = Path(__file__).resolve().parents[2] / "data" / "prompts"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config.yaml"
logger = get_logger(__name__)


class LLMProviderError(Exception):
    """Base exception for provider-related failures."""

    pass


class ProviderUpstreamError(LLMProviderError):
    """Raised when an upstream LLM provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        provider_stage: str,
        upstream_status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.provider_stage = provider_stage
        self.upstream_status_code = upstream_status_code
        self.retryable = retryable


class ProviderOutputValidationError(LLMProviderError):
    """Raised when provider output cannot be validated against schemas."""

    pass


class ProviderConfigurationError(LLMProviderError):
    """Raised when provider configuration is unsupported or unavailable."""

    pass


class ProviderResponseFormatError(LLMProviderError):
    """Raised when provider text output cannot be parsed into JSON."""

    def __init__(
        self,
        message: str,
        *,
        provider_stage: str | None = None,
        raw_response_excerpt: str | None = None,
        retryable: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider_stage = provider_stage
        self.raw_response_excerpt = raw_response_excerpt
        self.retryable = retryable


class LLMProvider(ABC):
    """Abstract interface for action interpretation and narration providers.

    Every runtime provider must implement the same two operations:
    - ``interpret_action`` for transforming participant free text into a
      structured action payload
    - ``generate_narration`` for turning a session state into a structured
      narration payload

    The returned dictionaries are intentionally raw. They are validated later
    through Pydantic schemas so all providers share the same output contract.
    """

    @abstractmethod
    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant free text into structured action data.

        Args:
            participant_input: Free-text participant action to interpret.

        Returns:
            dict[str, Any]: Raw structured payload to validate as an
                ``InterpretedAction``.
        """

        raise NotImplementedError

    @abstractmethod
    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate narration from a session state snapshot.

        Args:
            state: Session state after rules have been applied.

        Returns:
            dict[str, Any]: Raw structured payload to validate as a
                ``NarratorResponse``.
        """

        raise NotImplementedError

    @abstractmethod
    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Generate a debrief from scenario, final state and timeline."""

        raise NotImplementedError

    @abstractmethod
    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Generate a scenario draft from author-provided source text."""

        raise NotImplementedError


def load_prompt(name: str) -> str:
    """Load a prompt file from the prompt directory.

    Args:
        name: File name of the prompt to load.

    Returns:
        str: Prompt contents as UTF-8 text.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """

    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load application configuration from ``config.yaml``.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: Parsed configuration document.

    Raises:
        ProviderConfigurationError: If the file is missing or invalid.
    """

    config_path = path or CONFIG_PATH

    if not config_path.exists():
        logger.error("LLM configuration file was not found: %s", config_path)
        raise ProviderConfigurationError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except yaml.YAMLError as exc:
        logger.error(
            "Failed to parse LLM configuration from %s",
            config_path,
            exc_info=True,
        )
        raise ProviderConfigurationError(
            f"Invalid YAML configuration in {config_path}"
        ) from exc

    if not isinstance(data, dict):
        logger.error("LLM configuration root was not a mapping in %s", config_path)
        raise ProviderConfigurationError(
            f"Configuration root must be a mapping in {config_path}"
        )

    logger.info("Loaded application configuration from %s", config_path)
    return data


def load_llm_config(path: Path | None = None) -> dict[str, Any]:
    """Load the LLM-specific configuration section.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        dict[str, Any]: LLM provider configuration mapping.

    Raises:
        ProviderConfigurationError: If the ``llm_provider`` section is missing.

    Notes:
        The expected structure is a top-level ``llm_provider`` mapping with a
        ``provider`` selector and one nested mapping per supported provider,
        for example ``ollama`` or ``openai``.
    """

    data = load_config(path)
    llm_config = data.get("llm_provider")

    if not isinstance(llm_config, dict):
        logger.error("Missing or invalid llm_provider section in config.yaml")
        raise ProviderConfigurationError(
            "Missing or invalid llm_provider section in config.yaml"
        )

    logger.info("Loaded llm_provider configuration")
    return llm_config


def validate_interpreted_action(payload: dict[str, Any]) -> InterpretedAction:
    """Validate raw provider output as an interpreted action.

    Args:
        payload: Raw provider payload for action interpretation.

    Returns:
        InterpretedAction: Validated interpreted action.

    Raises:
        ProviderOutputValidationError: If the payload does not satisfy the
            action schema.
    """

    try:
        return InterpretedAction.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as interpreted action: %s",
            payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError(
            "Invalid interpreted action payload"
        ) from exc


def validate_narration(payload: dict[str, Any]) -> NarratorResponse:
    """Validate raw provider output as a narration payload.

    Args:
        payload: Raw provider payload for narration generation.

    Returns:
        NarratorResponse: Validated narration payload.

    Raises:
        ProviderOutputValidationError: If the payload does not satisfy the
            narration schema.
    """

    normalized_payload = payload
    if isinstance(payload, dict):
        normalized_payload = dict(payload)

        if isinstance(normalized_payload.get("key_points"), list):
            key_points = normalized_payload["key_points"]
            if len(key_points) > 5:
                logger.warning(
                    "Narration payload contained too many key_points; trimming from %s to 5",
                    len(key_points),
                )
                normalized_payload["key_points"] = key_points[:5]

        if isinstance(normalized_payload.get("injects"), list):
            injects = normalized_payload["injects"]
            if len(injects) > 2:
                logger.warning(
                    "Narration payload contained too many injects; trimming from %s to 2",
                    len(injects),
                )
                normalized_payload["injects"] = injects[:2]

    try:
        return NarratorResponse.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as narration payload: %s",
            normalized_payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid narration payload") from exc


def validate_debrief(payload: dict[str, Any]) -> DebriefResponse:
    """Validate raw provider output as a debrief payload."""

    try:
        return DebriefResponse.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as debrief payload: %s",
            payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid debrief payload") from exc


def validate_scenario(payload: dict[str, Any]) -> Scenario:
    """Validate raw provider output as a scenario payload."""

    normalized_payload = payload
    if isinstance(payload, dict):
        normalized_payload = normalize_scenario_payload(payload)

    try:
        return Scenario.model_validate(normalized_payload)
    except ValidationError as exc:
        logger.warning(
            "Provider output did not validate as scenario payload: %s",
            normalized_payload,
            exc_info=True,
        )
        raise ProviderOutputValidationError("Invalid scenario payload") from exc


class OllamaProvider(LLMProvider):
    """Runtime provider backed by the official Ollama Python client.

    The provider supports:
    - local Ollama via ``host: http://localhost:11434``
    - Ollama Cloud via ``host: https://ollama.com`` together with ``api_key``

    It requests JSON-only responses and parses them into Python dictionaries
    before schema validation happens in the API layer.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Create an Ollama-backed runtime provider from config data.

        Args:
            config: Mapping from ``config.yaml`` under ``llm_provider.ollama``.
                Supported keys are ``host``, ``api_key``, ``model``,
                ``interpret_model`` and ``narration_model``.
        """

        self.interpret_prompt = load_prompt("interpret_action.txt")
        self.narration_prompt = load_prompt("generate_narration.txt")
        self.debrief_prompt = load_prompt("generate_debrief.txt")
        self.scenario_authoring_prompt = load_prompt("generate_scenario_draft.txt")
        self.host = str(config.get("host") or "http://localhost:11434")
        self.default_model = str(config.get("model") or "llama3.2")
        self.interpret_model = str(config.get("interpret_model") or self.default_model)
        self.narration_model = str(config.get("narration_model") or self.default_model)
        self.scenario_model = str(config.get("scenario_model") or self.default_model)
        self.api_key = config.get("api_key")
        self.client = self._create_client(self.host, self._build_headers())
        logger.info(
            "Initialized OllamaProvider host=%s interpret_model=%s narration_model=%s scenario_model=%s",
            self.host,
            self.interpret_model,
            self.narration_model,
            self.scenario_model,
        )

    @staticmethod
    def _create_client(host: str, headers: dict[str, str] | None):
        """Create an Ollama client instance.

        Args:
            host: Base URL for the Ollama endpoint.
            headers: Optional headers applied to each request.

        Returns:
            Any: Instantiated Ollama client.

        Raises:
            ProviderConfigurationError: If the Ollama package is not installed.
        """

        try:
            from ollama import Client
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The ollama package is required for OllamaProvider. Install it with pip install ollama."
            ) from exc

        return Client(host=host, headers=headers or None)

    def _build_headers(self) -> dict[str, str] | None:
        """Build optional authorization headers for Ollama requests.

        Returns:
            dict[str, str] | None: Authorization headers when an API key is
                configured, otherwise ``None``.
        """

        if not self.api_key:
            return None

        return {"Authorization": f"Bearer {self.api_key}"}

    @staticmethod
    def _build_raw_response_excerpt(
        response_dump: Any, candidate_contents: list[str]
    ) -> str | None:
        """Build a compact loggable preview of the raw provider response."""

        excerpt_source = None
        for candidate in candidate_contents:
            if isinstance(candidate, str) and candidate.strip():
                excerpt_source = candidate.strip()
                break

        if excerpt_source is None and response_dump is not None:
            try:
                excerpt_source = json.dumps(response_dump, ensure_ascii=False)
            except TypeError:
                excerpt_source = str(response_dump)

        if excerpt_source is None:
            return None

        compact = re.sub(r"\s+", " ", excerpt_source).strip()
        return compact[:2000]

    @staticmethod
    def _repair_json_text(text: str) -> str:
        """Apply conservative repairs for common LLM JSON formatting mistakes."""

        repaired = text.strip()

        fenced_match = re.search(
            r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```",
            repaired,
            flags=re.DOTALL | re.IGNORECASE,
        )
        if fenced_match:
            repaired = fenced_match.group(1).strip()

        repaired = (
            repaired.replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2018", "'")
            .replace("\u2019", "'")
        )
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return repaired

    @staticmethod
    def _extract_json_payload(response: Any, *, provider_stage: str) -> dict[str, Any]:
        """Extract and parse JSON content from an Ollama chat response.

        Args:
            response: Response object returned by the Ollama client.

        Returns:
            dict[str, Any]: Parsed JSON payload.

        Raises:
            ProviderResponseFormatError: If the response content is missing or
                cannot be parsed as a JSON object.
        """

        response_dump = None
        if hasattr(response, "model_dump"):
            try:
                response_dump = response.model_dump()
            except Exception:
                response_dump = None
        elif isinstance(response, dict):
            response_dump = response

        candidate_contents: list[str] = []

        message = getattr(response, "message", None)
        if message is None and isinstance(response_dump, dict):
            message = response_dump.get("message")

        if message is not None:
            content = getattr(message, "content", None)
            thinking = getattr(message, "thinking", None)
            if isinstance(message, dict):
                content = content or message.get("content")
                thinking = thinking or message.get("thinking")
            if isinstance(content, str) and content.strip():
                candidate_contents.append(content)
            if isinstance(thinking, str) and thinking.strip():
                candidate_contents.append(thinking)

        if isinstance(response_dump, dict):
            for key in ("content", "response", "message"):
                value = response_dump.get(key)
                if isinstance(value, str) and value.strip():
                    candidate_contents.append(value)
                elif isinstance(value, dict):
                    nested_content = value.get("content")
                    nested_thinking = value.get("thinking")
                    if isinstance(nested_content, str) and nested_content.strip():
                        candidate_contents.append(nested_content)
                    if isinstance(nested_thinking, str) and nested_thinking.strip():
                        candidate_contents.append(nested_thinking)

        stripped = None
        for candidate in candidate_contents:
            if isinstance(candidate, str) and candidate.strip():
                stripped = candidate.strip()
                break

        raw_response_excerpt = OllamaProvider._build_raw_response_excerpt(
            response_dump, candidate_contents
        )

        if not stripped:
            logger.warning(
                "Ollama response was missing message content stage=%s raw_excerpt=%s",
                provider_stage,
                raw_response_excerpt,
            )
            raise ProviderResponseFormatError(
                "Ollama response did not contain message content",
                provider_stage=provider_stage,
                raw_response_excerpt=raw_response_excerpt,
            )
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            repaired = OllamaProvider._repair_json_text(stripped)
            if repaired != stripped:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = None
                else:
                    if not isinstance(parsed, dict):
                        logger.warning(
                            "Ollama repaired JSON was not an object stage=%s raw_excerpt=%s",
                            provider_stage,
                            raw_response_excerpt,
                        )
                        raise ProviderResponseFormatError(
                            "Ollama response JSON must be an object",
                            provider_stage=provider_stage,
                            raw_response_excerpt=raw_response_excerpt,
                        )
                    logger.info(
                        "Ollama response JSON repaired successfully stage=%s",
                        provider_stage,
                    )
                    return parsed

            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end == -1 or end <= start:
                logger.warning(
                    "Ollama response was not valid JSON stage=%s raw_excerpt=%s",
                    provider_stage,
                    raw_response_excerpt,
                )
                raise ProviderResponseFormatError(
                    "Ollama response was not valid JSON",
                    provider_stage=provider_stage,
                    raw_response_excerpt=raw_response_excerpt,
                ) from None

            try:
                parsed = json.loads(stripped[start : end + 1])
            except json.JSONDecodeError as exc:
                logger.warning(
                    "Ollama response was not valid JSON after substring extraction stage=%s raw_excerpt=%s",
                    provider_stage,
                    raw_response_excerpt,
                )
                raise ProviderResponseFormatError(
                    "Ollama response was not valid JSON",
                    provider_stage=provider_stage,
                    raw_response_excerpt=raw_response_excerpt,
                ) from exc

        if not isinstance(parsed, dict):
            logger.warning(
                "Ollama response JSON was not an object stage=%s raw_excerpt=%s",
                provider_stage,
                raw_response_excerpt,
            )
            raise ProviderResponseFormatError(
                "Ollama response JSON must be an object",
                provider_stage=provider_stage,
                raw_response_excerpt=raw_response_excerpt,
            )

        return parsed

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        """Best-effort extraction of an HTTP status code from a client exception."""

        for attribute in ("status_code", "status", "code"):
            value = getattr(exc, attribute, None)
            if isinstance(value, int):
                return value

        response = getattr(exc, "response", None)
        if response is not None:
            for attribute in ("status_code", "status"):
                value = getattr(response, attribute, None)
                if isinstance(value, int):
                    return value

        return None

    @classmethod
    def _build_upstream_error(
        cls, exc: Exception, *, model: str, provider_stage: str
    ) -> ProviderUpstreamError:
        """Normalize Ollama client failures into a structured upstream error."""

        status_code = cls._extract_status_code(exc)
        retryable = status_code is not None and 500 <= status_code <= 599
        message = f"Ollama request failed during {provider_stage}: {exc}"
        if status_code is not None:
            message = (
                f"Ollama request failed during {provider_stage} "
                f"with upstream status {status_code}: {exc}"
            )

        logger.warning(
            "Ollama request failed model=%s stage=%s upstream_status=%s retryable=%s",
            model,
            provider_stage,
            status_code,
            retryable,
            exc_info=True,
        )
        return ProviderUpstreamError(
            message,
            provider_stage=provider_stage,
            upstream_status_code=status_code,
            retryable=retryable,
        )

    def _chat_json(
        self, model: str, system_prompt: str, user_prompt: str, provider_stage: str
    ) -> dict[str, Any]:
        """Send a chat request and parse the returned JSON object.

        Args:
            model: Ollama model name to use.
            system_prompt: System instruction describing the task and format.
            user_prompt: User-specific request content.

        Returns:
            dict[str, Any]: Parsed JSON payload returned by the model.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the response content is not JSON.
        """

        try:
            response = self.client.chat(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                format="json",
                stream=False,
            )
        except Exception as exc:
            raise self._build_upstream_error(
                exc,
                model=model,
                provider_stage=provider_stage,
            ) from exc

        logger.info(
            "Ollama request completed for model=%s stage=%s", model, provider_stage
        )
        return self._extract_json_payload(response, provider_stage=provider_stage)

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Interpret participant text via Ollama.

        Args:
            participant_input: Free-text participant action.

        Returns:
            dict[str, Any]: Raw payload intended for ``InterpretedAction``.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the model does not return JSON.
        """

        expected_shape = {
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
        return self._chat_json(
            model=self.interpret_model,
            system_prompt=(
                f"{self.interpret_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Deltagaratgard:\n{participant_input}",
            provider_stage="interpret_action",
        )

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Generate a narrated situation update via Ollama.

        Args:
            state: Session state after deterministic rules have been applied.

        Returns:
            dict[str, Any]: Raw payload intended for ``NarratorResponse``.

        Raises:
            LLMProviderError: If the Ollama request fails.
            ProviderResponseFormatError: If the model does not return JSON.
        """

        expected_shape = {
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
        return self._chat_json(
            model=self.narration_model,
            system_prompt=(
                f"{self.narration_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Session state:\n{state.model_dump_json()}",
            provider_stage="generate_narration",
        )

    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Generate a structured debrief from the finished session."""

        expected_shape = {
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
        payload = {
            "scenario": scenario.model_dump(),
            "final_state": state.model_dump(),
            "timeline": [turn.model_dump() for turn in timeline],
        }
        return self._chat_json(
            model=self.narration_model,
            system_prompt=(
                f"{self.debrief_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=f"Ovningsunderlag:\n{json.dumps(payload, ensure_ascii=True)}",
            provider_stage="generate_debrief",
        )

    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Generate a scenario draft from author-provided source text."""

        expected_shape = {
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
            "target_aliases": [
                {"id": "string", "canonical": "string", "aliases": ["string"]}
            ],
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
            "presentation_guidelines": {
                "krisledning": {"focus": ["string"], "tone": "string"}
            },
        }
        return self._chat_json(
            model=self.scenario_model,
            system_prompt=(
                f"{self.scenario_authoring_prompt}\n"
                "Return only a single JSON object and no surrounding prose.\n"
                f"Expected shape: {json.dumps(expected_shape, ensure_ascii=True)}"
            ),
            user_prompt=(f"Kallformat: {source_format}\nKalltext:\n{source_text}"),
            provider_stage="generate_scenario_draft",
        )


class OpenAIProvider(LLMProvider):
    """Stub implementation for a future OpenAI-backed provider.

    The class currently loads prompt files but intentionally raises a
    configuration error when called because external integration is not yet
    implemented in this project.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create an OpenAI provider stub from config data.

        Args:
            config: Mapping from ``config.yaml`` under ``llm_provider.openai``.
                The values are currently stored for future use only.
        """

        self.interpret_prompt = load_prompt("interpret_action.txt")
        self.narration_prompt = load_prompt("generate_narration.txt")
        self.debrief_prompt = load_prompt("generate_debrief.txt")
        self.scenario_authoring_prompt = load_prompt("generate_scenario_draft.txt")
        self.config = config or {}
        logger.info("Initialized OpenAIProvider stub")

    def interpret_action(self, participant_input: str) -> dict[str, Any]:
        """Attempt to interpret an action with the OpenAI provider.

        Args:
            participant_input: Free-text participant action.

        Returns:
            dict[str, Any]: Never returns while the provider is stubbed.

        Raises:
            ProviderConfigurationError: Always, because the provider is not yet
                implemented.
        """

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_narration(self, state: SessionState) -> dict[str, Any]:
        """Attempt to generate narration with the OpenAI provider.

        Args:
            state: Session state to narrate.

        Returns:
            dict[str, Any]: Never returns while the provider is stubbed.

        Raises:
            ProviderConfigurationError: Always, because the provider is not yet
                implemented.
        """

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_debrief(
        self, scenario: Scenario, state: SessionState, timeline: list[Turn]
    ) -> dict[str, Any]:
        """Attempt to generate a debrief with the OpenAI provider."""

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")

    def generate_scenario_draft(
        self, source_text: str, source_format: str = "markdown"
    ) -> dict[str, Any]:
        """Attempt to generate a scenario draft with the OpenAI provider."""

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")


def get_llm_provider() -> LLMProvider:
    """Create the configured runtime provider instance.

    The provider is selected from ``config.yaml`` by reading
    ``llm_provider.provider`` and then the matching nested provider section.

    Returns:
        LLMProvider: Configured provider instance.

    Raises:
        ProviderConfigurationError: If the configured provider name is not
            supported.

    Notes:
        To add a new provider, extend this factory with a new branch and define
        a matching configuration block in ``config.yaml``.
    """

    llm_config = load_llm_config()
    provider_name = str(llm_config.get("provider") or "ollama").lower()

    if provider_name == "ollama":
        provider_config = llm_config.get("ollama")
        if not isinstance(provider_config, dict):
            logger.error(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
            raise ProviderConfigurationError(
                "Missing or invalid llm_provider.ollama section in config.yaml"
            )
        logger.info("Selected LLM provider=ollama")
        return OllamaProvider(provider_config)

    if provider_name == "openai":
        provider_config = llm_config.get("openai")
        if provider_config is not None and not isinstance(provider_config, dict):
            logger.error("Invalid llm_provider.openai section in config.yaml")
            raise ProviderConfigurationError(
                "Invalid llm_provider.openai section in config.yaml"
            )
        logger.info("Selected LLM provider=openai")
        return OpenAIProvider(provider_config)

    logger.error("Unsupported LLM provider requested: %s", provider_name)
    raise ProviderConfigurationError(f"Unsupported LLM provider: {provider_name}")
