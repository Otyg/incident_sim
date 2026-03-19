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

"""OpenAI runtime provider stub.

The structured task flow is already inherited from ``StructuredLLMProvider``;
this module currently only keeps placeholder transport configuration for a
future implementation.
"""

from typing import Any

from src.logging_utils import get_logger
from src.services.llm_provider import ProviderConfigurationError
from src.services.providers.base import StructuredLLMProvider


logger = get_logger(__name__)


class OpenAIProvider(StructuredLLMProvider):
    """Stub implementation for a future OpenAI-backed provider."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Create an OpenAI provider stub from config data."""

        super().__init__(config)
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
        logger.info("Initialized OpenAIProvider stub")

    def _chat_json(
        self, model: str, system_prompt: str, user_prompt: str, provider_stage: str
    ) -> dict[str, Any]:
        """Attempt to execute a structured request with the OpenAI provider."""

        raise ProviderConfigurationError("OpenAIProvider is not implemented yet")
