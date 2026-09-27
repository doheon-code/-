"""CLI: python -m kakao_reply <내보낸 대화.txt> --me <내 이름>"""

from __future__ import annotations

import argparse
import sys

import anthropic

from .analyzer import build_style_profile, compute_stats, format_stats, text_messages
from .parser import parse_file


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="kakao_reply", description="카카오톡 대화 분석 & 답장 문구 자동 생성")
    p.add_argument("file", help="카카오톡 '대화 내보내기'로 저장한 .txt 파일")
    p.add_argument("--me", help="대화방에서 표시되는 내 이름 (생략하면 참여자 목록을 보여줌)")
    p.add_argument("-n", "--count", type=int, default=3, help="답장 후보 개수 (기본 3)")
    p.add_argument("--context", type=int, default=40, help="분석에 사용할 최근 메시지 수 (기본 40)")
    p.add_argument("--tone", help='원하는 방향/톤 (예: "정중하게 거절", "짧고 귀엽게")')
    p.add_argument("--stats-only", action="store_true", help="API 호출 없이 통계만 출력")
    args = p.parse_args(argv)

    messages = parse_file(args.file)
    if not messages:
        print("메시지를 찾지 못했습니다. 카카오톡 '대화 내보내기' 텍스트 파일인지 확인해 주세요.", file=sys.stderr)
        return 1

    stats = compute_stats(messages)
    print("=== 대화 통계 ===")
    print(format_stats(stats))

    if args.stats_only:
        return 0

    if not args.me:
        names = ", ".join(s for s, _ in stats.per_sender.most_common())
        print(f"\n--me 로 내 이름을 지정해 주세요. 대화 참여자: {names}", file=sys.stderr)
        return 1
    if args.me not in stats.per_sender:
        names = ", ".join(stats.per_sender)
        print(f"\n'{args.me}' 님을 대화에서 찾지 못했습니다. 참여자: {names}", file=sys.stderr)
        return 1

    style = build_style_profile(messages, args.me)
    print(f"\n=== 내 말투 분석 ({args.me}) ===")
    print(style.describe())

    recent = text_messages(messages)[-args.context:]
    if recent and recent[-1].sender == args.me:
        print("\n(참고: 마지막 메시지가 내가 보낸 것이라, 이어서 보낼 후속 메시지를 제안합니다.)")

    from .generator import RefusalError, generate_replies

    try:
        result = generate_replies(recent, args.me, style, count=args.count, instruction=args.tone)
    except RefusalError as e:
        print(f"\n{e}", file=sys.stderr)
        return 2
    except anthropic.AuthenticationError:
        print("\nAPI 인증 실패: ANTHROPIC_API_KEY 환경변수를 확인해 주세요.", file=sys.stderr)
        return 2
    except TypeError as e:
        if "authentication" not in str(e):
            raise
        print("\nAPI 키가 없습니다. ANTHROPIC_API_KEY 환경변수를 설정해 주세요.", file=sys.stderr)
        return 2
    except anthropic.RateLimitError:
        print("\n요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.", file=sys.stderr)
        return 2
    except anthropic.APIStatusError as e:
        print(f"\nAPI 오류 ({e.status_code}): {e.message}", file=sys.stderr)
        return 2
    except anthropic.APIConnectionError:
        print("\nAPI 서버에 연결할 수 없습니다. 네트워크를 확인해 주세요.", file=sys.stderr)
        return 2

    print("\n=== 대화 분석 ===")
    print(f"요약: {result.summary}")
    print(f"분위기: {result.mood}")
    print(f"상대 마지막 메시지 의도: {result.last_message_intent}")
    print("\n=== 추천 답장 ===")
    for i, r in enumerate(result.replies, 1):
        print(f"{i}. [{r.tone}] {r.text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
