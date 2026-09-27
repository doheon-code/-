"""브리핑 데이터 묶기/풀기 도구.

  python3 build_site.py unpack <입력.json> <작업폴더>   # 웹페이지용 JSON -> 작업폴더 (아래 구조)
  python3 build_site.py todo   <작업폴더>               # 오늘 꼭 해야 할 일 (전망 채점, 주간·월간 요약)
  python3 build_site.py pack   <작업폴더> <출력.json>   # 작업폴더 -> 웹페이지용 JSON
  python3 build_site.py                                 # 저장소 기본값: news/ -> news/site/briefings.json

작업폴더 구조:
  briefings/YYYY-MM-DD.md          날짜별 브리핑
  summaries/week-YYYY-MM-DD.md     주간 요약 (파일 이름의 날짜는 그 주 월요일, 월~일)
  summaries/month-YYYY-MM.md       월간 요약
  tracker.json                     issues, forecasts, indicators

오늘 날짜는 한국 시간 기준이며, 시험할 때는 환경변수 BRIEF_TODAY=YYYY-MM-DD 로 바꿀 수 있다.

웹페이지의 briefings.json 이 모든 기록의 원본이다. tracker.json 형식이 어긋나면
에러를 내고 멈춘다 (잘못된 데이터가 페이지에 올라가지 않도록).
"""

import json
import re
import sys
from collections import Counter
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ISSUE_STATUS = {"진행 중", "소강", "종료"}
FORECAST_STATUS = {"대기", "발생", "미발생", "판단불가"}
FORECAST_KINDS = {"일간", "주간", "월간"}
KST = timezone(timedelta(hours=9))
WEEK_FILE = re.compile(r"week-(\d{4}-\d{2}-\d{2})")
MONTH_FILE = re.compile(r"month-(\d{4}-\d{2})")


def today() -> date:
    override = os.environ.get("BRIEF_TODAY")
    return date.fromisoformat(override) if override else datetime.now(KST).date()


LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")

# 도메인이 .kr 이 아닌 국내 매체. 여기 없고 .kr 도 아니면 해외로 분류한다.
KOREAN_DOMAINS = {
    "hankyung.com", "heraldcorp.com", "koreaherald.com", "koreajoongangdaily.com", "koreatimes.co.kr",
    "newspim.com", "nate.com", "radioseoul1650.com", "koriinsight.com", "raylogue.com", "mindlenews.com",
    "topstarnews.net", "betanews.net", "sedaily.com", "namu.wiki", "fnnews.com", "pressian.com",
    "yna.co.kr", "chosun.com", "joongang.co.kr", "donga.com", "hani.co.kr", "mk.co.kr", "sbs.co.kr",
    "imbc.com", "newsis.com", "ohmynews.com", "tvchosun.com", "segye.com", "munhwa.com", "hankookilbo.com",
    "etnews.com", "kbs.co.kr", "jtbc.co.kr", "mbn.co.kr", "ytn.co.kr", "news1.kr",
}


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":")[0]
    for prefix in ("www.", "m.", "en.", "biz.", "view.", "news.", "archives."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host


def is_korean(domain: str) -> bool:
    return domain.endswith(".kr") or any(domain == d or domain.endswith("." + d) for d in KOREAN_DOMAINS)


def extract_sources(markdown: str) -> list:
    """브리핑 본문의 링크를 모두 뽑아 섹션별 출처 목록으로 만든다 (같은 URL은 한 번만)."""
    section, seen, out = "", set(), []
    for line in markdown.splitlines():
        if line.startswith("## "):
            section = re.sub(r"\s*\(.*\)$", "", line[3:]).strip()
        headline = ""
        m = re.match(r"\s*-\s*\*\*(.+?)\*\*", line)
        if m:
            headline = m.group(1)
        elif line.startswith("출처"):
            headline = "시장 지표 표"
        for name, url in LINK.findall(line):
            if url in seen:
                continue
            seen.add(url)
            d = domain_of(url)
            out.append({"name": name.strip(), "url": url, "domain": d, "korean": is_korean(d),
                        "section": section, "headline": headline})
    return out


def check_sources(value, where: str) -> None:
    if value is None:
        return
    if not isinstance(value, list) or not all(isinstance(s, dict) and s.get("name") and s.get("url") for s in value):
        fail(f"{where}.sources 는 [{{\"name\": 매체명, \"url\": 주소}}, ...] 형식이어야 합니다")


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
            check_sources(t.get("sources"), f"{where}.timeline[{j}]")
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
        check_sources(f.get("sources"), where)
        if f.get("kind", "일간") not in FORECAST_KINDS:
            fail(f"{where}.kind 는 {sorted(FORECAST_KINDS)} 중 하나여야 합니다")
        if f["status"] != "대기":
            check_date(f.get("resolved"), f"{where}.resolved")
            check_sources(f.get("result_sources"), f"{where}.result")
    for i, row in enumerate(tracker.get("indicators", [])):
        where = f"indicators[{i}]"
        check_date(row.get("date"), f"{where}.date")
        values = row.get("values")
        if not isinstance(values, dict) or not values:
            fail(f"{where}.values 는 {{\"지표 이름\": 숫자}} 형식이어야 합니다")
        for k, v in values.items():
            if v is not None and not isinstance(v, (int, float)):
                fail(f"{where}.values[{k!r}] 는 숫자나 null 이어야 합니다 ({v!r})")
        check_sources(row.get("sources"), where)


def score(forecasts: list) -> dict:
    """결과가 나온 전망의 채점. Brier 점수는 0(완벽)~1, 항상 50%로 찍으면 0.25."""
    done = [f for f in forecasts if f["status"] in ("발생", "미발생")]
    if not done:
        return {"resolved": 0}
    brier = sum((f["probability"] / 100 - (f["status"] == "발생")) ** 2 for f in done) / len(done)
    right = sum((f["probability"] >= 50) == (f["status"] == "발생") for f in done)
    # 보정(calibration): 확률 구간별로 "말한 확률"과 "실제로 일어난 비율"을 비교한다.
    buckets = []
    for lo, hi in ((5, 25), (30, 45), (50, 65), (70, 95)):
        group = [f for f in done if lo <= f["probability"] <= hi]
        if group:
            buckets.append({"range": f"{lo}~{hi}%", "n": len(group),
                            "said": round(sum(f["probability"] for f in group) / len(group)),
                            "happened": round(100 * sum(f["status"] == "발생" for f in group) / len(group))})
    return {"resolved": len(done), "right": right, "brier": round(brier, 3), "calibration": buckets}


def media_summary(items: list) -> list:
    """매체별 인용 횟수와 인용한 날짜. 같은 매체의 이름 표기가 여럿이면 가장 많이 쓴 것을 쓴다."""
    by_domain: dict = {}
    for b in items:
        for s in b["sources"]:
            m = by_domain.setdefault(s["domain"], {"domain": s["domain"], "korean": s["korean"],
                                                   "names": Counter(), "count": 0, "dates": set()})
            m["names"][s["name"]] += 1
            m["count"] += 1
            m["dates"].add(b["date"])
    return sorted(({"domain": m["domain"], "name": m["names"].most_common(1)[0][0], "korean": m["korean"],
                    "count": m["count"], "dates": sorted(m["dates"], reverse=True)}
                   for m in by_domain.values()), key=lambda m: (-m["count"], m["name"]))


def snapshot_history(issues: list, day: str) -> None:
    """이슈별 시나리오 확률을 날짜별로 남긴다. 전날과 같으면 새로 남기지 않는다."""
    for issue in issues:
        scen = {s["name"]: s["probability"] for s in issue.get("outlook", {}).get("scenarios", [])}
        if not scen:
            continue
        hist = issue.setdefault("history", [])
        hist[:] = [h for h in hist if h["date"] != day]
        earlier = [h for h in hist if h["date"] < day]
        if not earlier or earlier[-1]["scenarios"] != scen:
            hist.append({"date": day, "scenarios": scen})
        hist.sort(key=lambda h: h["date"])


def load_summaries(work: Path) -> list:
    out = []
    for path in sorted((work / "summaries").glob("*.md"), reverse=True):
        text = path.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        if m := WEEK_FILE.fullmatch(path.stem):
            start = date.fromisoformat(m.group(1))
            if start.weekday() != 0:
                fail(f"summaries/{path.name}: 주간 요약 파일 이름의 날짜는 월요일이어야 합니다")
            kind, end = "주간", start + timedelta(days=6)
        elif m := MONTH_FILE.fullmatch(path.stem):
            start = date.fromisoformat(m.group(1) + "-01")
            kind, end = "월간", (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        else:
            fail(f"summaries/{path.name}: 파일 이름은 week-YYYY-MM-DD.md 또는 month-YYYY-MM.md 여야 합니다")
        out.append({"kind": kind, "key": path.stem, "start": start.isoformat(), "end": end.isoformat(),
                     "title": first.lstrip("# ").strip(), "markdown": text, "sources": extract_sources(text)})
    return out


def todo(work: Path) -> list:
    """오늘 반드시 할 일. 하루를 건너뛰어도 빠진 일이 다음 실행에서 다시 잡힌다."""
    now = today()
    tracker = json.loads((work / "tracker.json").read_text(encoding="utf-8"))
    briefs = {p.stem for p in (work / "briefings").glob("*.md") if DATE.fullmatch(p.stem)}
    have = {p.stem for p in (work / "summaries").glob("*.md")}
    tasks = []
    for f in tracker.get("forecasts", []):
        if f["status"] == "대기" and f["due"] < now.isoformat():
            tasks.append(f"전망 채점: {f['id']} (마감 {f['due']}, 당시 {f['probability']}%) — {f['claim']}")
    monday = now - timedelta(days=now.weekday())
    for back in range(1, 5):  # 최근 4주 안에 빠진 주간 요약
        start = monday - timedelta(weeks=back)
        end = start + timedelta(days=6)
        key = f"week-{start.isoformat()}"
        if key not in have and any(start.isoformat() <= b <= end.isoformat() for b in briefs):
            tasks.append(f"주간 요약 작성: summaries/{key}.md ({start.isoformat()} ~ {end.isoformat()})")
    first = now.replace(day=1)
    for back in range(1, 3):  # 최근 2개월 안에 빠진 월간 요약
        last_day = first - timedelta(days=1)
        start = last_day.replace(day=1)
        key = f"month-{start.strftime('%Y-%m')}"
        if key not in have and any(b.startswith(start.strftime("%Y-%m")) for b in briefs):
            tasks.append(f"월간 요약 작성: summaries/{key}.md ({start.isoformat()} ~ {last_day.isoformat()})")
        first = start
    return tasks


def pack(work: Path, out: Path) -> None:
    items = []
    for path in sorted((work / "briefings").glob("*.md"), reverse=True):
        if not DATE.fullmatch(path.stem):
            continue
        text = path.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        items.append({"date": path.stem, "title": first.lstrip("# ").strip(), "markdown": text,
                      "sources": extract_sources(text)})

    tracker_path = work / "tracker.json"
    tracker = json.loads(tracker_path.read_text(encoding="utf-8")) if tracker_path.exists() else {}
    validate(tracker)
    forecasts = tracker.get("forecasts", [])
    for f in forecasts:
        f.setdefault("kind", "일간")
    issues = tracker.get("issues", [])
    snapshot_history(issues, today().isoformat())
    tracker_path.write_text(json.dumps(tracker, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    summaries = load_summaries(work)

    data = {
        "updated": datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
        "today": today().isoformat(),
        "briefings": items,
        "summaries": summaries,
        "issues": issues,
        "forecasts": forecasts,
        "indicators": sorted(tracker.get("indicators", []), key=lambda r: r["date"]),
        "score": score(forecasts),
        "media": media_summary(items),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    n_src = sum(len(b["sources"]) for b in items)
    print(f"{out}: 브리핑 {len(items)}개, 요약 {len(summaries)}개, 이슈 {len(issues)}개, 전망 {len(forecasts)}개, "
          f"지표 기록 {len(data['indicators'])}일, 출처 {n_src}건(매체 {len(data['media'])}곳)")
    left = todo(work)
    if left:
        print("아직 남은 할 일:\n  - " + "\n  - ".join(left))
    no_src = [b["date"] for b in items if not b["sources"]]
    no_src += [s["key"] for s in summaries if not s["sources"]]
    if no_src:
        print(f"경고: 출처 링크가 하나도 없는 브리핑·요약이 있습니다: {', '.join(no_src)}")


def unpack(src: Path, work: Path) -> None:
    data = json.loads(src.read_text(encoding="utf-8"))
    (work / "briefings").mkdir(parents=True, exist_ok=True)
    for b in data.get("briefings", []):
        (work / "briefings" / f"{b['date']}.md").write_text(b["markdown"], encoding="utf-8")
    (work / "summaries").mkdir(parents=True, exist_ok=True)
    for s in data.get("summaries", []):
        (work / "summaries" / f"{s['key']}.md").write_text(s["markdown"], encoding="utf-8")
    tracker = {"issues": data.get("issues", []), "forecasts": data.get("forecasts", []),
               "indicators": data.get("indicators", [])}
    (work / "tracker.json").write_text(json.dumps(tracker, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{work}: 브리핑 {len(data.get('briefings', []))}개, 요약 {len(data.get('summaries', []))}개, "
          f"이슈 {len(tracker['issues'])}개, 전망 {len(tracker['forecasts'])}개, 지표 기록 {len(tracker['indicators'])}일")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        pack(ROOT, ROOT / "site" / "briefings.json")
    elif len(args) == 3 and args[0] == "pack":
        pack(Path(args[1]), Path(args[2]))
    elif len(args) == 3 and args[0] == "unpack":
        unpack(Path(args[1]), Path(args[2]))
    elif len(args) == 2 and args[0] == "todo":
        tasks = todo(Path(args[1]))
        print(f"오늘({today().isoformat()}) 할 일:")
        print("\n".join(f"  - {x}" for x in tasks) if tasks else "  - 없음 (평소처럼 오늘 브리핑만 작성)")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
