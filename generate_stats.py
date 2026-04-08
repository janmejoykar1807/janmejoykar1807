"""
generate_stats.py
=================
Fetches real GitHub stats via the GitHub GraphQL API and generates
a styled SVG card matching Janmejoy's dark README theme.

Outputs: assets/stats.svg

Environment variables required:
    GITHUB_TOKEN  — personal access token or Actions GITHUB_TOKEN
    GITHUB_USER   — GitHub username (default: janmejoykar1807)
"""

import os
import json
import math
import urllib.request
import urllib.error
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_USER  = os.environ.get("GITHUB_USER", "janmejoykar1807")
OUTPUT_PATH  = os.environ.get("OUTPUT_PATH", "assets/stats.svg")

# Theme — matches your README's dark palette exactly
THEME = {
    "bg_start":      "#0d1117",
    "bg_end":        "#161b22",
    "border":        "#21262d",
    "title":         "#e6edf3",
    "text":          "#c9d1d9",
    "muted":         "#8b949e",
    "blue":          "#58a6ff",
    "green":         "#3fb950",
    "purple":        "#bc8cff",
    "orange":        "#f78166",
    "yellow":        "#e3b341",
}

# ── GitHub GraphQL fetch ──────────────────────────────────────────────────────

GRAPHQL_QUERY = """
query($login: String!) {
  user(login: $login) {
    name
    login
    createdAt
    followers { totalCount }
    following  { totalCount }
    repositories(ownerAffiliations: [OWNER], privacy: PUBLIC, first: 100) {
      totalCount
      nodes {
        stargazerCount
        forkCount
        primaryLanguage { name }
        isFork
      }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays {
            contributionCount
            date
          }
        }
      }
    }
    pullRequests(states: [MERGED]) { totalCount }
    issues(states: [OPEN, CLOSED])  { totalCount }
    repositoriesContributedTo(
      contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY]
      includeUserRepositories: true
    ) { totalCount }
  }
}
"""

def fetch_stats():
    if not GITHUB_TOKEN:
        raise ValueError("GITHUB_TOKEN environment variable not set")

    payload = json.dumps({
        "query": GRAPHQL_QUERY,
        "variables": {"login": GITHUB_USER}
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "github-stats-svg/1.0"
        },
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=15) as res:
        data = json.loads(res.read().decode("utf-8"))

    if "errors" in data:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")

    return data["data"]["user"]


def parse_stats(user):
    repos = user["repositories"]["nodes"]
    own_repos = [r for r in repos if not r["isFork"]]

    total_stars = sum(r["stargazerCount"] for r in own_repos)
    total_forks = sum(r["forkCount"] for r in own_repos)

    cc = user["contributionsCollection"]
    calendar = cc["contributionCalendar"]

    # Total commits across all time (API only gives current year in collection)
    total_commits = cc["totalCommitContributions"]
    total_prs     = user["pullRequests"]["totalCount"]
    total_issues  = user["issues"]["totalCount"]
    total_contribs = calendar["totalContributions"]

    # Contribution streak calculation
    all_days = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            all_days.append((day["date"], day["contributionCount"]))
    all_days.sort(key=lambda x: x[0], reverse=True)

    current_streak = 0
    longest_streak = 0
    temp_streak = 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Current streak
    for date, count in all_days:
        if date > today:
            continue
        if count > 0:
            current_streak += 1
        else:
            break

    # Longest streak
    for _, count in sorted(all_days, key=lambda x: x[0]):
        if count > 0:
            temp_streak += 1
            longest_streak = max(longest_streak, temp_streak)
        else:
            temp_streak = 0

    return {
        "name":            user.get("name") or user["login"],
        "login":           user["login"],
        "total_commits":   total_commits,
        "total_prs":       total_prs,
        "total_issues":    total_issues,
        "total_stars":     total_stars,
        "total_forks":     total_forks,
        "total_repos":     user["repositories"]["totalCount"],
        "followers":       user["followers"]["totalCount"],
        "total_contribs":  total_contribs,
        "current_streak":  current_streak,
        "longest_streak":  longest_streak,
        "contrib_calendar": all_days,
    }

# ── SVG generation ────────────────────────────────────────────────────────────

def fmt(n):
    """Format large numbers compactly."""
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(n)

def mini_calendar(days, width=340, height=56):
    """Generate a mini contribution heatmap SVG fragment."""
    # Take last 26 weeks = 182 days
    recent = sorted(days, key=lambda x: x[0])[-182:]
    if not recent:
        return ""

    max_count = max(c for _, c in recent) or 1
    cell = 7
    gap  = 2
    cols = math.ceil(len(recent) / 7)

    def color(count):
        if count == 0:   return "#161b22"
        ratio = count / max_count
        if ratio < 0.25: return "#0e4429"
        if ratio < 0.50: return "#006d32"
        if ratio < 0.75: return "#26a641"
        return "#39d353"

    cells = []
    for i, (date, count) in enumerate(recent):
        col = i // 7
        row = i % 7
        x = col * (cell + gap)
        y = row * (cell + gap)
        c = color(count)
        cells.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
            f'rx="1.5" fill="{c}" opacity="0.9">'
            f'<title>{date}: {count} contributions</title></rect>'
        )

    total_width = cols * (cell + gap)
    return f'<g transform="translate(0,0)">{"".join(cells)}</g>', total_width


def generate_svg(stats):
    T = THEME
    W = 480
    H = 280
    pad = 24

    # Stats rows — (label, value, color, icon_path)
    rows = [
        ("Total Commits",       fmt(stats["total_commits"]),  T["blue"],   "M3 3h18v2H3zm0 4h18v2H3zm0 4h12v2H3z"),
        ("Pull Requests",       fmt(stats["total_prs"]),      T["purple"], "M7 3a3 3 0 0 0 0 6h10a3 3 0 0 0 0-6H7zM4 9a5 5 0 1 1 10 0H4zm8 0a5 5 0 1 1-10 0h10z"),
        ("Issues",              fmt(stats["total_issues"]),   T["orange"], "M12 2a10 10 0 1 0 0 20A10 10 0 0 0 12 2zm0 5a1 1 0 1 1 0 2 1 1 0 0 1 0-2zm-1 4h2v6h-2z"),
        ("Stars Earned",        fmt(stats["total_stars"]),    T["yellow"], "M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"),
        ("Current Streak",      f"{stats['current_streak']} days", T["green"],  "M13 2L3 14h9l-1 8 10-12h-9l1-8z"),
        ("Longest Streak",      f"{stats['longest_streak']} days", T["green"],  "M13 2L3 14h9l-1 8 10-12h-9l1-8z"),
        ("Total Repos",         fmt(stats["total_repos"]),    T["blue"],   "M3 3h18v2H3zm0 4h18v2H3zm0 4h12v2H3z"),
        ("Followers",           fmt(stats["followers"]),      T["muted"],  "M16 11c1.66 0 2.99-1.34 2.99-3S17.66 5 16 5c-1.66 0-3 1.34-3 3s1.34 3 3 3zm-8 0c1.66 0 2.99-1.34 2.99-3S9.66 5 8 5C6.34 5 5 6.34 5 8s1.34 3 3 3z"),
    ]

    # Calendar fragment
    cal_result = mini_calendar(stats["contrib_calendar"])
    if cal_result:
        cal_svg, cal_w = cal_result
    else:
        cal_svg, cal_w = "", 0

    # Layout: 2 columns of stats, calendar below
    col_w    = (W - pad * 2 - 16) // 2
    row_h    = 28
    stats_h  = math.ceil(len(rows) / 2) * row_h
    cal_y    = pad + 48 + stats_h + 16
    cal_h    = 7 * 9   # 7 rows × (7px + 2px gap)
    H        = cal_y + cal_h + pad + 8

    # Build stat items
    items_svg = []
    for i, (label, value, color, _) in enumerate(rows):
        col = i % 2
        row = i // 2
        x = pad + col * (col_w + 16)
        y = pad + 48 + row * row_h

        items_svg.append(f'''
        <g transform="translate({x},{y})">
          <circle cx="5" cy="5" r="4" fill="{color}" opacity="0.2"/>
          <circle cx="5" cy="5" r="2" fill="{color}"/>
          <text x="16" y="9" font-size="11" fill="{T['muted']}"
                font-family="'Segoe UI',system-ui,sans-serif">{label}</text>
          <text x="{col_w - 4}" y="9" font-size="12" fill="{color}" font-weight="600"
                font-family="'Segoe UI',system-ui,sans-serif"
                text-anchor="end">{value}</text>
        </g>''')

    # Updated timestamp
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%"   stop-color="{T['bg_start']}"/>
      <stop offset="100%" stop-color="{T['bg_end']}"/>
    </linearGradient>
    <linearGradient id="title_grad" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%"   stop-color="{T['blue']}"/>
      <stop offset="100%" stop-color="{T['purple']}"/>
    </linearGradient>
    <style>
      @keyframes fadeIn {{0%{{opacity:0;transform:translateY(8px)}}100%{{opacity:1;transform:translateY(0)}}}}
      .card{{animation:fadeIn .6s ease-out both}}
      .row{{animation:fadeIn .5s ease-out both}}
    </style>
  </defs>

  <!-- Background -->
  <rect width="{W}" height="{H}" rx="12" fill="url(#bg)" class="card"/>
  <rect width="{W}" height="{H}" rx="12" fill="none"
        stroke="{T['border']}" stroke-width="1"/>

  <!-- Title -->
  <text x="{pad}" y="{pad + 20}" font-size="16" font-weight="700"
        font-family="'Segoe UI',system-ui,sans-serif"
        fill="url(#title_grad)" class="card">{stats['name']}'s GitHub Stats</text>

  <!-- Subtitle -->
  <text x="{pad}" y="{pad + 36}" font-size="11"
        font-family="'Segoe UI',system-ui,sans-serif"
        fill="{T['muted']}" class="card">@{stats['login']} · {stats['total_contribs']} contributions this year</text>

  <!-- Divider -->
  <line x1="{pad}" y1="{pad + 44}" x2="{W - pad}" y2="{pad + 44}"
        stroke="{T['border']}" stroke-width="0.5"/>

  <!-- Stats rows -->
  {''.join(items_svg)}

  <!-- Contribution calendar label -->
  <text x="{pad}" y="{cal_y - 6}" font-size="10"
        font-family="'Segoe UI',system-ui,sans-serif"
        fill="{T['muted']}">contribution activity · last 26 weeks</text>

  <!-- Contribution calendar -->
  <g transform="translate({pad},{cal_y})">
    {cal_svg}
  </g>

  <!-- Updated timestamp -->
  <text x="{W - pad}" y="{H - 8}" font-size="9"
        font-family="'Segoe UI',system-ui,sans-serif"
        fill="{T['muted']}" text-anchor="end" opacity="0.6">
    auto-generated {updated}
  </text>
</svg>'''

    return svg

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print(f"Fetching stats for @{GITHUB_USER}...")
    user_data = fetch_stats()
    stats = parse_stats(user_data)

    print(f"  Commits  : {stats['total_commits']}")
    print(f"  PRs      : {stats['total_prs']}")
    print(f"  Issues   : {stats['total_issues']}")
    print(f"  Stars    : {stats['total_stars']}")
    print(f"  Streak   : {stats['current_streak']} days (longest: {stats['longest_streak']})")

    svg = generate_svg(stats)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(svg)

    print(f"SVG written to {OUTPUT_PATH} ({len(svg)} chars)")


if __name__ == "__main__":
    main()
