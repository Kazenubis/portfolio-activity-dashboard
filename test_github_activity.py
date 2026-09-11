import sys
import types
import unittest

import github_activity
from github_activity import (
    OFFLINE_WEEKLY_COMMITS,
    aggregate_weekly_activity,
    current_quiet_streak,
    get_activity,
    most_active_week,
    total_commits,
)


class TestAggregation(unittest.TestCase):
    def test_aggregates_equal_length_histories(self):
        result = aggregate_weekly_activity([[1, 2, 3], [4, 5, 6]])
        self.assertEqual(result, [5, 7, 9])

    def test_right_aligns_shorter_histories(self):
        # A newer repo only has 2 weeks of history; it should still line
        # up with the most recent 2 weeks of the older repo's 4.
        result = aggregate_weekly_activity([[1, 2, 3, 4], [10, 20]])
        self.assertEqual(result, [1, 2, 13, 24])

    def test_empty_input_gives_empty_result(self):
        self.assertEqual(aggregate_weekly_activity([]), [])


class TestStats(unittest.TestCase):
    def test_total_commits_sums_the_window(self):
        self.assertEqual(total_commits([1, 2, 3]), 6)

    def test_most_active_week_finds_the_peak(self):
        idx, count = most_active_week([2, 8, 3, 1])
        self.assertEqual((idx, count), (1, 8))

    def test_most_active_week_on_empty_list(self):
        self.assertEqual(most_active_week([]), (None, 0))

    def test_current_quiet_streak_counts_trailing_zeros(self):
        self.assertEqual(current_quiet_streak([5, 3, 0, 0, 0]), 3)

    def test_current_quiet_streak_is_zero_if_most_recent_week_is_active(self):
        self.assertEqual(current_quiet_streak([0, 0, 4]), 0)


class FakeResponse:
    def __init__(self, payload, status_ok=True):
        self._payload = payload
        self._status_ok = status_ok

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self._status_ok:
            raise RuntimeError("simulated HTTP error")


class TestOfflineFallback(unittest.TestCase):
    """Same dual-patch technique used in the Anime News Aggregator: since
    github_activity.py does `import requests` at module load, patching
    sys.modules alone doesn't reach the module's already-bound name — it
    has to be reassigned directly too."""

    def setUp(self):
        self.original_requests = github_activity.requests
        fake_requests = types.ModuleType("requests")
        fake_requests.get = self._raise_connection_error
        sys.modules["requests"] = fake_requests
        github_activity.requests = fake_requests

    def tearDown(self):
        sys.modules["requests"] = self.original_requests
        github_activity.requests = self.original_requests

    @staticmethod
    def _raise_connection_error(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    def test_get_activity_falls_back_to_offline_sample_data(self):
        weekly_totals, source = get_activity(weeks=6)
        self.assertEqual(source, "offline sample data")
        self.assertEqual(weekly_totals, OFFLINE_WEEKLY_COMMITS[-6:])

    def test_offline_sample_reflects_a_batch_push_pattern(self):
        # The whole point of the sample data: a few big spikes (pushing a
        # finished batch of 10) among mostly-quiet weeks, not a flat or
        # uniformly random shape.
        weekly_totals, _source = get_activity(weeks=len(OFFLINE_WEEKLY_COMMITS))
        spikes = [count for count in weekly_totals if count >= 10]
        quiet_weeks = [count for count in weekly_totals if count <= 2]
        self.assertGreaterEqual(len(spikes), 2)
        self.assertGreater(len(quiet_weeks), len(spikes))


class TestLivePath(unittest.TestCase):
    """Verifies the live-path parsing logic against a canned but
    realistically-shaped GitHub API response, independent of the
    fallback tests above."""

    def setUp(self):
        self.original_requests = github_activity.requests
        fake_requests = types.ModuleType("requests")
        fake_requests.get = self._fake_get
        sys.modules["requests"] = fake_requests
        github_activity.requests = fake_requests

    def tearDown(self):
        sys.modules["requests"] = self.original_requests
        github_activity.requests = self.original_requests

    @staticmethod
    def _fake_get(url, timeout=5, **kwargs):
        if url.endswith("/repos"):
            return FakeResponse([
                {"full_name": "Kazenubis/repo-a", "fork": False},
                {"full_name": "Kazenubis/repo-b", "fork": False},
                {"full_name": "Kazenubis/a-fork", "fork": True},
            ])
        if url.endswith("/repo-a/stats/commit_activity"):
            return FakeResponse([{"total": 3}, {"total": 0}])
        if url.endswith("/repo-b/stats/commit_activity"):
            return FakeResponse([{"total": 1}, {"total": 5}])
        raise AssertionError(f"unexpected URL: {url}")

    def test_get_activity_uses_live_data_and_excludes_forks(self):
        weekly_totals, source = get_activity(username="Kazenubis", weeks=2)
        self.assertEqual(source, "live")
        # repo-a: [3, 0], repo-b: [1, 5] -> combined [4, 5]. The fork is
        # never fetched at all (fetch_user_repos filters it out).
        self.assertEqual(weekly_totals, [4, 5])


if __name__ == "__main__":
    unittest.main()
