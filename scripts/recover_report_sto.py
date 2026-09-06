#!/usr/bin/env python3
"""Recover historical report STOs from Telegram JSON exports.

Only explicit /STO records are trusted. A service is mapped when all matching
/STO records agree on the same STO. Conflicting services are left untouched.
The script writes report_area_orders rows for every matching
report_group_orders(service_number, period_start) row.

Usage:
  python3 scripts/recover_report_sto.py \
    --db /path/to/bot.sqlite3 \
    --jgr /path/to/result-JGR.json \
    --myr /path/to/result-MYR.json
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

SERVICE_RE = re.compile(r"\b(15\d{10})\b")
STO_RE = re.compile(r"/STO\s*:\s*(JGR|MYR)\b", re.I)


def flatten_text(value):
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(flatten_text(x) for x in value)
    if isinstance(value, dict):
        return str(value.get("text", ""))
    return ""


def load_sto_map(path: Path, expected_sto: str):
    data = json.loads(path.read_text(encoding="utf-8"))
    messages = data.get("messages", []) if isinstance(data, dict) else data
    found = defaultdict(set)
    for msg in messages:
        text = flatten_text(msg.get("text", "")) if isinstance(msg, dict) else ""
        if not text or "/STO" not in text.upper():
            continue
        m = STO_RE.search(text)
        if not m or m.group(1).upper() != expected_sto:
            continue
        # Require the service field near the /STO payload to avoid unrelated
        # phone numbers elsewhere in a message.
        nm = re.search(r"NO\s+SERVICE\s*:\s*(?:[^\d]{0,30})(15\d{10})", text, re.I)
        if not nm:
            continue
        service = nm.group(1)
        found[service].add(expected_sto)
    return found


def table_columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--jgr", type=Path, required=True)
    ap.add_argument("--myr", type=Path, required=True)
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        report_cols = table_columns(conn, "report_group_orders")
        if not report_cols:
            raise SystemExit("report_group_orders table not found")
        if "service_number" not in report_cols or "period_start" not in report_cols:
            raise SystemExit("report_group_orders lacks service_number/period_start")

        jgr = load_sto_map(args.jgr, "JGR")
        myr = load_sto_map(args.myr, "MYR")
        all_map = defaultdict(set)
        for service, values in jgr.items():
            all_map[service].update(values)
        for service, values in myr.items():
            all_map[service].update(values)

        conflicts = {s: sorted(v) for s, v in all_map.items() if len(v) != 1}
        proven = {s: next(iter(v)) for s, v in all_map.items() if len(v) == 1}

        # Keep the existing table if present; otherwise create the minimal
        # schema expected by the dashboard.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS report_area_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_number TEXT NOT NULL,
                period_start TEXT NOT NULL,
                sto_code TEXT NOT NULL,
                area_label TEXT DEFAULT '',
                UNIQUE(service_number, period_start)
            )
        """)
        area_cols = table_columns(conn, "report_area_orders")
        required = {"service_number", "period_start", "sto_code"}
        if not required.issubset(area_cols):
            raise SystemExit(f"report_area_orders missing columns: {sorted(required-area_cols)}")

        rows = conn.execute(
            "SELECT service_number, period_start FROM report_group_orders "
            "WHERE TRIM(COALESCE(service_number,'')) <> ''"
        ).fetchall()

        matched = 0
        inserted = 0
        updated = 0
        unmatched = 0
        for row in rows:
            service = re.sub(r"[^A-Z0-9]", "", str(row["service_number"]).upper())
            sto = proven.get(service)
            if not sto:
                unmatched += 1
                continue
            matched += 1
            params = (service, str(row["period_start"]), sto)
            exists = conn.execute(
                "SELECT id, sto_code FROM report_area_orders "
                "WHERE service_number=? AND period_start=?", params[:2]
            ).fetchone()
            if exists:
                current = str(exists["sto_code"] or "").strip().upper()
                if current and current != sto:
                    # Never overwrite a conflicting existing mapping.
                    conflicts.setdefault(service, sorted({current, sto}))
                    continue
                if current != sto:
                    conn.execute("UPDATE report_area_orders SET sto_code=? WHERE id=?", (sto, exists["id"]))
                    updated += 1
                continue

            conn.execute(
                "INSERT INTO report_area_orders(service_number, period_start, sto_code, area_label) "
                "VALUES(?,?,?,?)",
                (service, str(row["period_start"]), sto, sto),
            )
            inserted += 1

        conn.commit()

        totals = conn.execute(
            "SELECT UPPER(TRIM(sto_code)) sto, COUNT(*) n "
            "FROM report_area_orders GROUP BY UPPER(TRIM(sto_code)) ORDER BY n DESC"
        ).fetchall()
        print(f"JGR explicit services : {len(jgr)}")
        print(f"MYR explicit services : {len(myr)}")
        print(f"Proven unique services: {len(proven)}")
        print(f"Conflicting services  : {len(conflicts)}")
        print(f"Report rows matched   : {matched}")
        print(f"Report rows unmatched : {unmatched}")
        print(f"Inserted mappings      : {inserted}")
        print(f"Updated mappings       : {updated}")
        print("Current report_area_orders:")
        for row in totals:
            print(f"  {row['sto'] or '-'} = {row['n']}")
        if conflicts:
            print("CONFLICTS (left untouched):")
            for service, values in sorted(conflicts.items()):
                print(f"  {service}: {','.join(values)}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
