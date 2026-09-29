#!/usr/bin/env python3
"""사랑의교회 홈페이지 주보 게시판에서 주보 사진을 찾아 받아 온다.

    python3 tools/fetch_bulletin.py                       # 가장 최근 주보 확인
    python3 tools/fetch_bulletin.py --date 2026-09-20     # 특정 날짜 주보 확인
    python3 tools/fetch_bulletin.py --download            # 사진을 work/날짜/ 에 받기

결과는 JSON 한 줄로 출력한다. status 값:
  done        data/날짜.json이 이미 있다. 할 일 없음
  new         아직 만들지 않은 주보다
  incomplete  오늘 올라온 주보인데 사진이 6장보다 적다. 아직 올리는 중일 수 있다
사진을 하나도 찾지 못하면(홈페이지 구조가 바뀐 경우) status "error"를 출력하고 2로 끝난다.
"""
import argparse
import datetime as dt
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = "https://www.sarang.org/info/sun_bulletin.asp"
# 게시판은 큰 사진 주소를 data-url에, 작은 사진은 src에 둔다
IMAGE = re.compile(r'data-url="(https://image\.godpia\.com/org/jubo/img/(\d{8})_(\d{2})_\d+\.jpg)"')
USER_AGENT = "Mozilla/5.0 (compatible; dotbogi-jubo; +https://eunseo9311.github.io/dotbogi-jubo/)"
EXPECTED_PAGES = 6


def get(url, data=None):
    request = urllib.request.Request(url, data=data, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--date", help="YYYY-MM-DD. 없으면 게시판의 가장 최근 주보")
    parser.add_argument("--download", action="store_true", help="사진을 work/날짜/ 에 받는다")
    args = parser.parse_args()

    form = None
    if args.date:
        dt.date.fromisoformat(args.date)
        form = urllib.parse.urlencode({"d": args.date.replace("-", "")}).encode()
    page = get(PAGE, form).decode("utf-8", "replace")

    issues = {}
    for url, ymd, number in IMAGE.findall(page):
        issues.setdefault(ymd, {})[number] = url
    wanted = args.date.replace("-", "") if args.date else (max(issues) if issues else None)
    if not wanted or wanted not in issues:
        print(json.dumps({
            "status": "error",
            "message": "주보 사진을 찾지 못했습니다. 홈페이지 구조가 바뀌었거나 그 날짜 주보가 없습니다.",
            "dates_on_page": sorted(issues),
        }, ensure_ascii=False))
        return 2

    date = f"{wanted[:4]}-{wanted[4:6]}-{wanted[6:]}"
    images = [issues[wanted][n] for n in sorted(issues[wanted])]
    have_data = (ROOT / "data" / f"{date}.json").exists()
    if have_data:
        status = "done"
    elif len(images) < EXPECTED_PAGES and date == dt.date.today().isoformat():
        status = "incomplete"
    else:
        status = "new"

    folder = ROOT / "work" / date
    saved = []
    if args.download:
        folder.mkdir(parents=True, exist_ok=True)
        for url in images:
            number = IMAGE.search(f'data-url="{url}"').group(3)
            target = folder / f"{number}.jpg"
            if not target.exists():
                target.write_bytes(get(url))
            saved.append(str(target.relative_to(ROOT)))

    print(json.dumps({
        "status": status,
        "date": date,
        "count": len(images),
        "images": images,
        "have_data": have_data,
        "saved": saved,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
