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
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent

DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
ISSUE_STATUS = {"진행 중", "소강", "종료"}
FORECAST_STATUS = {"대기", "발생", "미발생", "판단불가"}


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

    kst = timezone(timedelta(hours=9))
    data = {
        "updated": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"),
        "briefings": items,
        "issues": tracker.get("issues", []),
        "forecasts": forecasts,
        "score": score(forecasts),
        "media": media_summary(items),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    n_src = sum(len(b["sources"]) for b in items)
    print(f"{out}: 브리핑 {len(items)}개, 이슈 {len(data['issues'])}개, 전망 {len(forecasts)}개, "
          f"출처 {n_src}건(매체 {len(data['media'])}곳)")
    no_src = [b["date"] for b in items if not b["sources"]]
    if no_src:
        print(f"경고: 출처 링크가 하나도 없는 브리핑이 있습니다: {', '.join(no_src)}")


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
