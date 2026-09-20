"""
generate_github_stats.py

Pulls REAL stats for a GitHub user via the GitHub GraphQL API and renders
them as a PNG chart saved into the repo (assets/github_stats.png).

Run locally:
    GH_TOKEN=xxxx GITHUB_USERNAME=a7mds2r python generate_github_stats.py

In GitHub Actions, GH_TOKEN should be a repo secret (a classic PAT with
`read:user` scope is required for the contributionsCollection field —
the default GITHUB_TOKEN does NOT have access to it).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import requests
import matplotlib
matplotlib.use("Agg")  # headless backend, needed inside GitHub Actions runners
import matplotlib.pyplot as plt

GITHUB_API_URL = "https://api.github.com/graphql"


def run_graphql_query(query: str, variables: dict, token: str) -> dict:
    """Send a GraphQL query to GitHub and return the `data` payload.

    Raises on HTTP errors or GraphQL-level errors so failures are loud
    instead of silently producing an empty chart.
    """
    headers = {"Authorization": f"bearer {token}"}
    response = requests.post(
        GITHUB_API_URL,
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if "errors" in payload:
        raise RuntimeError(f"GitHub GraphQL error: {payload['errors']}")
    return payload["data"]


def fetch_user_stats(username: str, token: str) -> dict:
    """Fetch contribution calendar + top repositories (with languages) in one call."""
    one_year_ago = (datetime.now(timezone.utc) - timedelta(days=365)).isoformat()

    query = """
    query($login: String!, $from: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from) {
          contributionCalendar {
            totalContributions
            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                      orderBy: {field: UPDATED_AT, direction: DESC}) {
          nodes {
            name
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges {
                size
                node { name }
              }
            }
          }
        }
      }
    }
    """
    variables = {"login": username, "from": one_year_ago}
    data = run_graphql_query(query, variables, token)
    return data["user"]


def compute_current_streak(weeks: list) -> int:
    """Count consecutive days with contributions, walking backward from today."""
    days = [d for week in weeks for d in week["contributionDays"]]
    days.sort(key=lambda d: d["date"])

    streak = 0
    for day in reversed(days):
        if day["contributionCount"] > 0:
            streak += 1
        else:
            break
    return streak


def aggregate_languages(repositories: list) -> dict:
    """Sum bytes-of-code per language across all owned repos (real, not cached)."""
    totals = {}
    for repo in repositories:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
    return dict(sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:8])


def plot_stats(total_contributions: int, streak: int, languages: dict, output_path: str):
    """Render a two-panel figure: language breakdown (left) + summary numbers (right)."""
    background = "#0d1117"  # GitHub dark background
    panel = "#161b22"
    foreground = "#f0f6fc"
    muted = "#8b949e"
    fig, (ax_lang, ax_summary) = plt.subplots(
        1, 2, figsize=(8.5, 3.2), gridspec_kw={"width_ratios": [1.25, 1]},
        facecolor=background,
    )
    for axis in (ax_lang, ax_summary):
        axis.set_facecolor(panel)

    # --- Panel 1: language pie chart ---
    if languages:
        ax_lang.pie(
            languages.values(),
            labels=languages.keys(),
            autopct="%1.0f%%",
            startangle=90,
            textprops={"fontsize": 8, "color": foreground},
            wedgeprops={"linewidth": 1, "edgecolor": background},
        )
        ax_lang.set_title("Most Used Languages", color=foreground, fontsize=11, pad=10)
    else:
        ax_lang.text(0.5, 0.5, "No language data", ha="center", va="center")
        ax_lang.axis("off")

    # --- Panel 2: key numbers as text ---
    ax_summary.axis("off")
    ax_summary.text(0.05, 0.8, "GitHub Stats", fontsize=15, fontweight="bold", color=foreground)
    ax_summary.text(0.05, 0.55, f"Total contributions (1y): {total_contributions}", fontsize=10, color=foreground)
    ax_summary.text(0.05, 0.35, f"Current streak: {streak} day(s)", fontsize=10, color=foreground)
    ax_summary.text(
        0.05, 0.05,
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        fontsize=7, color=muted,
    )

    fig.tight_layout(pad=1.1)
    fig.savefig(output_path, dpi=140, facecolor=background)
    print(f"Saved chart to {output_path}")


def main():
    username = os.environ.get("GITHUB_USERNAME", "a7mds2r")
    token = os.environ.get("GH_TOKEN")
    output_path = os.environ.get("OUTPUT_PATH", "assets/github_stats.png")

    if not token:
        print("ERROR: set the GH_TOKEN environment variable (a PAT with read:user scope).")
        sys.exit(1)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    user_data = fetch_user_stats(username, token)
    calendar = user_data["contributionsCollection"]["contributionCalendar"]
    total_contributions = calendar["totalContributions"]
    streak = compute_current_streak(calendar["weeks"])
    languages = aggregate_languages(user_data["repositories"]["nodes"])

    plot_stats(total_contributions, streak, languages, output_path)


if __name__ == "__main__":
    main()
