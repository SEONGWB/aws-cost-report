"""비용 수집 배치 (주기적으로 실행: python -m app.jobs.collect).

    python -m app.jobs.collect                 # 최근 COLLECT_DAYS일 (기본 3)
    python -m app.jobs.collect --days 30       # 최근 30일
    python -m app.jobs.collect --start 2026-10-01 --end 2026-11-01   # [start, end)
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from app.application import Application

log = logging.getLogger("app.jobs.collect")


class CollectJob:
    def __init__(self, application: Application) -> None:
        self._app = application

    def run(self, argv: list[str] | None = None) -> int:
        args = self._parse(argv)
        repo = self._app.repository
        repo.open()
        try:
            if args.start:
                result = self._app.service.collect(args.start, args.end)
            else:
                result = self._app.service.collect_recent(args.days or self._app.settings.collect_days)
            print(result.model_dump_json())
            return 0
        except Exception:
            log.exception("수집 실패")
            return 1
        finally:
            repo.close()

    @staticmethod
    def _parse(argv: list[str] | None) -> argparse.Namespace:
        parser = argparse.ArgumentParser(description="AWS 비용 수집")
        parser.add_argument("--days", type=int, help="어제까지 최근 N일")
        parser.add_argument("--start", type=date.fromisoformat, help="YYYY-MM-DD (포함)")
        parser.add_argument("--end", type=date.fromisoformat, help="YYYY-MM-DD (미포함)")
        args = parser.parse_args(argv)
        if bool(args.start) != bool(args.end):
            parser.error("--start 와 --end 는 함께 지정해야 합니다")
        return args


def main() -> None:
    sys.exit(CollectJob(Application()).run())


if __name__ == "__main__":
    main()
