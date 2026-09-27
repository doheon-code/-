"""API 호출 없이 로컬에서 계산하는 대화 통계와 말투 분석."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .parser import Message

_WORD = re.compile(r"[가-힣A-Za-z0-9]{2,}")
_LAUGH = re.compile(r"[ㅋㅎ]{2,}")
_CRY = re.compile(r"[ㅠㅜ]{2,}")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
_HONORIFIC_ENDINGS = ("요", "니다", "세요", "까요", "죠")

STOPWORDS = {
    "그리고", "그래서", "근데", "그냥", "진짜", "너무", "이제", "혹시", "아니",
    "나도", "저도", "이거", "그거", "저거", "오늘", "내일", "사진", "이모티콘",
}


@dataclass
class StyleProfile:
    sender: str
    message_count: int
    avg_length: float
    laugh_ratio: float       # ㅋㅋ/ㅎㅎ 포함 비율
    cry_ratio: float         # ㅠㅠ/ㅜㅜ 포함 비율
    emoji_ratio: float
    honorific_ratio: float   # 존댓말 어미 비율
    frequent_endings: list[str] = field(default_factory=list)
    samples: list[str] = field(default_factory=list)

    def describe(self) -> str:
        speech = "존댓말" if self.honorific_ratio >= 0.5 else "반말"
        return (
            f"- 주로 {speech} 사용 (존댓말 비율 {self.honorific_ratio:.0%})\n"
            f"- 평균 메시지 길이 {self.avg_length:.1f}자\n"
            f"- ㅋㅋ/ㅎㅎ 사용 {self.laugh_ratio:.0%}, ㅠㅠ 사용 {self.cry_ratio:.0%}, "
            f"이모지 사용 {self.emoji_ratio:.0%}\n"
            f"- 자주 쓰는 말끝: {', '.join(self.frequent_endings) or '없음'}"
        )


@dataclass
class ChatStats:
    total_messages: int
    per_sender: Counter
    top_words: list[tuple[str, int]]
    active_hours: list[tuple[int, int]]
    first_date: str | None
    last_date: str | None


def text_messages(messages: list[Message]) -> list[Message]:
    return [m for m in messages if not m.is_media]


def compute_stats(messages: list[Message], top_n: int = 15) -> ChatStats:
    words = Counter()
    hours = Counter()
    for m in text_messages(messages):
        words.update(w for w in _WORD.findall(m.text) if w not in STOPWORDS)
        if m.timestamp:
            hours[m.timestamp.hour] += 1
    stamps = [m.timestamp for m in messages if m.timestamp]
    return ChatStats(
        total_messages=len(messages),
        per_sender=Counter(m.sender for m in messages),
        top_words=words.most_common(top_n),
        active_hours=hours.most_common(3),
        first_date=min(stamps).strftime("%Y-%m-%d") if stamps else None,
        last_date=max(stamps).strftime("%Y-%m-%d") if stamps else None,
    )


def _ending(text: str) -> str | None:
    cleaned = re.sub(r"[\s.!?~^ㅋㅎㅠㅜ]+$", "", text)
    cleaned = _EMOJI.sub("", cleaned).strip()
    return cleaned[-2:].strip() if len(cleaned) >= 2 else None


def build_style_profile(messages: list[Message], sender: str, sample_count: int = 30) -> StyleProfile:
    mine = [m.text for m in text_messages(messages) if m.sender == sender]
    n = len(mine) or 1

    def ratio(pred) -> float:
        return sum(1 for t in mine if pred(t)) / n

    endings = Counter(e for t in mine if (e := _ending(t)))
    # 너무 긴 메시지는 샘플에서 제외해 말투가 잘 드러나는 짧은 문장을 우선
    samples = [t for t in mine if 2 <= len(t) <= 80][-sample_count:]

    return StyleProfile(
        sender=sender,
        message_count=len(mine),
        avg_length=sum(len(t) for t in mine) / n,
        laugh_ratio=ratio(lambda t: _LAUGH.search(t)),
        cry_ratio=ratio(lambda t: _CRY.search(t)),
        emoji_ratio=ratio(lambda t: _EMOJI.search(t)),
        honorific_ratio=ratio(lambda t: _ending(t) is not None and _ending(t).endswith(_HONORIFIC_ENDINGS)),
        frequent_endings=[e for e, _ in endings.most_common(5)],
        samples=samples,
    )


def format_stats(stats: ChatStats) -> str:
    lines = [f"기간: {stats.first_date} ~ {stats.last_date}", f"전체 메시지: {stats.total_messages}개", "", "보낸 사람별:"]
    for sender, count in stats.per_sender.most_common():
        lines.append(f"  {sender}: {count}개 ({count / stats.total_messages:.0%})")
    if stats.active_hours:
        lines.append("가장 활발한 시간대: " + ", ".join(f"{h}시({c})" for h, c in stats.active_hours))
    if stats.top_words:
        lines.append("자주 나온 단어: " + ", ".join(f"{w}({c})" for w, c in stats.top_words))
    return "\n".join(lines)
