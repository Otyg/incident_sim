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

"""OpenRouter runtime provider implementation.

The provider uses OpenRouter's OpenAI-compatible chat completions API while
reusing the shared structured task flow from ``StructuredLLMProvider``.
"""

import json
import re
from typing import Any
from urllib import error, request

from src.logging_utils import get_logger
from src.services.llm_provider import (
    ProviderConfigurationError,
    ProviderResponseFormatError,
    ProviderUpstreamError,
)
from src.services.providers.base import StructuredLLMProvider


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 120
logger = get_logger(__name__)


class OpenRouterProvider(StructuredLLMProvider):
    """Runtime provider backed by OpenRouter's chat completions API."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create an OpenRouter provider from config data."""

        super().__init__(config)
        self.base_url = str(
            self.config.get("base_url") or DEFAULT_OPENROUTER_BASE_URL
        ).rstrip("/")
        self.chat_completions_url = f"{self.base_url}/chat/completions"
        self.default_model = str(self.config.get("model") or "")
        self.interpret_model = str(
            self.config.get("interpret_model") or self.default_model
        )
        self.narration_model = str(
            self.config.get("narration_model") or self.default_model
        )
        self.scenario_model = str(
            self.config.get("scenario_model") or self.default_model
        )
        self.api_key = self.config.get("api_key")
        self.app_url = self.config.get("app_url")
        self.app_name = self.config.get("app_name")
        self.timeout_seconds = int(
            self.config.get("timeout_seconds") or DEFAULT_TIMEOUT_SECONDS
        )
        logger.info(
            "Initialized OpenRouterProvider base_url=%s interpret_model=%s narration_model=%s scenario_model=%s",
            self.base_url,
            self.interpret_model,
            self.narration_model,
            self.scenario_model,
        )

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for OpenRouter requests."""

        if not self.api_key:
            raise ProviderConfigurationError(
                "OpenRouterProvider requires llm_provider.openrouter.api_key"
            )

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self.app_url:
            headers["HTTP-Referer"] = str(self.app_url)
        if self.app_name:
            headers["X-Title"] = str(self.app_name)
        return headers

    def _build_request_body(
        self, model: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """Build a chat-completions request payload for OpenRouter."""

        if not model:
            raise ProviderConfigurationError(
                "OpenRouterProvider requires a configured model for this stage"
            )

        return {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
        }

    def _post_json(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a JSON payload to OpenRouter and return the parsed JSON body."""

        raw_request = request.Request(
            self.chat_completions_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=self._build_headers(),
            method="POST",
        )
        with request.urlopen(raw_request, timeout=self.timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))

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
    def _extract_content(response: dict[str, Any]) -> str | None:
        """Extract message content from an OpenRouter chat-completions response."""

        choices = response.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return None

        message = first_choice.get("message")
        if not isinstance(message, dict):
            return None

        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
            if parts:
                return "\n".join(parts)

        return None

    @classmethod
    def _extract_json_payload(
        cls, response: dict[str, Any], *, provider_stage: str
    ) -> dict[str, Any]:
        """Extract and parse the JSON object returned by OpenRouter."""

        content = cls._extract_content(response)
        raw_response_excerpt = json.dumps(response, ensure_ascii=False)[:2000]

        if not content:
            logger.warning(
                "OpenRouter response was missing message content stage=%s raw_excerpt=%s",
                provider_stage,
                raw_response_excerpt,
            )
            raise ProviderResponseFormatError(
                "OpenRouter response did not contain message content",
                provider_stage=provider_stage,
                raw_response_excerpt=raw_response_excerpt,
            )

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            repaired = cls._repair_json_text(content)
            if repaired != content:
                try:
                    parsed = json.loads(repaired)
                except json.JSONDecodeError:
                    parsed = None
                else:
                    if not isinstance(parsed, dict):
                        raise ProviderResponseFormatError(
                            "OpenRouter response JSON must be an object",
                            provider_stage=provider_stage,
                            raw_response_excerpt=raw_response_excerpt,
                        )
                    return parsed

            start = content.find("{")
            end = content.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise ProviderResponseFormatError(
                    "OpenRouter response was not valid JSON",
                    provider_stage=provider_stage,
                    raw_response_excerpt=raw_response_excerpt,
                ) from None
            try:
                parsed = json.loads(content[start : end + 1])
            except json.JSONDecodeError as exc:
                raise ProviderResponseFormatError(
                    "OpenRouter response was not valid JSON",
                    provider_stage=provider_stage,
                    raw_response_excerpt=raw_response_excerpt,
                ) from exc

        if not isinstance(parsed, dict):
            raise ProviderResponseFormatError(
                "OpenRouter response JSON must be an object",
                provider_stage=provider_stage,
                raw_response_excerpt=raw_response_excerpt,
            )
        return parsed

    @staticmethod
    def _extract_status_code(exc: Exception) -> int | None:
        """Best-effort extraction of an HTTP status code from a request exception."""

        if isinstance(exc, error.HTTPError):
            return exc.code
        code = getattr(exc, "code", None)
        return code if isinstance(code, int) else None

    @classmethod
    def _build_upstream_error(
        cls, exc: Exception, *, model: str, provider_stage: str
    ) -> ProviderUpstreamError:
        """Normalize OpenRouter HTTP failures into a structured upstream error."""

        status_code = cls._extract_status_code(exc)
        retryable = status_code in {408, 429} or (
            status_code is not None and 500 <= status_code <= 599
        )
        message = f"OpenRouter request failed during {provider_stage}: {exc}"
        if status_code is not None:
            message = (
                f"OpenRouter request failed during {provider_stage} "
                f"with upstream status {status_code}: {exc}"
            )

        logger.warning(
            "OpenRouter request failed model=%s stage=%s upstream_status=%s retryable=%s",
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
        """Send a chat request to OpenRouter and parse the returned JSON object."""

        payload = self._build_request_body(model, system_prompt, user_prompt)
        try:
            response = self._post_json(payload)
        except ProviderConfigurationError:
            raise
        except Exception as exc:
            raise self._build_upstream_error(
                exc,
                model=model,
                provider_stage=provider_stage,
            ) from exc

        logger.info(
            "OpenRouter request completed for model=%s stage=%s",
            model,
            provider_stage,
        )
        return self._extract_json_payload(response, provider_stage=provider_stage)
