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

# Light GitHub color scheme
COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]

CELL = 12
GAP = 3
STEP = CELL + GAP

PAD_CARD = 24          # inner card padding (left/right/bottom)
PAD_TOP_INNER = 60     # space inside card above grid (title + subtitle + month labels)
PAD_BOTTOM_INNER = 36  # space inside card below grid (streak + legend)
DAY_LABEL_W = 32       # width reserved left of grid for Mon/Wed/Fri


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


def cell_color(count: int) -> str:
    if count == 0:
        return COLORS[0]
    if count <= 3:
        return COLORS[1]
    if count <= 6:
        return COLORS[2]
    if count <= 9:
        return COLORS[3]
    return COLORS[4]


def _streaks(contributions: dict[str, int], today: datetime) -> tuple[int, int]:
    current = 0
    d = today
    while contributions.get(d.strftime("%Y-%m-%d"), 0) > 0:
        current += 1
        d -= timedelta(days=1)

    longest = run = 0
    for date_str in sorted(contributions):
        if contributions[date_str] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return current, longest


def render(contributions: dict[str, int], login_personal: str, login_work: str) -> str:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(weeks=52)
    # Align to Sunday
    start -= timedelta(days=(start.weekday() + 1) % 7)

    weeks: list[list] = []
    day = start
    while day <= today:
        weeks.append([day + timedelta(days=i) for i in range(7)])
        day += timedelta(weeks=1)

    grid_w = len(weeks) * STEP
    grid_h = 7 * STEP

    inner_w = DAY_LABEL_W + grid_w
    card_w = PAD_CARD + inner_w + PAD_CARD
    card_h = PAD_CARD + PAD_TOP_INNER + grid_h + PAD_BOTTOM_INNER + PAD_CARD

    # Grid origin (inside card)
    gx = PAD_CARD + DAY_LABEL_W
    gy = PAD_CARD + PAD_TOP_INNER

    total = sum(contributions.values())
    current_streak, longest_streak = _streaks(contributions, today)
    font = "system-ui,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif"
    label_color = "#57606a"

    # --- Title and subtitle ---
    title_y = PAD_CARD + 18
    subtitle_y = PAD_CARD + 34
    title = (
        f'<text x="{PAD_CARD}" y="{title_y}" font-size="14" font-weight="700" '
        f'fill="#24292f" font-family="{font}">Contributions '
        f'<tspan font-size="11" font-weight="400" fill="{label_color}">· </tspan>'
        f'<tspan font-size="13" font-weight="600" fill="#24292f">{login_personal}</tspan>'
        f'<tspan font-size="11" font-weight="400" fill="{label_color}"> + {login_work}</tspan>'
        f'</text>'
    )
    subtitle = (
        f'<text x="{PAD_CARD}" y="{subtitle_y}" font-size="11" fill="{label_color}" '
        f'font-family="{font}">{total:,} contributions in the last year</text>'
    )

    # --- Pre-compute each month's week span for centered labels ---
    month_week_indices: dict[tuple, list[int]] = {}
    for wi, week in enumerate(weeks):
        for d in week:
            if d <= today:
                key = (d.year, d.month)
                if key not in month_week_indices:
                    month_week_indices[key] = []
                if wi not in month_week_indices[key]:
                    month_week_indices[key].append(wi)

    # --- Month labels (fire on week that contains the 1st of each month) ---
    month_labels = []
    seen_year_months: set[tuple] = set()
    month_label_y = gy - 6

    # --- Day-of-week labels ---
    day_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    day_label_els = [
        f'<text x="{PAD_CARD + DAY_LABEL_W - 5}" y="{gy + di * STEP + CELL}" '
        f'font-size="9" fill="{label_color}" font-family="{font}" text-anchor="end">'
        f'{day_names[di]}</text>'
        for di in (1, 3, 5)
    ]

    # --- Cells ---
    cells = []
    for wi, week in enumerate(weeks):
        x = gx + wi * STEP
        # Month label: fires on the week that contains the 1st of a new month
        for offset in range(7):
                check = week[0] + timedelta(days=offset)
                if check.day == 1 and check <= today and (check.year, check.month) not in seen_year_months:
                    is_first = len(seen_year_months) == 0
                    is_current = (check.year == today.year and check.month == today.month)
                    seen_year_months.add((check.year, check.month))
                    span = month_week_indices.get((check.year, check.month), [wi])
                    center_x = gx + min(span) * STEP + len(span) * STEP / 2
                    label = check.strftime("%b") + (f" '{check.strftime('%y')}" if check.month == 1 or is_first or is_current else "")
                    month_labels.append(
                        f'<text x="{center_x:.0f}" y="{month_label_y}" font-size="10" '
                        f'fill="{label_color}" font-family="{font}" text-anchor="middle">'
                        f'{label}</text>'
                    )
                    break

        for di, d in enumerate(week):
            if d > today:
                continue
            date_str = d.strftime("%Y-%m-%d")
            count = contributions.get(date_str, 0)
            y = gy + di * STEP
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" '
                f'fill="{cell_color(count)}"><title>{date_str}: {count}</title></rect>'
            )

    # --- Bottom row: streak stats (left) + legend (right), baseline-aligned ---
    row_y = gy + grid_h + 24       # text baseline
    box_y = row_y - CELL + 2       # legend squares aligned to text baseline

    streak_text = (
        f'<text x="{PAD_CARD}" y="{row_y}" font-size="10" '
        f'fill="{label_color}" font-family="{font}" font-weight="500">'
        f'Current streak: {current_streak}d'
        f'  ·  Longest: {longest_streak}d</text>'
    )

    legend_x_start = card_w - PAD_CARD - len(COLORS) * (CELL + 3) - 40
    legend = [
        streak_text,
        (
            f'<text x="{legend_x_start - 8}" y="{row_y}" font-size="10" '
            f'fill="{label_color}" font-family="{font}" text-anchor="end">Less</text>'
        ),
    ]
    for i, c in enumerate(COLORS):
        lx = legend_x_start + i * (CELL + 3)
        legend.append(f'<rect x="{lx}" y="{box_y}" width="{CELL}" height="{CELL}" rx="2" fill="{c}"/>')
    more_x = legend_x_start + len(COLORS) * (CELL + 3) + 4
    legend.append(
        f'<text x="{more_x}" y="{row_y}" font-size="10" '
        f'fill="{label_color}" font-family="{font}">More</text>'
    )

    shadow_filter = (
        '<defs><filter id="s" x="-5%" y="-5%" width="110%" height="120%">'
        '<feDropShadow dx="0" dy="4" stdDeviation="8" flood-color="#000" flood-opacity="0.08"/>'
        '</filter></defs>'
    )
    elements = [
        shadow_filter,
        f'<rect width="{card_w}" height="{card_h}" rx="10" fill="#ffffff" filter="url(#s)"/>',
        title,
        subtitle,
        *month_labels,
        *day_label_els,
        *cells,
        *legend,
    ]

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{card_w}" height="{card_h}" viewBox="0 0 {card_w} {card_h}">\n'
        + "\n".join(elements)
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
    recent = (
        sum(n for d, n in personal.items() if d >= cutoff)
        + sum(n for d, n in work.items() if d >= cutoff)
    )
    if recent == 0:
        print("no contributions in the last 7 days — skipping update")
        return

    print(f"total contributions: {sum(merged.values())}")
    svg = render(dict(merged), login_personal, login_work)

    with open(output, "w") as f:
        f.write(svg)
    print(f"written → {output}")


if __name__ == "__main__":
    main()
