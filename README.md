# 카카오톡 자동 답장 생성기

카카오톡 **대화 내보내기** 파일(.txt)을 분석해서 대화 통계와 내 말투를 파악하고,
Claude API로 **내 말투를 흉내 낸 답장 문구 후보**를 만들어 줍니다.

## 기능

- 카톡 내보내기 파일 파싱 (PC / Android / iOS 형식, 여러 줄 메시지, UTF-8·CP949)
- 대화 통계: 기간, 사람별 메시지 수, 활발한 시간대, 자주 나온 단어 (API 없이 로컬 계산)
- 내 말투 분석: 존댓말/반말, 평균 길이, ㅋㅋ·ㅠㅠ·이모지 빈도, 자주 쓰는 말끝
- AI 분석: 최근 대화 요약, 분위기, 상대방 마지막 메시지의 의도
- 답장 후보 여러 개 (수락/보류/공감 등 서로 다른 방향)

## 설치

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."   # https://console.anthropic.com 에서 발급
```

## 카톡 대화 내보내기

- **PC**: 채팅방 → 우측 상단 ≡ 메뉴 → `대화 내보내기` → .txt 저장
- **모바일**: 채팅방 → ≡ 메뉴 → 설정(⚙) → `대화 내용 내보내기` → `텍스트만 보내기`

## 사용법

```bash
# 통계만 보기 (API 호출 없음)
python -m kakao_reply 대화.txt --stats-only

# 답장 후보 생성 (--me 에는 채팅방에 표시되는 내 이름)
python -m kakao_reply 대화.txt --me 홍길동

# 옵션
python -m kakao_reply 대화.txt --me 홍길동 -n 5 --tone "정중하게 거절" --context 60
```

| 옵션 | 설명 |
|---|---|
| `--me` | 대화방에서 내 이름 (생략하면 참여자 목록 표시) |
| `-n`, `--count` | 답장 후보 개수 (기본 3) |
| `--tone` | 원하는 방향/톤, 예: `"짧고 귀엽게"`, `"약속 미루기"` |
| `--context` | 분석에 쓸 최근 메시지 수 (기본 40) |
| `--stats-only` | 통계만 출력 |

### 출력 예시

```
=== 대화 분석 ===
요약: 주말에 성수 새 카페에 가기로 하고 시간을 정하는 중
분위기: 밝고 들뜬 분위기
상대 마지막 메시지 의도: 토요일 오후 2시가 괜찮은지 묻는 질문

=== 추천 답장 ===
1. [수락] 완전 좋아ㅋㅋ 토욜 2시 콜!!
2. [시간 조정] 토요일 좋은데 3시쯤은 어때?? 오전에 일이 있어서ㅠ
3. [확인 후 답장] 오 잠깐만 일정 한번 보고 바로 말해줄게ㅋㅋ
```

## 코드에서 사용

```python
from kakao_reply import parse_file, build_style_profile
from kakao_reply.analyzer import text_messages
from kakao_reply.generator import generate_replies

msgs = parse_file("대화.txt")
style = build_style_profile(msgs, "홍길동")
result = generate_replies(text_messages(msgs)[-40:], "홍길동", style, count=3)
for r in result.replies:
    print(r.tone, r.text)
```

## 구조

```
kakao_reply/
  parser.py     # 카톡 내보내기 파일 파서
  analyzer.py   # 통계 & 말투 분석 (로컬)
  generator.py  # Claude API로 분석 + 답장 생성 (JSON 구조화 출력)
  __main__.py   # CLI
samples/        # 예시 대화 파일
tests/          # pytest
```

## 참고

- 대화 내용이 Anthropic API로 전송됩니다. 민감한 대화는 주의하세요.
- 기본 모델은 `claude-opus-5` 이고 `generator.py`의 `MODEL`에서 바꿀 수 있습니다.
- 생성된 문구는 제안일 뿐이니, 보내기 전에 꼭 확인하세요.

테스트: `python -m pytest`

---

## 🗞️ 데일리 정치·경제 브리핑

매일 전 세계와 한국의 정치·경제 뉴스 요약이 [`news/`](news/README.md) 폴더에 쌓입니다.
