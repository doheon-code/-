"""브리핑 데이터 묶기/풀기 도구.

  python3 build_site.py pack   <작업폴더> <출력.json>   # 작업폴더/briefings/*.md + tracker.json -> 웹페이지용 JSON
  python3 build_site.py unpack <입력.json> <작업폴더>   # 웹페이지용 JSON -> briefings/*.md + tracker.json
  python3 build_site.py                                 # 저장소 기본값: news/ -> news/site/briefings.json

웹페이지의 briefings.json 이 모든 기록의 원본이다. tracker.json 형식이 어긋나면
에러를 내고 멈춘다 (잘못된 데이터가 페이지에 올라가지 않도록).
"""

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ISSUE_STATUS = {"진행 중", "소강", "종료"}
FORECAST_STATUS = {"대기", "발생", "미발생", "판단불가"}


def fail(msg: str) -> None:
    sys.exit(f"tracker.json 오류: {msg}")


def check_date(value, where: str) -> None:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        fail(f"{where}: 날짜는 YYYY-MM-DD 형식이어야 합니다 ({value!r})")


def validate(tracker: dict) -> None:
    issue_ids = set()
    for i, issue in enumerate(tracker.get("issues", [])):
        where = f"issues[{i}]"
        for key in ("id", "title", "area", "status", "summary", "updated"):
            if not issue.get(key):
                fail(f"{where}.{key} 가 비어 있습니다")
        if issue["status"] not in ISSUE_STATUS:
            fail(f"{where}.status 는 {sorted(ISSUE_STATUS)} 중 하나여야 합니다")
        check_date(issue["updated"], f"{where}.updated")
        issue_ids.add(issue["id"])
        for j, t in enumerate(issue.get("timeline", [])):
            check_date(t.get("date"), f"{where}.timeline[{j}].date")
        scenarios = issue.get("outlook", {}).get("scenarios", [])
        if scenarios:
            total = sum(s.get("probability", 0) for s in scenarios)
            if total != 100:
                fail(f"{where}.outlook.scenarios 확률 합이 100이 아닙니다 ({total})")
    seen = set()
    for i, f in enumerate(tracker.get("forecasts", [])):
        where = f"forecasts[{i}]"
        for key in ("id", "made", "issue", "claim", "probability", "due", "basis", "status"):
            if f.get(key) in (None, ""):
                fail(f"{where}.{key} 가 비어 있습니다")
        if f["id"] in seen:
            fail(f"{where}.id 중복: {f['id']}")
        seen.add(f["id"])
        if f["issue"] not in issue_ids:
            fail(f"{where}.issue 가 issues 에 없는 id 입니다 ({f['issue']})")
        p = f["probability"]
        if not isinstance(p, int) or not 5 <= p <= 95:
            fail(f"{where}.probability 는 5~95 정수여야 합니다 ({p!r})")
        if f["status"] not in FORECAST_STATUS:
            fail(f"{where}.status 는 {sorted(FORECAST_STATUS)} 중 하나여야 합니다")
        check_date(f["made"], f"{where}.made")
        check_date(f["due"], f"{where}.due")
        if f["status"] != "대기":
            check_date(f.get("resolved"), f"{where}.resolved")


def score(forecasts: list) -> dict:
    """결과가 나온 전망의 채점. Brier 점수는 0(완벽)~1, 항상 50%로 찍으면 0.25."""
    done = [f for f in forecasts if f["status"] in ("발생", "미발생")]
    if not done:
        return {"resolved": 0}
    brier = sum((f["probability"] / 100 - (f["status"] == "발생")) ** 2 for f in done) / len(done)
    right = sum((f["probability"] >= 50) == (f["status"] == "발생") for f in done)
    return {"resolved": len(done), "right": right, "brier": round(brier, 3)}


def pack(work: Path, out: Path) -> None:
    items = []
    for path in sorted((work / "briefings").glob("*.md"), reverse=True):
        if not DATE.fullmatch(path.stem):
            continue
        text = path.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        items.append({"date": path.stem, "title": first.lstrip("# ").strip(), "markdown": text})

    tracker_path = work / "tracker.json"
    tracker = json.loads(tracker_path.read_text(encoding="utf-8")) if tracker_path.exists() else {}
    validate(tracker)
    forecasts = tracker.get("forecasts", [])

    kst = timezone(timedelta(hours=9))
    data = {
        "updated": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"),
        "briefings": items,
        "issues": tracker.get("issues", []),
        "forecasts": forecasts,
        "score": score(forecasts),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out}: 브리핑 {len(items)}개, 이슈 {len(data['issues'])}개, 전망 {len(forecasts)}개")


def unpack(src: Path, work: Path) -> None:
    data = json.loads(src.read_text(encoding="utf-8"))
    (work / "briefings").mkdir(parents=True, exist_ok=True)
    for b in data.get("briefings", []):
        (work / "briefings" / f"{b['date']}.md").write_text(b["markdown"], encoding="utf-8")
    tracker = {"issues": data.get("issues", []), "forecasts": data.get("forecasts", [])}
    (work / "tracker.json").write_text(json.dumps(tracker, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{work}: 브리핑 {len(data.get('briefings', []))}개, 이슈 {len(tracker['issues'])}개, 전망 {len(tracker['forecasts'])}개")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        pack(ROOT, ROOT / "site" / "briefings.json")
    elif len(args) == 3 and args[0] == "pack":
        pack(Path(args[1]), Path(args[2]))
    elif len(args) == 3 and args[0] == "unpack":
        unpack(Path(args[1]), Path(args[2]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
