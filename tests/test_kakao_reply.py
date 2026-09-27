import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from kakao_reply.analyzer import build_style_profile, compute_stats
from kakao_reply.generator import generate_replies
from kakao_reply.parser import parse_file, parse_lines

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def test_parse_pc_format_with_multiline_and_dates():
    msgs = parse_file(SAMPLES / "sample_pc.txt")
    assert [m.sender for m in msgs][:3] == ["김민지", "나", "김민지"]
    assert msgs[0].timestamp == datetime(2026, 9, 25, 20, 2)
    assert "성수 새로 생긴 카페" in msgs[2].text  # 여러 줄 메시지 합치기
    assert msgs[-1].timestamp == datetime(2026, 9, 26, 11, 30)
    assert msgs[4].is_media


def test_parse_android_format():
    msgs = parse_file(SAMPLES / "sample_android.txt")
    assert len(msgs) == 3
    assert msgs[1].sender == "이대리"
    assert msgs[1].timestamp == datetime(2026, 9, 26, 17, 42)


def test_parse_ios_format_and_noon_midnight():
    msgs = parse_lines([
        "2026. 9. 26. 오전 12:05, 철수 : 자니?",
        "2026. 9. 26. 오후 12:30, 영희 : 점심 먹자",
        "2026. 9. 26. 15:10, 철수 : ㅇㅋ",
    ])
    assert [m.timestamp.hour for m in msgs] == [0, 12, 15]


def test_stats_and_style_profile():
    msgs = parse_file(SAMPLES / "sample_pc.txt")
    stats = compute_stats(msgs)
    assert stats.per_sender["김민지"] == 4
    style = build_style_profile(msgs, "나")
    assert style.message_count == 3
    assert style.laugh_ratio > 0.5
    assert style.honorific_ratio < 0.5


def test_generate_replies_with_fake_client():
    captured = {}
    payload = {
        "summary": "주말 카페 약속을 잡는 중",
        "mood": "밝음",
        "last_message_intent": "토요일 2시 가능 여부 질문",
        "replies": [{"tone": "수락", "text": "완전 좋아ㅋㅋ 토욜 2시 콜!!"}],
    }

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps(payload))])

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    msgs = parse_file(SAMPLES / "sample_pc.txt")
    result = generate_replies(msgs, "나", build_style_profile(msgs, "나"), count=1, client=client)

    assert result.replies[0].text == "완전 좋아ㅋㅋ 토욜 2시 콜!!"
    prompt = captured["messages"][0]["content"]
    assert "나(나): 그냥 집 가려구ㅋㅋ 왜??" in prompt
    assert captured["output_config"]["format"]["type"] == "json_schema"
