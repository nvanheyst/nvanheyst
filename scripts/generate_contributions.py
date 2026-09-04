#!/usr/bin/env python3
"""Merge contribution graphs from two GitHub accounts and render a combined SVG."""
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""

COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

CELL = 10
GAP = 3
STEP = CELL + GAP
PAD_LEFT = 28
PAD_TOP = 18
PAD_BOTTOM = 8
PAD_RIGHT = 8


def fetch(token: str, login: str, from_date: str, to_date: str) -> dict[str, int]:
    payload = json.dumps({
        "query": QUERY,
        "variables": {"login": login, "from": from_date, "to": to_date},
    }).encode()
    req = Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urlopen(req) as resp:
        data = json.loads(resp.read())
    out: dict[str, int] = {}
    for week in data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
        for day in week["contributionDays"]:
            out[day["date"]] = day["contributionCount"]
    return out


def color(count: int) -> str:
    if count == 0:
        return COLORS[0]
    if count <= 3:
        return COLORS[1]
    if count <= 6:
        return COLORS[2]
    if count <= 9:
        return COLORS[3]
    return COLORS[4]


def render(contributions: dict[str, int]) -> str:
    today = datetime.now(timezone.utc).date()
    # Align start to the most recent Sunday, 52 weeks back
    start = today - timedelta(weeks=52)
    start -= timedelta(days=(start.weekday() + 1) % 7)

    weeks: list[list] = []
    day = start
    while day <= today:
        week = [day + timedelta(days=i) for i in range(7)]
        weeks.append(week)
        day += timedelta(weeks=1)

    width = PAD_LEFT + len(weeks) * STEP + PAD_RIGHT
    height = PAD_TOP + 7 * STEP + PAD_BOTTOM

    cells = []
    month_labels = []
    seen_months: set[int] = set()
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]

    for wi, week in enumerate(weeks):
        x = PAD_LEFT + wi * STEP
        for di, d in enumerate(week):
            if d > today:
                continue
            date_str = d.strftime("%Y-%m-%d")
            count = contributions.get(date_str, 0)
            y = PAD_TOP + di * STEP
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{color(count)}"><title>{date_str}: {count}</title></rect>'
            )
            if di == 0 and d.month not in seen_months:
                seen_months.add(d.month)
                month_labels.append(
                    f'<text x="{x}" y="{PAD_TOP - 4}" font-size="9" '
                    f'fill="#767676" font-family="system-ui,sans-serif">'
                    f'{d.strftime("%b")}</text>'
                )

    day_label_els = [
        f'<text x="{PAD_LEFT - 4}" y="{PAD_TOP + di * STEP + CELL}" font-size="9" '
        f'fill="#767676" font-family="system-ui,sans-serif" text-anchor="end">'
        f'{day_names[di]}</text>'
        for di in (1, 3, 5)
    ]

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">\n'
        + "\n".join(month_labels + day_label_els + cells)
        + "\n</svg>\n"
    )


def main() -> None:
    token_personal = os.environ["TOKEN_PERSONAL"]
    token_work = os.environ["TOKEN_WORK"]
    login_personal = os.environ.get("LOGIN_PERSONAL", "nvanheyst")
    login_work = os.environ.get("LOGIN_WORK", "nvh-cpr")
    output = os.environ.get("OUTPUT", "contributions.svg")

    now = datetime.now(timezone.utc)
    to_date = now.isoformat()
    from_date = (now - timedelta(weeks=53)).isoformat()

    print(f"fetching {login_personal}...")
    personal = fetch(token_personal, login_personal, from_date, to_date)
    print(f"fetching {login_work}...")
    work = fetch(token_work, login_work, from_date, to_date)

    merged: dict[str, int] = defaultdict(int)
    for d, n in personal.items():
        merged[d] += n
    for d, n in work.items():
        merged[d] += n

    # Only update if either account had activity in the last 7 days
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=7)).isoformat()
    recent = sum(n for d, n in personal.items() if d >= cutoff) + \
             sum(n for d, n in work.items() if d >= cutoff)
    if recent == 0:
        print("no contributions in the last 7 days — skipping update")
        return

    print(f"total contributions: {sum(merged.values())}")
    svg = render(dict(merged))

    with open(output, "w") as f:
        f.write(svg)
    print(f"written → {output}")


if __name__ == "__main__":
    main()
