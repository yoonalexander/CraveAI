"""Generate an additive hosted import and record its verified receipt."""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import csv
from hashlib import md5
import json
from pathlib import Path

from scripts.import_restaurant_catalog import ADMISSIONS, SNAPSHOT, read_catalog_rows
from scripts.reconcile_restaurant_catalog import csv_rows

LEDGER = ADMISSIONS.with_name("gta-municipal-dispositions.csv")
RESOLVED = {"already_listed", "duplicate_candidate", "inactive_record", "out_of_scope", "dropped_insufficient_evidence"}


def active_digest(rows: list[dict]) -> str:
    return md5("\n".join(sorted(row["id"] for row in rows if row["listed"])).encode()).hexdigest()


def publication_plan(staged: Path) -> dict:
    previous = read_catalog_rows(SNAPSHOT)
    full = read_catalog_rows(SNAPSHOT, staged)
    old = {row["id"]: row for row in previous}
    new = {row["id"]: row for row in full}
    if any(new.get(ident) != row for ident, row in old.items()):
        raise ValueError("An additive batch must preserve every existing catalog row.")
    rows = [new[ident] for ident in sorted(new.keys() - old.keys())]
    if not rows or any(not row["listed"] for row in rows):
        raise ValueError("The staged manifest must contain active additions.")
    before, after = active_digest(previous), active_digest(full)
    payload = base64.b64encode(json.dumps(rows, default=str, separators=(",", ":")).encode()).decode()
    incoming = f"""SELECT * FROM jsonb_to_recordset(convert_from(decode('{payload}', 'base64'), 'UTF8')::jsonb)
    AS r(id text, name text, lat double precision, lng double precision, address text, cuisine text,
         website text, listed boolean, checked_on date, phone text, hours text)"""
    insert = f"""WITH locked AS MATERIALIZED (SELECT pg_advisory_xact_lock(482207106)),
    incoming AS MATERIALIZED ({incoming}), baseline AS MATERIALIZED (
        SELECT md5(string_agg(c.id, chr(10) ORDER BY c.id COLLATE "C") FILTER (WHERE c.listed)) AS digest
        FROM locked CROSS JOIN public.catalog_restaurants c
    ), applied AS (
        INSERT INTO public.catalog_restaurants (id, name, lat, lng, address, cuisine, website, listed, checked_on, phone, hours)
        SELECT i.* FROM incoming i CROSS JOIN baseline b
        WHERE b.digest IN ('{before}', '{after}') AND NOT EXISTS (
            SELECT 1 FROM incoming x JOIN public.catalog_restaurants c USING (id) WHERE NOT c.listed
        ) ON CONFLICT (id) DO NOTHING RETURNING id
    ) SELECT (SELECT digest FROM baseline) AS before_digest, (SELECT count(*) FROM applied) AS inserted"""
    verify = f"""WITH incoming AS ({incoming})
    SELECT (SELECT count(*) FROM incoming i JOIN public.catalog_restaurants c USING (id)
            WHERE row(i.name,i.lat,i.lng,i.address,i.cuisine,i.website,i.listed,i.checked_on,i.phone,i.hours)
            IS NOT DISTINCT FROM row(c.name,c.lat,c.lng,c.address,c.cuisine,c.website,c.listed,c.checked_on,c.phone,c.hours)) AS exact_fields,
           count(*) FILTER (WHERE listed) AS active, count(*) FILTER (WHERE NOT listed) AS retired,
           md5(string_agg(id,chr(10) ORDER BY id COLLATE "C") FILTER (WHERE listed)) AS active_id_digest
    FROM public.catalog_restaurants"""
    return {"count": len(rows), "before": before, "after": after,
            "ids": [row["id"] for row in rows], "insert": insert, "verify": verify}


def apply_dispositions(proposed: dict, accepted: set[str], new_manifest: bytes | None) -> None:
    current = list(csv_rows(LEDGER))
    if len(current) != len(proposed) or {row["candidate_id"] for row in current} != proposed.keys():
        raise ValueError("Candidate IDs differ between the current and staging ledgers.")
    for row in current:
        ident = row["candidate_id"]
        reviewed = proposed[ident]
        if ident in accepted:
            if row["disposition"] not in {"pending", "added"}:
                raise ValueError(f"Unexpected existing disposition for {ident}.")
            row.update(reviewed, disposition="added")
        elif row["disposition"] == "pending" and reviewed["disposition"] in RESOLVED:
            row.update(reviewed)
    ledger_tmp = LEDGER.with_suffix(".tmp")
    with ledger_tmp.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(current[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(current)
    if new_manifest is not None:
        manifest_tmp = ADMISSIONS.with_suffix(".tmp")
        manifest_tmp.write_bytes(new_manifest)
        manifest_tmp.replace(ADMISSIONS)
    ledger_tmp.replace(LEDGER)
    print(dict(Counter(row["disposition"] for row in current)))


def record_publication(staged: Path, staging_ledger: Path, receipt: dict) -> None:
    rows = list(csv_rows(staging_ledger))
    proposed = {row["candidate_id"]: row for row in rows}
    if len(rows) != len(proposed):
        raise ValueError("The staging ledger contains duplicate candidate IDs.")
    accepted = {ident for ident, row in proposed.items() if row["disposition"] == "staged_for_import"}
    staged_content = staged.read_bytes()
    manifest_current = ADMISSIONS.exists() and ADMISSIONS.read_bytes() == staged_content
    if manifest_current:
        catalog = read_catalog_rows(SNAPSHOT)
        expected = active_digest(catalog)
        if accepted - {row["id"] for row in catalog if row["listed"]}:
            raise ValueError("The published manifest is missing staged candidate IDs.")
    else:
        plan = publication_plan(staged)
        expected = plan["after"]
        if accepted != set(plan["ids"]):
            raise ValueError("Staging ledger and admissions manifest disagree.")
    if receipt["exact_fields"] != len(accepted) or receipt["active_id_digest"] != expected:
        raise ValueError("Hosted verification does not match the staged publication.")
    apply_dispositions(proposed, accepted, None if manifest_current else staged_content)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", type=Path, required=True)
    parser.add_argument("--staging-ledger", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if bool(args.staging_ledger) != bool(args.receipt):
        parser.error("Pass both --staging-ledger and --receipt to record a verified publication.")
    if args.receipt:
        record_publication(args.staged, args.staging_ledger, json.loads(args.receipt.read_text(encoding="utf-8")))
    else:
        print(json.dumps(publication_plan(args.staged)))


if __name__ == "__main__":
    main()
