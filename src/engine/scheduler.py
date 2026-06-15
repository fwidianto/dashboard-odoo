"""Scheduled synchronization runner using APScheduler."""

import signal
import sys
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.engine.sync_engine import SyncEngine
from src.utils.config_loader import get_config
from src.utils.logging import get_logger, setup_logging
from src.utils.settings import get_settings


class SyncScheduler:
    """
    Scheduler for automated synchronization runs.

    Uses APScheduler to run sync jobs at configurable intervals.
    """

    def __init__(
        self,
        full_sync_hour: int = 2,
        full_sync_minute: int = 0,
        incremental_interval_minutes: int = 15,
    ):
        """
        Initialize the scheduler.

        Args:
            full_sync_hour: Hour for daily full sync (0-23).
            full_sync_minute: Minute for daily full sync (0-59).
            incremental_interval_minutes: Interval for incremental syncs.
        """
        self._logger = get_logger("scheduler")
        self._scheduler = BackgroundScheduler()
        self._engine: Optional[SyncEngine] = None
        self._is_running = False

        # Store configuration
        self._full_sync_hour = full_sync_hour
        self._full_sync_minute = full_sync_minute
        self._incremental_interval = incremental_interval_minutes

    def _get_engine(self) -> SyncEngine:
        """Get or create sync engine instance."""
        if self._engine is None:
            self._engine = SyncEngine()
            self._engine.initialize()
        return self._engine

    def _run_incremental_sync(self) -> None:
        """Run incremental sync for all models."""
        self._logger.info("Starting scheduled incremental sync")
        try:
            engine = self._get_engine()
            results = engine.sync_all(full_sync=False)

            successful = sum(1 for r in results if r.success)
            self._logger.info(
                "Incremental sync completed",
                total=len(results),
                successful=successful,
            )
        except Exception as e:
            self._logger.error("Incremental sync failed", error=str(e))

    def _run_full_sync(self) -> None:
        """Run full sync for all models."""
        self._logger.info("Starting scheduled full sync")
        try:
            engine = self._get_engine()
            results = engine.sync_all(full_sync=True)

            successful = sum(1 for r in results if r.success)
            self._logger.info(
                "Full sync completed",
                total=len(results),
                successful=successful,
            )
        except Exception as e:
            self._logger.error("Full sync failed", error=str(e))

    def start(self, run_immediately: bool = False) -> None:
        """
        Start the scheduler.

        Args:
            run_immediately: If True, run a sync immediately before scheduling.
        """
        if self._is_running:
            self._logger.warning("Scheduler is already running")
            return

        self._logger.info(
            "Starting scheduler",
            incremental_interval=self._incremental_interval,
            full_sync_time=f"{self._full_sync_hour:02d}:{self._full_sync_minute:02d}",
        )

        # Schedule incremental sync
        self._scheduler.add_job(
            self._run_incremental_sync,
            trigger=IntervalTrigger(minutes=self._incremental_interval),
            id="incremental_sync",
            name="Incremental Sync",
            replace_existing=True,
        )

        # Schedule daily full sync
        self._scheduler.add_job(
            self._run_full_sync,
            trigger="cron",
            hour=self._full_sync_hour,
            minute=self._full_sync_minute,
            id="full_sync",
            name="Daily Full Sync",
            replace_existing=True,
        )

        # Run immediately if requested
        if run_immediately:
            self._run_incremental_sync()

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Start scheduler
        self._scheduler.start()
        self._is_running = True

        self._logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler gracefully."""
        if not self._is_running:
            return

        self._logger.info("Stopping scheduler")
        self._scheduler.shutdown(wait=True)
        self._is_running = False

        if self._engine:
            self._engine.close()
            self._engine = None

        self._logger.info("Scheduler stopped")

    def _signal_handler(self, signum, frame) -> None:
        """Handle shutdown signals."""
        self._logger.info("Received shutdown signal", signal=signum)
        self.stop()
        sys.exit(0)

    def run_once(self, full_sync: bool = False) -> None:
        """
        Run a single sync (useful for manual triggers).

        Args:
            full_sync: If True, run full sync; otherwise incremental.
        """
        self._logger.info("Running single sync", full_sync=full_sync)
        try:
            engine = self._get_engine()
            results = engine.sync_all(full_sync=full_sync)

            successful = sum(1 for r in results if r.success)
            self._logger.info(
                "Single sync completed",
                total=len(results),
                successful=successful,
            )
        except Exception as e:
            self._logger.error("Single sync failed", error=str(e))
            raise

    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._is_running

    def get_next_run_times(self, count: int = 5) -> list[datetime]:
        """
        Get next scheduled run times.

        Args:
            count: Number of upcoming runs to return.

        Returns:
            List of datetime objects for next runs.
        """
        jobs = self._scheduler.get_jobs()
        next_runs = []
        
        for job in jobs:
            if hasattr(job, "next_run_time") and job.next_run_time:
                next_runs.append((job.name, job.next_run_time))
        
        # Sort by datetime and return
        next_runs.sort(key=lambda x: x[1])
        return [run[1] for run in next_runs[:count]]


def run_scheduler(
    interval_minutes: Optional[int] = None,
    full_sync_hour: int = 2,
    full_sync_minute: int = 0,
    run_immediately: bool = False,
) -> None:
    """
    Run the scheduler.

    Args:
        interval_minutes: Incremental sync interval (uses settings if None).
        full_sync_hour: Hour for daily full sync.
        full_sync_minute: Minute for daily full sync.
        run_immediately: Run sync immediately before scheduling.
    """
    settings = get_settings()
    interval = interval_minutes or settings.sync.schedule_interval_minutes

    scheduler = SyncScheduler(
        full_sync_hour=full_sync_hour,
        full_sync_minute=full_sync_minute,
        incremental_interval_minutes=interval,
    )

    scheduler.start(run_immediately=run_immediately)

    # Keep main thread alive
    try:
        while scheduler.is_running:
            import time
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Odoo Sync Scheduler")
    parser.add_argument(
        "--interval",
        type=int,
        help="Incremental sync interval in minutes",
    )
    parser.add_argument(
        "--full-sync-hour",
        type=int,
        default=2,
        help="Hour for daily full sync (0-23)",
    )
    parser.add_argument(
        "--full-sync-minute",
        type=int,
        default=0,
        help="Minute for daily full sync (0-59)",
    )
    parser.add_argument(
        "--run-immediately",
        action="store_true",
        help="Run sync immediately before scheduling",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(log_level=args.log_level)

    run_scheduler(
        interval_minutes=args.interval,
        full_sync_hour=args.full_sync_hour,
        full_sync_minute=args.full_sync_minute,
        run_immediately=args.run_immediately,
    )