#!/usr/bin/env python3
"""돋보기 주보 페이지 만들기.

data/YYYY-MM-DD.json(한 주 주보 내용)을 tools/template.html 틀에 넣어
YYYY-MM-DD/index.html(지난 주보 보관용)과 index.html(가장 최근 주보)을 만든다.

    python3 tools/build.py            # 모든 주보를 검사하고 페이지를 만든다
    python3 tools/build.py --check    # 검사만 하고 파일은 쓰지 않는다

내용 파일에 휴대폰 번호 같은 개인정보가 보이거나 필수 항목이 빠지면
페이지를 만들지 않고 이유를 출력한 뒤 1로 끝난다.
"""
import datetime as dt
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TEMPLATE = ROOT / "tools" / "template.html"
SITE_URL = "https://eunseo9311.github.io/dotbogi-jubo/"
WEEKDAYS = "월화수목금토일"
OG_DESCRIPTION = "사랑의교회 주보를 어르신이 읽기 쉽게 큰 글씨로 옮겼어요. 예배 순서, 이번 주 소식, 함께 드릴 기도를 담았습니다."

# 개인정보 막기: 휴대폰 번호, 계좌번호처럼 보이는 숫자 묶음
PRIVATE_PATTERNS = [
    (re.compile(r"01[016789][-. ]?\d{3,4}[-. ]?\d{4}"), "휴대폰 번호"),
    (re.compile(r"\d{3,6}-\d{2,6}-\d{4,8}(-\d{1,4})?"), "계좌번호로 보이는 숫자"),
]


def e(text):
    return html.escape(str(text), quote=True)


class Invalid(Exception):
    pass


def need(obj, key, where, kind=str):
    if not isinstance(obj, dict) or key not in obj:
        raise Invalid(f"{where}: '{key}' 항목이 없습니다")
    value = obj[key]
    if kind is str and (not isinstance(value, str) or not value.strip()):
        raise Invalid(f"{where}.{key}: 빈 글자입니다")
    if kind is list and not isinstance(value, list):
        raise Invalid(f"{where}.{key}: 목록이어야 합니다")
    if kind is dict and not isinstance(value, dict):
        raise Invalid(f"{where}.{key}: 묶음이어야 합니다")
    return value


def need_lines(obj, key, where, low=1, high=None):
    lines = need(obj, key, where, list)
    if len(lines) < low or (high is not None and len(lines) > high):
        span = f"{low}~{high}개" if high else f"{low}개 이상"
        raise Invalid(f"{where}.{key}: {span}여야 하는데 {len(lines)}개입니다")
    for i, line in enumerate(lines):
        if not isinstance(line, str) or not line.strip():
            raise Invalid(f"{where}.{key}[{i}]: 빈 줄입니다")
    return lines


def all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from all_strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from all_strings(v)


def validate(issue, path):
    where = path.name
    date = need(issue, "date", where)
    if path.stem != date:
        raise Invalid(f"{where}: 파일 이름과 date({date})가 다릅니다")
    dt.date.fromisoformat(date)

    sermon = need(issue, "sermon", where, dict)
    for key in ("kicker", "title", "passage", "preacher"):
        need(sermon, key, f"{where}.sermon")
    for i, verse in enumerate(need(issue, "verses", where, list)):
        need(verse, "text", f"{where}.verses[{i}]")
        need(verse, "ref", f"{where}.verses[{i}]")
    need(issue, "verse_plain", where)

    steps = need(issue, "steps", where, list)
    if not steps:
        raise Invalid(f"{where}.steps: 예배 순서가 비었습니다")
    for i, step in enumerate(steps):
        need(step, "name", f"{where}.steps[{i}]")
        need(step, "text", f"{where}.steps[{i}]")
        for j, hymn in enumerate(step.get("hymns", [])):
            for key in ("book", "number", "title"):
                need(hymn, key, f"{where}.steps[{i}].hymns[{j}]")

    services = need(issue, "services", where, list)
    if not services:
        raise Invalid(f"{where}.services: 부별 안내가 비었습니다")
    for i, svc in enumerate(services):
        for key in ("part", "time", "pre"):
            need(svc, key, f"{where}.services[{i}]")
        for j, fact in enumerate(need(svc, "facts", f"{where}.services[{i}]", list)):
            need(fact, "label", f"{where}.services[{i}].facts[{j}]")
            need_lines(fact, "lines", f"{where}.services[{i}].facts[{j}]")

    need_lines(issue, "confession", where, 0)
    for i, item in enumerate(need(issue, "weekday", where, list)):
        need(item, "name", f"{where}.weekday[{i}]")
        need(item, "time", f"{where}.weekday[{i}]")
        need_lines(item, "lines", f"{where}.weekday[{i}]", 0)

    three = need(issue, "three", where, list)
    if not 1 <= len(three) <= 3:
        raise Invalid(f"{where}.three: 1~3개여야 하는데 {len(three)}개입니다")
    for i, item in enumerate(three):
        need(item, "strong", f"{where}.three[{i}]")
        need(item, "text", f"{where}.three[{i}]")

    news = need(issue, "news", where, list)
    if not 1 <= len(news) <= 12:
        raise Invalid(f"{where}.news: 1~12개여야 하는데 {len(news)}개입니다")
    for i, item in enumerate(news):
        need(item, "tag", f"{where}.news[{i}]")
        need(item, "title", f"{where}.news[{i}]")
        need_lines(item, "lines", f"{where}.news[{i}]", 1, 3)

    joy = issue.get("joy")
    if joy:
        need_lines(joy, "lines", f"{where}.joy", 1, 4)
    need_lines(issue, "prayers", where, 0, 5)

    for text in all_strings(issue):
        for pattern, label in PRIVATE_PATTERNS:
            found = pattern.search(text)
            if found:
                raise Invalid(f"{where}: {label}가 들어 있습니다: {found.group(0)}")


def date_parts(date):
    day = dt.date.fromisoformat(date)
    weekday = WEEKDAYS[day.weekday()]
    weekday_word = "주일" if weekday == "일" else f"{weekday}요일"
    return day, weekday_word


def render_screen1(issue):
    s = issue["sermon"]
    out = []
    out.append(f"""    <article class="card card--accent" aria-labelledby="sermon-title">
      <p class="kicker">{e(s['kicker'])}</p>
      <h3 class="sermon-title" id="sermon-title">“{e(s['title'])}”</h3>
      <dl class="pairs">
        <div><dt>성경</dt><dd>{e(s['passage'])}</dd></div>
        <div><dt>설교</dt><dd>{e(s['preacher'])}</dd></div>
      </dl>
    </article>
""")
    verses = "".join(f"""      <figure class="verse">
        <blockquote><p>{e(v['text'])}</p></blockquote>
        <figcaption>{e(v['ref'])}</figcaption>
      </figure>
""" for v in issue["verses"])
    out.append(f"""
    <section class="stack" aria-labelledby="verse-title">
      <h3 class="block-title" id="verse-title">이번 주 말씀</h3>
{verses}      <div class="plain">
        <p class="plain-label">쉬운 말로 읽으면</p>
        <p>{e(issue['verse_plain'])}</p>
      </div>
    </section>
""")
    steps = []
    for n, step in enumerate(issue["steps"], 1):
        parts = [f"""        <li>
          <p class="step-name"><span class="num lead-num">{n}</span>{e(step['name'])}</p>
          <p>{e(step['text'])}</p>
"""]
        if step.get("hymns"):
            hymns = "".join(f"""            <li>
              <p class="hymn-ref">{e(h['book'])}<span class="hymn-no">{e(h['number'])}</span></p>
              <p class="hymn-title">{e(h['title'])}</p>
            </li>
""" for h in step["hymns"])
            parts.append(f"""          <ul class="hymns">
{hymns}          </ul>
""")
        if step.get("note"):
            parts.append(f"""          <p class="aside">{e(step['note'])}</p>
""")
        parts.append("""        </li>
""")
        steps.append("".join(parts))
    out.append(f"""
    <section class="stack" aria-labelledby="order-title">
      <h3 class="block-title" id="order-title">예배는 이렇게 드립니다</h3>
      <ol class="steps">
{"".join(steps)}      </ol>
    </section>
""")
    cards = []
    for svc in issue["services"]:
        facts = "".join(
            f"""            <div><dt>{e(f['label'])}</dt><dd>{"<br>".join(e(x) for x in f['lines'])}</dd></div>
""" for f in svc["facts"])
        cards.append(f"""        <article class="card" aria-label="{e(svc['part'])} 예배">
          <p class="service-top"><span class="pill">{e(svc['part'])}</span><span class="service-time">{e(svc['time'])}</span></p>
          <p class="service-pre">{e(svc['pre'])}</p>
          <dl class="facts">
{facts}          </dl>
        </article>
""")
    note = ""
    if issue.get("services_note"):
        note = f"""      <p class="aside">{e(issue['services_note'])}</p>
"""
    out.append(f"""
    <section class="stack" aria-labelledby="services-title">
      <h3 class="block-title" id="services-title">부별 안내</h3>
      <p>내가 드리는 예배 시간을 찾아보세요.</p>
      <div class="services">
{"".join(cards)}      </div>
{note}    </section>
""")
    if issue["confession"]:
        lines = "".join(f"""        <li>{e(x)}</li>
""" for x in issue["confession"])
        out.append(f"""
    <section class="stack" aria-labelledby="confess-title">
      <h3 class="block-title" id="confess-title">함께 드리는 고백</h3>
      <p class="muted">주보에 실린 공동체 고백을 한 문장씩 나눠 적었어요.</p>
      <ul class="confession">
{lines}      </ul>
    </section>
""")
    if issue["weekday"]:
        items = []
        for w in issue["weekday"]:
            body = [f"""        <li>
          <p class="week-name">{e(w['name'])}</p>
          <p class="week-time">{e(w['time'])}</p>
"""]
            if w["lines"]:
                body.append(f"""          <p>{"<br>".join(e(x) for x in w['lines'])}</p>
""")
            if w.get("list"):
                rows = "".join(f"""            <li>{e(x)}</li>
""" for x in w["list"])
                body.append(f"""          <ul class="preachers">
{rows}          </ul>
""")
            if w.get("note"):
                body.append(f"""          <p class="aside">{e(w['note'])}</p>
""")
            body.append("""        </li>
""")
            items.append("".join(body))
        out.append(f"""
    <section class="stack" aria-labelledby="week-title">
      <h3 class="block-title" id="week-title">주중 예배와 기도회</h3>
      <ul class="week">
{"".join(items)}      </ul>
    </section>
""")
    return "".join(out)


def render_screen2(issue):
    out = []
    three = "".join(
        f"""        <li><p><span class="num lead-num">{n}</span><strong>{e(t['strong'])}</strong> {e(t['text'])}</p></li>
""" for n, t in enumerate(issue["three"], 1))
    count = ["", "한 가지", "두 가지", "세 가지"][len(issue["three"])]
    out.append(f"""    <section class="three-box" aria-labelledby="three-title">
      <h3 class="block-title" id="three-title">꼭 기억하실 {count}</h3>
      <ol class="three">
{three}      </ol>
    </section>
""")
    cards = []
    for n, item in enumerate(issue["news"], 1):
        sub = f"""          <p class="news-sub">{e(item['sub'])}</p>
""" if item.get("sub") else ""
        lines = "".join(f"""            <li>{e(x)}</li>
""" for x in item["lines"])
        ask = f"""          <p class="ask"><b>문의</b>{e(item['ask'])}</p>
""" if item.get("ask") else ""
        cards.append(f"""        <article class="card" aria-labelledby="n{n}">
          <p class="tag">{e(item['tag'])}</p>
          <h4 class="news-title" id="n{n}">{e(item['title'])}</h4>
{sub}          <ul class="lines">
{lines}          </ul>
{ask}        </article>
""")
    out.append(f"""
    <section class="stack" aria-labelledby="news-title">
      <h3 class="block-title" id="news-title">자세한 소식</h3>
      <div class="news">
{chr(10).join(cards)}      </div>
    </section>
""")
    joy = issue.get("joy")
    if joy:
        lines = "".join(f"""        <li>{e(x)}</li>
""" for x in joy["lines"])
        contact = ""
        if joy.get("contact"):
            contact = f"""      <p class="ask"><b>{e(joy.get('contact_label', '경조사 연락'))}</b>{e(joy['contact'])}</p>
"""
        out.append(f"""
    <section class="stack" aria-labelledby="joy-title">
      <h3 class="block-title" id="joy-title">기쁨과 위로를 나눠요</h3>
      <ul class="lines">
{lines}      </ul>
{contact}    </section>
""")
    if issue["prayers"]:
        prayers = "".join(
            f"""        <li><p><span class="num num--light lead-num">{n}</span>{e(p)}</p></li>
""" for n, p in enumerate(issue["prayers"], 1))
        out.append(f"""
    <article class="card card--accent" aria-labelledby="pray-title">
      <h3 class="block-title" id="pray-title">함께 드릴 기도</h3>
      <ol class="prayers">
{prayers}      </ol>
    </article>
""")
    return "".join(out)


def render_archive(dates, current, at_root):
    """다른 주 주보로 가는 링크. 주보가 하나뿐이면 비운다."""
    if len(dates) < 2:
        return ""
    newest = dates[-1]
    items = []
    for d in reversed(dates[-12:]):
        day, _ = date_parts(d)
        label = f"{day.month}월 {day.day}일"
        if d == newest:
            href = "./" if at_root else "../"
        else:
            href = f"{d}/" if at_root else f"../{d}/"
        if d == current:
            items.append(f'        <li><span aria-current="page">{label}</span></li>\n')
        else:
            items.append(f'        <li><a href="{href}">{label}</a></li>\n')
    return f"""    <nav class="archive" aria-label="다른 주 주보">
      <p class="archive-title">다른 주 주보 보기</p>
      <ul>
{"".join(items)}      </ul>
    </nav>
"""


def render_page(template, issue, dates, at_root):
    date = issue["date"]
    day, weekday_word = date_parts(date)
    newest = dates[-1]
    page_url = SITE_URL if at_root else f"{SITE_URL}{date}/"
    notice = ""
    if date != newest:
        newest_day, _ = date_parts(newest)
        notice = f"""    <p class="old-note">지난 주보예요. <a href="../">{newest_day.month}월 {newest_day.day}일 주보 보기</a></p>
"""
    values = {
        "{{DESCRIPTION}}": e(f"사랑의교회 {day.year}년 {day.month}월 {day.day}일 주보를 어르신이 읽기 쉽게 큰 글씨로 옮긴 페이지"),
        "{{OG_TITLE}}": e(f"돋보기 주보 · {day.month}월 {day.day}일 {weekday_word}"),
        "{{OG_DESCRIPTION}}": e(OG_DESCRIPTION),
        "{{PAGE_URL}}": page_url,
        "{{SITE_URL}}": SITE_URL,
        "{{DATE_LABEL}}": f"{day.year}년 {day.month}월 {day.day}일 {weekday_word}",
        "{{DATE_SHORT}}": f"{day.year}년 {day.month}월 {day.day}일",
        "{{OLD_NOTICE}}\n": notice,
        "{{SCREEN1}}\n": render_screen1(issue),
        "{{SCREEN2}}\n": render_screen2(issue),
        "{{ARCHIVE}}\n": render_archive(dates, date, at_root),
    }
    page = template
    for key, value in values.items():
        if key not in page:
            raise Invalid(f"template.html에 {key.strip()} 자리가 없습니다")
        page = page.replace(key, value)
    leftover = re.search(r"\{\{[A-Z0-9_]+\}\}", page)
    if leftover:
        raise Invalid(f"template.html에 채우지 못한 자리가 있습니다: {leftover.group(0)}")
    return page


def main():
    check_only = "--check" in sys.argv[1:]
    paths = sorted(DATA.glob("????-??-??.json"))
    if not paths:
        print("data/ 폴더에 주보 내용 파일이 없습니다", file=sys.stderr)
        return 1
    issues = []
    try:
        for path in paths:
            issue = json.loads(path.read_text(encoding="utf-8"))
            validate(issue, path)
            issues.append(issue)
    except (Invalid, ValueError) as err:
        print(f"검사 실패: {err}", file=sys.stderr)
        return 1

    template = TEMPLATE.read_text(encoding="utf-8")
    dates = [i["date"] for i in issues]
    pages = {}
    try:
        for issue in issues:
            pages[ROOT / issue["date"] / "index.html"] = render_page(template, issue, dates, at_root=False)
        pages[ROOT / "index.html"] = render_page(template, issues[-1], dates, at_root=True)
    except Invalid as err:
        print(f"만들기 실패: {err}", file=sys.stderr)
        return 1

    if check_only:
        print(f"검사 통과: 주보 {len(issues)}개 ({dates[0]} ~ {dates[-1]})")
        return 0
    for path, page in pages.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(page, encoding="utf-8")
    print(f"만들었습니다: 주보 {len(issues)}개, 첫 화면은 {dates[-1]}")
    for path in pages:
        print(" -", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
