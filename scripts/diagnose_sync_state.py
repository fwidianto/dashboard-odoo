#!/usr/bin/env python3
"""
Diagnostic script to verify sync_state table and persistence.
Run this BEFORE and AFTER a sync to understand what's happening.
"""

import sys
sys.path.insert(0, '/workspace/project/dashboard-odoo')

from src.clients.postgres_client import PostgresClient
from src.state.state_manager import StateManager
from datetime import datetime


def main():
    print("=" * 60)
    print("SYNC STATE DIAGNOSTIC")
    print("=" * 60)
    
    # Connect to database
    pg = PostgresClient()
    state_mgr = StateManager(pg)
    
    # 1. Show table structure
    print("\n1. SYNC_STATE TABLE STRUCTURE:")
    print("-" * 40)
    try:
        result = pg.engine.execute("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_name = 'sync_state'
            ORDER BY ordinal_position
        """)
        for row in result:
            print(f"  {row[0]:20} {row[1]:15} nullable={row[2]}")
    except Exception as e:
        print(f"  Error getting schema: {e}")
    
    # 2. Show ALL rows in sync_state
    print("\n2. ALL ROWS IN SYNC_STATE:")
    print("-" * 40)
    try:
        result = pg.engine.execute("SELECT * FROM sync_state ORDER BY model_name")
        rows = result.fetchall()
        if not rows:
            print("  (empty table)")
        else:
            for row in rows:
                print(f"  model_name: {row[1]}")
                print(f"    table_name: {row[2]}")
                print(f"    last_sync_date: {row[3]}")
                print(f"    last_sync_id: {row[4]}")
                print(f"    record_count: {row[5]}")
                print(f"    status: {row[6]}")
                print(f"    created_at: {row[7]}")
                print(f"    updated_at: {row[8]}")
                print()
    except Exception as e:
        print(f"  Error getting rows: {e}")
    
    # 3. Check specific model
    model_to_check = "account.move.line"
    print(f"\n3. CHECKING MODEL: {model_to_check}")
    print("-" * 40)
    
    state = pg.get_sync_state(model_to_check)
    if state:
        print(f"  Found: YES")
        print(f"  last_sync_date: {state['last_sync_date']}")
        print(f"  last_sync_id: {state['last_sync_id']}")
        print(f"  status: {state['status']}")
        print(f"  record_count: {state['record_count']}")
    else:
        print(f"  Found: NO (no row exists for this model)")
    
    # 4. Test manual save
    print(f"\n4. TEST MANUAL SAVE:")
    print("-" * 40)
    test_date = datetime(2026, 6, 18, 14, 0, 0)
    print(f"  Saving test date: {test_date}")
    
    pg.update_sync_state(
        model_name="account.move.line",
        table_name="account_move_line",
        last_sync_date=test_date,
        record_count=100,
        status="completed",
    )
    
    # Verify
    state = pg.get_sync_state("account.move.line")
    if state:
        print(f"  Verified last_sync_date: {state['last_sync_date']}")
        print(f"  Type: {type(state['last_sync_date'])}")
    else:
        print("  ERROR: State not found after save!")
    
    # 5. Test StateManager
    print(f"\n5. TESTING STATE MANAGER:")
    print("-" * 40)
    last_sync = state_mgr.get_last_sync_date("account.move.line")
    print(f"  get_last_sync_date returned: {last_sync}")
    print(f"  Type: {type(last_sync)}")
    
    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
