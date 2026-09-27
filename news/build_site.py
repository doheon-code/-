"""news/briefings/*.md 를 모아 웹페이지용 news/site/briefings.json 을 만든다."""

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIEFINGS = ROOT / "briefings"
OUT = ROOT / "site" / "briefings.json"


def main() -> None:
    items = []
    for path in sorted(BRIEFINGS.glob("*.md"), reverse=True):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):
            continue
        text = path.read_text(encoding="utf-8")
        first = text.splitlines()[0] if text else ""
        items.append({
            "date": path.stem,
            "title": first.lstrip("# ").strip(),
            "markdown": text,
        })
    kst = timezone(timedelta(hours=9))
    data = {"updated": datetime.now(kst).strftime("%Y-%m-%d %H:%M KST"), "briefings": items}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{OUT.relative_to(ROOT.parent)}: {len(items)}개 브리핑")


if __name__ == "__main__":
    main()
