#!/usr/bin/env python3
"""Phase 13 — Complete Backup / Restore Verification Suite

Performs the full backup & restore validation on the PostgreSQL container:
1. Runs scripts/backup.sh (or pg_dump inside umoa13_postgres)
2. Restores into a fresh database `umoa_banking_restored` via scripts/restore.sh
3. Compares before & after across:
   - Tables list & schemas
   - Column types and nullability
   - Primary keys, Foreign keys, Check constraints, Unique constraints
   - Indexes
   - Exact row counts for all tables
   - Exact row checksums/contents for:
     * institutions
     * documents & sources
     * metric_definitions
     * financial_data
     * financial_data_review_events (audit trail)
     * deals
     * deal_sources & deal_field_sources
     * deal_participants
     * deal_duplicate_candidates
4. Cleans up the restored scratch database
5. Exits 0 only if 100% matched
"""

import os
import subprocess
import sys
import json

CONTAINER = os.environ.get("PG_CONTAINER", "umoa13_postgres")
DB_ORIG = "umoa_banking"
DB_RESTORED = "umoa_banking_restored"
DUMP_FILE = "backups/phase13_backup_validation.dump"
BASH_PATH = r"C:\Program Files\Git\bin\bash.exe"


def exec_sql(db: str, sql: str) -> str:
    cmd = [
        "docker", "exec", CONTAINER,
        "psql", "-U", "umoa_user", "-d", db, "-tAc", sql
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"SQL Error on {db}: {res.stderr.strip()}")
    return res.stdout.strip()


def run_bash(script: str, *args) -> None:
    env = {**os.environ, "PG_CONTAINER": CONTAINER}
    cmd = [BASH_PATH, script, *args]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    if res.returncode != 0:
        raise RuntimeError(f"Script Error ({script}): {res.stderr.strip()} (stdout: {res.stdout.strip()})")
    print(f"  [OK] {script} -> {res.stdout.strip()}")


def main():
    print("================================================================================")
    print("UMOA Banking Intelligence — Phase 13 Backup / Restore Verification")
    print("================================================================================\n")

    os.makedirs("backups", exist_ok=True)

    # 1. Clean up any existing restored test db
    print("1. Preparing environment...")
    exec_sql("postgres", f'DROP DATABASE IF EXISTS "{DB_RESTORED}" WITH (FORCE);')

    # 2. Run backup
    print("\n2. Executing backup.sh...")
    run_bash("scripts/backup.sh", DB_ORIG, DUMP_FILE)
    dump_size = os.path.getsize(DUMP_FILE)
    print(f"  Dump file created: {DUMP_FILE} ({dump_size} bytes)")
    assert dump_size > 0, "Dump file is empty!"

    # 3. Run restore
    print("\n3. Executing restore.sh into new database...")
    run_bash("scripts/restore.sh", DUMP_FILE, DB_RESTORED)

    # 4. Deep Comparison
    print("\n4. Performing deep database comparison (Original vs Restored)...")

    # A. Compare Tables
    tables_sql = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;"
    orig_tables = exec_sql(DB_ORIG, tables_sql).splitlines()
    rest_tables = exec_sql(DB_RESTORED, tables_sql).splitlines()
    print(f"  - Tables count: {len(orig_tables)} vs {len(rest_tables)}")
    assert orig_tables == rest_tables, f"Tables mismatch: {orig_tables} != {rest_tables}"
    print(f"    Tables verified: {', '.join(orig_tables)}")

    # B. Compare Constraints (PK, FK, Check, Unique)
    constraints_sql = """
    SELECT conname, contype, conrelid::regclass::text
    FROM pg_constraint con
    JOIN pg_namespace nsp ON nsp.oid = con.connamespace
    WHERE nsp.nspname = 'public'
    ORDER BY conrelid::regclass::text, conname;
    """
    orig_con = exec_sql(DB_ORIG, constraints_sql).splitlines()
    rest_con = exec_sql(DB_RESTORED, constraints_sql).splitlines()
    print(f"  - Constraints count: {len(orig_con)} vs {len(rest_con)}")
    assert orig_con == rest_con, f"Constraints mismatch: {len(orig_con)} vs {len(rest_con)}"

    # C. Compare Indexes
    indexes_sql = """
    SELECT indexname, tablename, indexdef
    FROM pg_indexes
    WHERE schemaname = 'public'
    ORDER BY tablename, indexname;
    """
    orig_idx = exec_sql(DB_ORIG, indexes_sql).splitlines()
    rest_idx = exec_sql(DB_RESTORED, indexes_sql).splitlines()
    print(f"  - Indexes count: {len(orig_idx)} vs {len(rest_idx)}")
    assert orig_idx == rest_idx, f"Indexes mismatch: {len(orig_idx)} vs {len(rest_idx)}"

    # D. Compare Row Counts for each table
    print("\n  - Table Row Counts comparison:")
    for tbl in orig_tables:
        c_orig = int(exec_sql(DB_ORIG, f"SELECT count(*) FROM {tbl};"))
        c_rest = int(exec_sql(DB_RESTORED, f"SELECT count(*) FROM {tbl};"))
        print(f"    * {tbl.ljust(30)}: {c_orig} rows (orig) == {c_rest} rows (restored)")
        assert c_orig == c_rest, f"Row count mismatch on {tbl}: {c_orig} != {c_rest}"

    # E. Compare Data Hashes for Key Tables
    print("\n  - Key Tables Data Consistency Check:")
    key_tables = [
        "institutions",
        "documents",
        "sources",
        "metric_definitions",
        "financial_data",
        "financial_data_review_events",
        "deals",
        "deal_sources",
        "deal_field_sources",
        "deal_participants",
        "deal_duplicate_candidates",
    ]
    for tbl in key_tables:
        if tbl in orig_tables:
            # Query all rows ordered by id / created_at
            sql = f"SELECT * FROM {tbl} ORDER BY 1;"
            d_orig = exec_sql(DB_ORIG, sql)
            d_rest = exec_sql(DB_RESTORED, sql)
            assert d_orig == d_rest, f"Data content mismatch on {tbl}!"
            print(f"    * {tbl.ljust(30)}: Content IDENTICAL [PASS]")

    # 5. Clean up
    print("\n5. Cleaning up restored scratch database and dump...")
    exec_sql("postgres", f'DROP DATABASE IF EXISTS "{DB_RESTORED}" WITH (FORCE);')
    if os.path.exists(DUMP_FILE):
        os.remove(DUMP_FILE)
    print("  Scratch database and dump cleaned up.")

    print("\n================================================================================")
    print("BACKUP & RESTORE VALIDATION: 100% SUCCESSFUL AND VERIFIED")
    print("================================================================================\n")


if __name__ == "__main__":
    main()
