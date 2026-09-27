"""카카오톡 '대화 내보내기' 텍스트 파일 파서.

지원 형식
- PC(Windows/Mac):  [홍길동] [오후 3:15] 안녕하세요
                    --------------- 2024년 1월 5일 금요일 ---------------
- Android:          2024년 1월 5일 오후 3:15, 홍길동 : 안녕하세요
- iOS:              2024. 1. 5. 오후 3:15, 홍길동 : 안녕하세요
                    2024. 1. 5. 15:15, 홍길동 : 안녕하세요

여러 줄로 이어지는 메시지는 이전 메시지에 합쳐집니다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass
class Message:
    sender: str
    text: str
    timestamp: datetime | None

    @property
    def is_media(self) -> bool:
        return self.text.strip() in MEDIA_PLACEHOLDERS


MEDIA_PLACEHOLDERS = {
    "사진", "동영상", "이모티콘", "파일", "음성메시지", "삭제된 메시지입니다.",
    "사진 2장", "사진 3장", "(이모티콘)", "<사진 읽지 않음>", "<동영상 읽지 않음>",
}

_TIME = r"(?:(?P<ampm>오전|오후)\s*)?(?P<hour>\d{1,2}):(?P<minute>\d{2})"

# PC: [이름] [오후 3:15] 내용
_PC_MSG = re.compile(r"^\[(?P<sender>[^\]]+)\] \[" + _TIME + r"\] (?P<text>.*)$")
# PC 날짜 구분선: --------------- 2024년 1월 5일 금요일 ---------------
_PC_DATE = re.compile(r"^-+\s*(?P<y>\d{4})년 (?P<m>\d{1,2})월 (?P<d>\d{1,2})일.*?-+\s*$")
# Android: 2024년 1월 5일 오후 3:15, 이름 : 내용
_ANDROID_MSG = re.compile(
    r"^(?P<y>\d{4})년 (?P<m>\d{1,2})월 (?P<d>\d{1,2})일 " + _TIME
    + r", (?P<sender>.+?) : (?P<text>.*)$"
)
# iOS: 2024. 1. 5. 오후 3:15, 이름 : 내용
_IOS_MSG = re.compile(
    r"^(?P<y>\d{4})\. (?P<m>\d{1,2})\. (?P<d>\d{1,2})\.? " + _TIME
    + r", (?P<sender>.+?) : (?P<text>.*)$"
)
# 모바일 날짜/시스템 줄 (메시지가 아닌 줄): "2024년 1월 5일 금요일", "2024. 1. 5. 오후 3:15: 홍길동님이 들어왔습니다."
_MOBILE_DATE_ONLY = re.compile(r"^(?P<y>\d{4})(?:년|\.) ?(?P<m>\d{1,2})(?:월|\.) ?(?P<d>\d{1,2})(?:일|\.)")
_HEADER = re.compile(r"(님과 카카오톡 대화|카카오톡 대화|저장한 날짜|Talk_\d)")


def _to_24h(ampm: str | None, hour: int) -> int:
    if ampm == "오후" and hour != 12:
        return hour + 12
    if ampm == "오전" and hour == 12:
        return 0
    return hour


def _build_dt(y: int, m: int, d: int, ampm: str | None, hour: str, minute: str) -> datetime:
    return datetime(y, m, d, _to_24h(ampm, int(hour)), int(minute))


def parse_lines(lines: list[str]) -> list[Message]:
    messages: list[Message] = []
    current_date: date | None = None

    for raw in lines:
        line = raw.rstrip("\r\n").lstrip("﻿")
        if not line.strip():
            continue

        if m := _PC_MSG.match(line):
            ts = None
            if current_date:
                ts = _build_dt(current_date.year, current_date.month, current_date.day,
                               m["ampm"], m["hour"], m["minute"])
            messages.append(Message(m["sender"].strip(), m["text"], ts))
            continue

        if m := _PC_DATE.match(line):
            current_date = date(int(m["y"]), int(m["m"]), int(m["d"]))
            continue

        if m := (_ANDROID_MSG.match(line) or _IOS_MSG.match(line)):
            ts = _build_dt(int(m["y"]), int(m["m"]), int(m["d"]), m["ampm"], m["hour"], m["minute"])
            current_date = ts.date()
            messages.append(Message(m["sender"].strip(), m["text"], ts))
            continue

        # 날짜 구분 줄이나 입장/퇴장 같은 시스템 메시지는 건너뜀
        if _MOBILE_DATE_ONLY.match(line) or (not messages and _HEADER.search(line)):
            continue

        # 그 외의 줄은 직전 메시지의 연속(여러 줄 메시지)
        if messages:
            messages[-1].text += "\n" + line

    return messages


def parse_file(path: str | Path) -> list[Message]:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="replace")
    return parse_lines(text.splitlines())
