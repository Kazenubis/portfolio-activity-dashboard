"""
Portfolio Activity Dashboard — a "GitHub repo activity dashboard" backlog
item pointed at my own growing 100-repo portfolio (github.com/Kazenubis).
Pulls each repo's weekly commit-activity stats from the GitHub API and
charts the combined weekly total across every repo a username owns.

Same live-API-with-offline-fallback pattern as the Anime News Aggregator
and Stock Trend Visualizer: this sandbox has no outbound network access,
so the fallback path (representative sample data shaped like my actual
batch-of-10 push cadence) is what genuinely runs here — see
tests/README for how that's verified deterministically.
"""

import argparse

import requests

GITHUB_API = "https://api.github.com"
DEFAULT_USERNAME = "Kazenubis"
DEFAULT_WEEKS = 12

# Representative offline sample: commit bursts every ~3 weeks (pushing a
# finished batch of 10 repos), quiet weeks in between while building the
# next batch — the actual shape this portfolio's activity has taken.
OFFLINE_WEEKLY_COMMITS = [
    2, 1, 0, 14, 3, 1, 0, 16, 2, 0, 1, 15,
]


def fetch_user_repos(username, per_page=100, timeout=5):
    """Returns a list of repo full names ('owner/repo') for a user's
    public, non-fork repos. Raises on any network/HTTP failure — no
    internal try/except, same convention as the other API-integration
    projects in this portfolio."""
    response = requests.get(
        f"{GITHUB_API}/users/{username}/repos",
        params={"per_page": per_page, "type": "owner"},
        timeout=timeout,
    )
    response.raise_for_status()
    repos = response.json()
    return [repo["full_name"] for repo in repos if not repo.get("fork")]


def fetch_weekly_commit_activity(full_name, timeout=5):
    """Returns a list of the last 52 weeks' commit counts for one repo,
    via GitHub's per-repo commit-activity stats endpoint."""
    response = requests.get(
        f"{GITHUB_API}/repos/{full_name}/stats/commit_activity", timeout=timeout
    )
    response.raise_for_status()
    weeks = response.json()
    return [week["total"] for week in weeks]


def aggregate_weekly_activity(per_repo_weekly):
    """Sums several repos' week-aligned commit-count lists into one
    combined weekly total. Repos with shorter histories (fewer weeks of
    data) are treated as zero for the missing earlier weeks."""
    if not per_repo_weekly:
        return []
    max_len = max(len(weeks) for weeks in per_repo_weekly)
    totals = [0] * max_len
    for weeks in per_repo_weekly:
        # Right-align: index -1 is always "this week" across repos of
        # different ages.
        offset = max_len - len(weeks)
        for i, count in enumerate(weeks):
            totals[offset + i] += count
    return totals


def get_activity(username=DEFAULT_USERNAME, weeks=DEFAULT_WEEKS, timeout=5):
    """Tries the live GitHub API; falls back to representative offline
    sample data on any failure. Returns (weekly_totals, source_label)."""
    try:
        repo_names = fetch_user_repos(username, timeout=timeout)
        per_repo = [fetch_weekly_commit_activity(name, timeout=timeout) for name in repo_names]
        totals = aggregate_weekly_activity(per_repo)
        return totals[-weeks:], "live"
    except Exception:
        return OFFLINE_WEEKLY_COMMITS[-weeks:], "offline sample data"


def total_commits(weekly_totals):
    return sum(weekly_totals)


def most_active_week(weekly_totals):
    """Returns (index, count) of the highest-activity week, or (None, 0)
    for an empty list. Index is 0 = oldest week in the given window."""
    if not weekly_totals:
        return None, 0
    best_index = max(range(len(weekly_totals)), key=lambda i: weekly_totals[i])
    return best_index, weekly_totals[best_index]


def current_quiet_streak(weekly_totals):
    """Consecutive zero-commit weeks counting back from the most recent
    week — a simple 'how long since the last push' signal."""
    streak = 0
    for count in reversed(weekly_totals):
        if count == 0:
            streak += 1
        else:
            break
    return streak


def plot_activity(weekly_totals, output_path, username, source_label):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 4))
    weeks = list(range(1, len(weekly_totals) + 1))
    ax.bar(weeks, weekly_totals, color="#6e40c9")
    ax.set_title(f"{username}'s weekly commit activity ({source_label})")
    ax.set_xlabel("Week (oldest -> most recent)")
    ax.set_ylabel("Commits")
    ax.set_xticks(weeks)
    ax.grid(alpha=0.3, axis="y")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Portfolio Activity Dashboard")
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--weeks", type=int, default=DEFAULT_WEEKS)
    parser.add_argument("--chart", metavar="PATH", help="Save a bar chart to PATH")
    args = parser.parse_args()

    weekly_totals, source = get_activity(args.username, args.weeks)
    print(f"Source: {source}")
    print(f"Total commits (last {len(weekly_totals)} weeks): {total_commits(weekly_totals)}")
    idx, count = most_active_week(weekly_totals)
    if idx is not None:
        print(f"Most active week: week {idx + 1} ({count} commits)")
    quiet = current_quiet_streak(weekly_totals)
    if quiet:
        print(f"Current quiet streak: {quiet} week(s) with no commits")

    if args.chart:
        plot_activity(weekly_totals, args.chart, args.username, source)
        print(f"Saved chart to {args.chart}")


if __name__ == "__main__":
    main()
