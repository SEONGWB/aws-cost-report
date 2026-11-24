from __future__ import annotations

from datetime import date

import pytest

from app.jobs.collect import CollectJob


def test_collect_range(application, capsys):
    code = CollectJob(application).run(["--start", "2026-11-01", "--end", "2026-11-04"])
    assert code == 0
    assert '"rows":24' in capsys.readouterr().out  # 3일 x 8서비스
    assert application.repository.latest_date() == date(2026, 11, 3)


def test_collect_recent_default(application):
    assert CollectJob(application).run([]) == 0
    assert application.repository.latest_date() is not None


def test_collect_requires_both_dates(application):
    with pytest.raises(SystemExit):
        CollectJob(application).run(["--start", "2026-11-01"])


def test_collect_failure_returns_1(application, monkeypatch):
    def boom(*_):
        raise RuntimeError("AWS down")

    monkeypatch.setattr(application.client, "fetch_daily", boom)
    assert CollectJob(application).run(["--days", "1"]) == 1
