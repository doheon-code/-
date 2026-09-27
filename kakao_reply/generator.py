"""Claude API로 대화 흐름을 분석하고 답장 후보를 생성."""

from __future__ import annotations

import json
from dataclasses import dataclass

import anthropic

from .analyzer import StyleProfile
from .parser import Message

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """너는 카카오톡 답장을 대신 써 주는 도우미야.
사용자(= '나')가 실제로 보낼 답장 문구를 만들어야 하므로, 아래 원칙을 지켜.

- 대화 맥락과 상대방의 마지막 메시지 의도(질문, 부탁, 약속 잡기, 감정 공유 등)에 정확히 반응할 것.
- '나'의 평소 말투(존댓말/반말, 말끝, ㅋㅋ·ㅠㅠ·이모지 사용 빈도, 메시지 길이)를 최대한 흉내 낼 것.
- 카톡답게 짧고 자연스럽게. 설명문이나 따옴표, "답장:" 같은 접두어는 넣지 말 것.
- 모르는 사실(일정, 장소, 금액 등)을 지어내지 말고, 필요하면 되묻거나 여지를 두는 표현을 쓸 것.
- 후보들은 서로 다른 방향(예: 수락/보류/거절, 짧게/정성껏)이 되도록 다양하게 만들 것."""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "최근 대화 요약 (1~2문장)"},
        "mood": {"type": "string", "description": "대화 분위기"},
        "last_message_intent": {"type": "string", "description": "상대 마지막 메시지의 의도"},
        "replies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tone": {"type": "string", "description": "답장 방향/톤 (예: 수락, 공감, 장난스럽게)"},
                    "text": {"type": "string", "description": "그대로 보낼 답장 문구"},
                },
                "required": ["tone", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "mood", "last_message_intent", "replies"],
    "additionalProperties": False,
}


@dataclass
class ReplySuggestion:
    tone: str
    text: str


@dataclass
class ReplyResult:
    summary: str
    mood: str
    last_message_intent: str
    replies: list[ReplySuggestion]


class RefusalError(RuntimeError):
    pass


def _format_transcript(messages: list[Message], me: str) -> str:
    lines = []
    for m in messages:
        who = f"나({m.sender})" if m.sender == me else m.sender
        when = m.timestamp.strftime("%m/%d %H:%M") if m.timestamp else ""
        lines.append(f"[{when}] {who}: {m.text}")
    return "\n".join(lines)


def build_prompt(
    recent: list[Message],
    me: str,
    style: StyleProfile,
    count: int,
    instruction: str | None,
) -> str:
    samples = "\n".join(f"- {s}" for s in style.samples) or "- (샘플 없음)"
    parts = [
        f"<my_style>\n'나'의 이름: {me}\n{style.describe()}\n\n평소 보낸 메시지 예시:\n{samples}\n</my_style>",
        f"<conversation>\n{_format_transcript(recent, me)}\n</conversation>",
        f"위 대화에 이어서 '나'가 보낼 답장 후보를 {count}개 만들어 줘.",
    ]
    if instruction:
        parts.append(f"추가 요청: {instruction}")
    return "\n\n".join(parts)


def generate_replies(
    recent: list[Message],
    me: str,
    style: StyleProfile,
    count: int = 3,
    instruction: str | None = None,
    client: anthropic.Anthropic | None = None,
    model: str = MODEL,
) -> ReplyResult:
    client = client or anthropic.Anthropic()
    response = client.beta.messages.create(
        model=model,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RESULT_SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": build_prompt(recent, me, style, count, instruction)}],
    )

    if response.stop_reason == "refusal":
        raise RefusalError("모델이 이 요청에 대한 응답을 거절했습니다.")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("응답이 max_tokens에서 잘렸습니다.")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)
    return ReplyResult(
        summary=data["summary"],
        mood=data["mood"],
        last_message_intent=data["last_message_intent"],
        replies=[ReplySuggestion(r["tone"], r["text"]) for r in data["replies"]],
    )
