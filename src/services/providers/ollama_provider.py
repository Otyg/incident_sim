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

"""Ollama runtime provider implementation.

This module contains only Ollama-specific client, error and JSON extraction
logic. Shared task orchestration is inherited from ``StructuredLLMProvider``.
"""

import json
import re
from typing import Any

from src.logging_utils import get_logger
from src.services.llm_provider import (
    LLMProviderError,
    ProviderConfigurationError,
    ProviderResponseFormatError,
    ProviderUpstreamError,
)
from src.services.providers.base import StructuredLLMProvider


logger = get_logger(__name__)


class OllamaProvider(StructuredLLMProvider):
    """Runtime provider backed by the official Ollama Python client.

    Supports both local Ollama and Ollama Cloud, depending on configured host
    and API key.
    """

    def __init__(self, config: dict[str, Any]) -> None:
        """Create an Ollama-backed runtime provider from config data."""

        super().__init__(config)
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
        """Create an Ollama client instance."""

        try:
            from ollama import Client
        except ImportError as exc:
            raise ProviderConfigurationError(
                "The ollama package is required for OllamaProvider. Install it with pip install ollama."
            ) from exc

        return Client(host=host, headers=headers or None)

    def _build_headers(self) -> dict[str, str] | None:
        """Build optional authorization headers for Ollama requests."""

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
        """Extract and parse JSON content from an Ollama chat response."""

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
        """Send a chat request and parse the returned JSON object."""

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
