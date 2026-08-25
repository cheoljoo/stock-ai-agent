#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 백엔드 모듈 - AWS Bedrock 대신 로컬 계정 기반 CLI(agy)로 AI 모델을 호출한다.

기존에는 AWS Bedrock(Claude Opus)를 API 키/과금 기반으로 호출했지만,
이 모듈은 로컬에 로그인된 Google/Anthropic 계정 구독 한도 내에서
`agy` CLI(gemini code 계열, Gemini/Claude 모델을 모두 지원)를 서브프로세스로
호출하는 strands Model 구현체를 제공한다.

사용법 (app.py / stock_agent.py 공통):
    from ai_backend import create_agent_model
    model = create_agent_model()
    agent = Agent(model=model, tools=[...], system_prompt="...")

제공자(provider) 전환:
    환경변수 AI_PROVIDER 로 "gemini"(기본값) 또는 "claude" 선택.
    환경변수 AI_MODEL_ID 로 agy가 인식하는 정확한 모델명을 직접 지정 가능
    (예: gemini-3.1-pro-high, claude-sonnet-4-6). agy는 이미 두 제공자를
    모두 지원하므로, Claude를 추가할 때 별도 CLI 연동 코드 없이
    AI_PROVIDER=claude 로만 전환하면 된다.
"""

import asyncio
import os
import shutil
import subprocess
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

from pydantic import BaseModel
from strands.models.model import BaseModelConfig, Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolChoice, ToolSpec

T = TypeVar("T", bound=BaseModel)

# systemd 서비스 등 로그인 셸 PATH를 상속받지 못하는 환경에서도 agy를 찾기 위한 후보 경로
_AGY_FALLBACK_PATHS = [
    os.path.expanduser("~/.local/bin/agy"),
    "/usr/local/bin/agy",
]


def _resolve_agy_path() -> str:
    """agy CLI의 실행 파일 경로를 찾는다.

    환경변수 AGY_BIN으로 직접 지정하거나, PATH에서 찾거나, 잘 알려진 설치 경로를
    순서대로 확인한다.
    """
    override = os.environ.get("AGY_BIN")
    if override and os.path.isfile(override):
        return override

    found = shutil.which("agy")
    if found:
        return found

    for candidate in _AGY_FALLBACK_PATHS:
        if os.path.isfile(candidate):
            return candidate

    raise RuntimeError(
        "agy CLI를 찾을 수 없습니다. AGY_BIN 환경변수로 실행 파일 경로를 직접 지정하거나 "
        "PATH에 agy가 있는지 확인하세요."
    )

# 제공자별 기본 모델 (agy models 명령으로 조회 가능한 이름)
PROVIDER_DEFAULT_MODELS = {
    "gemini": "gemini-3.1-pro-high",
    "claude": "claude-sonnet-4-6",
}

DEFAULT_PROVIDER = "gemini"
DEFAULT_TIMEOUT_SECONDS = 300


class AgyCliConfig(BaseModelConfig, total=False):
    """agy CLI 모델 설정.

    Attributes:
        model_id: agy가 인식하는 모델명 (예: gemini-3.1-pro-high, claude-sonnet-4-6).
        timeout: 서브프로세스 응답 대기 제한 시간(초).
    """

    model_id: str
    timeout: int


class AgyCliModel(Model):
    """`agy -p` 서브프로세스를 통해 응답을 받아오는 strands Model 구현체.

    AWS Bedrock 대신 로컬에 로그인된 계정 구독으로 동작하는 것이 목적이므로,
    도구 호출(tool use)은 지원하지 않고 텍스트 응답만 처리한다. 이 프로젝트의
    Streamlit 앱은 항상 tools=[] 로 Agent를 생성하므로 이 제약은 영향이 없다.
    """

    def __init__(self, **model_config: Any) -> None:
        self.config = AgyCliConfig(**model_config)
        self.config.setdefault("timeout", DEFAULT_TIMEOUT_SECONDS)

    def update_config(self, **model_config: Any) -> None:
        self.config.update(model_config)

    def get_config(self) -> AgyCliConfig:
        return self.config

    @staticmethod
    def _flatten_messages(messages: Messages, system_prompt: str | None) -> str:
        """strands 메시지 목록을 agy에 전달할 하나의 프롬프트 문자열로 변환한다."""
        parts = []
        if system_prompt:
            parts.append(system_prompt.strip())

        for message in messages:
            texts = [block["text"] for block in message.get("content", []) if "text" in block]
            if not texts:
                continue
            label = "User" if message.get("role") == "user" else "Assistant"
            parts.append(f"[{label}]\n" + "\n".join(texts))

        return "\n\n".join(parts)

    def _invoke_cli(self, prompt: str) -> str:
        model_id = self.config.get("model_id") or PROVIDER_DEFAULT_MODELS[DEFAULT_PROVIDER]
        timeout = self.config.get("timeout", DEFAULT_TIMEOUT_SECONDS)

        agy_bin = _resolve_agy_path()
        cmd = [agy_bin, "-p", prompt, "--model", model_id, "--output-format", "text"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError as error:
            raise RuntimeError(
                f"agy CLI 실행에 실패했습니다({agy_bin}). 실행 권한/경로를 확인하세요."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"agy CLI 응답 시간 초과({timeout}초): model={model_id}") from error

        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"agy CLI 오류(exit={result.returncode}, model={model_id}): {detail}")

        return result.stdout.strip()

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        *,
        tool_choice: ToolChoice | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[StreamEvent, None]:
        if tool_specs:
            raise NotImplementedError(
                "AgyCliModel은 도구 호출(tool use)을 지원하지 않습니다. tools=[] 로 Agent를 생성하세요."
            )

        prompt = self._flatten_messages(messages, system_prompt)
        text = await asyncio.to_thread(self._invoke_cli, prompt)

        yield {"messageStart": {"role": "assistant"}}
        yield {"contentBlockStart": {"start": {}}}
        yield {"contentBlockDelta": {"delta": {"text": text}}}
        yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}

    async def structured_output(
        self, output_model: type[T], prompt: Messages, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncGenerator[dict[str, T | Any], None]:
        raise NotImplementedError("AgyCliModel은 structured_output을 지원하지 않습니다.")
        yield  # pragma: no cover - AsyncGenerator 형태를 만족시키기 위한 도달 불가 코드


def create_agent_model(provider: str | None = None, model_id: str | None = None) -> AgyCliModel:
    """환경변수(AI_PROVIDER, AI_MODEL_ID) 또는 인자를 기반으로 AgyCliModel을 생성한다.

    Args:
        provider: "gemini" 또는 "claude". 생략 시 AI_PROVIDER 환경변수(기본값 gemini) 사용.
        model_id: agy가 인식하는 정확한 모델명. 생략 시 AI_MODEL_ID 환경변수 또는
            provider별 기본 모델을 사용한다.
    """
    resolved_provider = (provider or os.environ.get("AI_PROVIDER", DEFAULT_PROVIDER)).lower()
    resolved_model_id = (
        model_id
        or os.environ.get("AI_MODEL_ID")
        or PROVIDER_DEFAULT_MODELS.get(resolved_provider, PROVIDER_DEFAULT_MODELS[DEFAULT_PROVIDER])
    )

    timeout = int(os.environ.get("AI_CLI_TIMEOUT", DEFAULT_TIMEOUT_SECONDS))

    return AgyCliModel(model_id=resolved_model_id, timeout=timeout)
