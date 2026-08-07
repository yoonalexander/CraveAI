from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def count_application_rows(database_path: Path) -> dict[str, int]:
    if not database_path.is_file():
        raise FileNotFoundError(f"Legacy SQLite database not found: {database_path}")

    connection = sqlite3.connect(f"file:{database_path.as_posix()}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]
        return {
            table: int(
                connection.execute(
                    f'SELECT COUNT(*) FROM "{table.replace(chr(34), chr(34) * 2)}"'
                ).fetchone()[0]
            )
            for table in tables
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Abort a Postgres cutover if the legacy SQLite database contains rows."
    )
    parser.add_argument(
        "database",
        nargs="?",
        type=Path,
        default=Path("data/craveai.db"),
        help="Path to the legacy SQLite database (default: data/craveai.db).",
    )
    args = parser.parse_args()

    counts = count_application_rows(args.database.resolve())
    unexpected = {table: count for table, count in counts.items() if count > 0}
    print(f"Legacy SQLite row counts: {counts}")
    if unexpected:
        print(f"Cutover aborted; unexpected legacy rows found: {unexpected}")
        return 1

    print("Legacy SQLite is empty; Postgres cutover may proceed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
