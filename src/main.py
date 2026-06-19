"""Main entry point for Odoo to PostgreSQL synchronization."""

import argparse
import sys
from datetime import datetime
from typing import Optional

from src.engine.sync_engine import SyncEngine
from src.utils.config_loader import get_config
from src.utils.logging import get_logger, setup_logging
from src.utils.settings import get_settings
from src.utils.validation import validate, print_validation_result, Validator


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Odoo to PostgreSQL Synchronization Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--mode",
        choices=["full", "incremental"],
        help="Sync mode: 'full' for complete sync, 'incremental' for delta sync",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        help="Specific models to sync (default: all models)",
    )
    parser.add_argument(
        "--config",
        help="Path to models.yaml configuration file",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    parser.add_argument(
        "--log-file",
        help="Log file path",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration without syncing",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show sync status for all models",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset sync state for specified models (use with --models)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit records per model for quick validation (e.g., 1000). Runs validation then exits.",
    )

    return parser.parse_args()


def run_validation() -> int:
    """
    Run comprehensive validation and print results.
    
    Returns:
        Exit code (0 for success, 1 for validation failures).
    """
    logger = get_logger("validation")
    
    try:
        result = validate()
        print_validation_result(result)
        
        if not result.is_valid:
            logger.error("Validation failed", error_count=len(result.errors))
            return 1
        
        if result.warnings:
            logger.warning("Validation passed with warnings", warning_count=len(result.warnings))
        else:
            logger.info("Validation passed")
        
        return 0
        
    except Exception as e:
        logger.error("Validation error", error=str(e))
        print(f"\n✗ Validation error: {e}")
        print("  → Check your configuration and try again\n")
        return 1


def run_sync(
    mode: str,
    model_names: Optional[list[str]] = None,
    config_path: Optional[str] = None,
    validate_only: bool = False,
    record_limit: Optional[int] = None,
) -> int:
    """
    Run the synchronization process.

    Args:
        mode: Sync mode ('full' or 'incremental').
        model_names: Optional list of specific models to sync.
        config_path: Optional path to configuration file.
        validate_only: If True, only validate configuration.
        record_limit: If set, limit records per model for quick validation.

    Returns:
        Exit code (0 for success, 1 for failure).
    """
    logger = get_logger("main")
    settings = get_settings()
    
    if record_limit:
        print(f"[DEBUG] run_sync called: record_limit={record_limit}")
        print(f"\n🔍 QUICK VALIDATION MODE: {record_limit} records per model\n")

    try:
        # Load configuration - PASS model_names to prevent loading ALL models
        # This is CRITICAL for performance - without this, ALL models get field discovery
        config = get_config(config_path, model_names=model_names)

        # Determine sync mode
        full_sync = mode == "full"

        # Initialize sync engine with selected models
        print("\n" + "=" * 60)
        print("SYNCHRONIZATION")
        print("=" * 60)
        print(f"Mode: {mode}")
        print(f"Models: {', '.join(model_names) if model_names else 'ALL'}")
        print("=" * 60)
        
        engine = SyncEngine()
        engine.initialize(model_names=model_names)

        # Run validation if requested
        if validate_only:
            logger.info("Validating configuration...")
            errors = engine.validate_configuration()
            if errors:
                logger.error("Configuration validation failed", errors=errors)
                for error in errors:
                    print(f"  - {error}")
                return 1
            logger.info("Configuration is valid")
            return 0

        # Run sync
        logger.info(
            "Starting synchronization",
            mode=mode,
            full_sync=full_sync,
            models=model_names or "all",
        )

        results = engine.sync_all(full_sync=full_sync, model_names=model_names, record_limit=record_limit)

        # Report results
        total_synced = 0
        total_inserted = 0
        total_updated = 0
        failures = []

        for result in results:
            total_synced += result.records_synced
            total_inserted += result.records_inserted
            total_updated += result.records_updated

            if result.success:
                logger.info(
                    f"✓ {result.model_name}: {result.records_synced} records "
                    f"(+{result.records_inserted}, ~{result.records_updated}) "
                    f"in {result.duration_seconds:.2f}s"
                )
            else:
                failures.append(result)
                logger.error(
                    f"✗ {result.model_name}: {len(result.errors)} errors",
                    errors=result.errors,
                )

        # Summary
        print("\n" + "=" * 60)
        print("SYNCHRONIZATION SUMMARY")
        print("=" * 60)
        print(f"Mode: {mode}")
        print(f"Total records synced: {total_synced}")
        print(f"  Inserted: {total_inserted}")
        print(f"  Updated: {total_updated}")
        print(f"Success rate: {len(results) - len(failures)}/{len(results)}")
        
        if failures:
            print("\nFailures:")
            for f in failures:
                print(f"  - {f.model_name}: {', '.join(f.errors)}")
        
        # Print detailed error summary from error reporter
        error_reporter = engine.get_error_reporter()
        if error_reporter.has_errors():
            print("\n" + "=" * 60)
            print("DETAILED ERROR ANALYSIS")
            print("=" * 60)
            # This will print the comprehensive error report
            error_reporter.print_summary()

        print("=" * 60)
        return 0 if not failures else 1

    except Exception as e:
        logger.exception("Synchronization failed")
        print(f"\nError: {e}")
        return 1


def show_status(model_names: Optional[list[str]] = None) -> int:
    """
    Show sync status for models.

    Args:
        model_names: Optional list of specific models to show status for.

    Returns:
        Exit code.
    """
    logger = get_logger("status")

    try:
        engine = SyncEngine()
        engine.initialize(model_names=model_names)

        status = engine.get_sync_status()

        print("\n" + "=" * 60)
        print("SYNC STATUS")
        print("=" * 60)
        print(f"Total models configured: {status['total_models']}")
        print(f"Models with sync state: {status['synced_models']}")
        print()

        if status["models"]:
            print(f"{'Model':<30} {'Table':<25} {'Status':<12} {'Records':<10} {'Last Sync'}")
            print("-" * 100)
            for state in status["models"]:
                last_sync = state.get("last_sync_date")
                last_sync_str = last_sync.strftime("%Y-%m-%d %H:%M") if last_sync else "Never"
                print(
                    f"{state['model_name']:<30} {state['table_name']:<25} "
                    f"{state['status']:<12} {state['record_count']:<10} {last_sync_str}"
                )
        else:
            print("No sync history found. Run a sync to populate status.")

        print("=" * 60)
        return 0

    except Exception as e:
        logger.exception("Failed to get status")
        print(f"\nError: {e}")
        return 1


def reset_sync_state(model_names: list[str]) -> int:
    """
    Reset sync state for specified models.

    Args:
        model_names: List of model names to reset.

    Returns:
        Exit code.
    """
    logger = get_logger("reset")

    try:
        from src.state.state_manager import StateManager
        from src.clients.postgres_client import PostgresClient

        pg_client = PostgresClient()
        state_manager = StateManager(pg_client)
        state_manager.initialize()

        for model_name in model_names:
            state_manager.reset_model_state(model_name)
            print(f"Reset sync state for: {model_name}")

        pg_client.close()
        return 0

    except Exception as e:
        logger.exception("Failed to reset state")
        print(f"\nError: {e}")
        return 1


if __name__ == "__main__":
    args = parse_args()

    # Setup logging
    setup_logging(
        log_level=args.log_level,
        log_file=args.log_file,
    )

    logger = get_logger("main")

    # Handle validation command (uses new validation module)
    if args.validate:
        sys.exit(run_validation())

    # Handle status command
    if args.status:
        sys.exit(show_status())

    # Handle reset command
    if args.reset:
        if not args.models:
            print("Error: --reset requires --models to be specified")
            sys.exit(1)
        sys.exit(reset_sync_state(args.models))

    # Get sync mode
    settings = get_settings()
    mode = args.mode or settings.sync.mode

    # Run sync
    exit_code = run_sync(
        mode=mode,
        model_names=args.models,
        config_path=args.config,
        validate_only=args.validate,
        record_limit=args.limit,
    )

    sys.exit(exit_code)