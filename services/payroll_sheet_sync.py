from __future__ import annotations

import csv
import hashlib
import io
import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

DEFAULT_PAYROLL_SPREADSHEET_ID = ""
DEFAULT_PAYROLL_SHEET_GID = "0"
PAYROLL_SOURCE = "Google Sheets - REKON | VALIDASI"

HEADER_ALIASES: dict[str, set[str]] = {
    "nik": {"NIK TEKNISI TACTICAL", "NIK TEKNISI", "NIK", "NIK TACTICAL"},
    "technician_name": {"NAMA TEKNISI TACTICAL", "NAMA TEKNISI", "NAMA TACTICAL"},
    "validasi_tactical": {"VALIDASI TACTICAL"},
    "validasi_parameter": {"VALIDASI PARAMETER"},
    "hss": {"HSS"},
    "batch": {"BATCH"},
    "status_rapel": {"STATUS RAPEL", "STATUS RAPEL"},
    "submission_date": {"SUBMISSION DATE", "TANGGAL SUBMISSION", "SUBMISSION"},
    "task_payment": {"TASK PAYMENT", "TASK PEMBAYARAN", "PAYMENT TASK"},
    "status_payment": {"STATUS PAYMENT", "PAYMENT STATUS"},
    "paid_to": {"PAID TO", "DIBAYAR KE", "PEMBAYARAN KE"},
    "payment_information": {"PAYMENT INFORMATION", "INFORMASI PEMBAYARAN", "KETERANGAN PAYMENT"},
}

FIELD_ORDER = tuple(HEADER_ALIASES)


@dataclass(frozen=True)
class PayrollRecord:
    nik: str
    technician_name: str = ""
    validasi_tactical: str = ""
    validasi_parameter: str = ""
    hss: str = ""
    batch: str = ""
    status_rapel: str = ""
    submission_date: str = ""
    task_payment: str = ""
    status_payment: str = ""
    paid_to: str = ""
    payment_information: str = ""

    def as_dict(self) -> dict[str, str]:
        return {field: getattr(self, field) for field in FIELD_ORDER}


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def normalize_nik(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize(value))


def find_column(headers: list[str], aliases: set[str]) -> int | None:
    wanted = {normalize(alias) for alias in aliases}
    for index, header in enumerate(headers):
        if normalize(header) in wanted:
            return index
    return None


def cell(row: list[str], column: int | None) -> str:
    if column is None or column >= len(row):
        return ""
    return str(row[column] or "").strip()


def parse_sheet_url(url: str) -> tuple[str, str]:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError("Link Google Sheets payroll tidak valid.")
    parsed = urlparse(url)
    gid = parse_qs(parsed.query).get("gid", [""])[0]
    if not gid and parsed.fragment.startswith("gid="):
        gid = parsed.fragment.split("=", 1)[1]
    return match.group(1), gid or DEFAULT_PAYROLL_SHEET_GID


def csv_url(spreadsheet_id: str, gid: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=csv&gid={gid}"


def download_payroll_rows(spreadsheet_id: str, gid: str) -> list[list[str]]:
    request = Request(csv_url(spreadsheet_id, gid), headers={"User-Agent": "Kerja-Bot/1.0"})
    with urlopen(request, timeout=20) as response:
        payload = response.read().decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(payload)))
    if not rows:
        raise ValueError("Google Sheets REKON | VALIDASI kosong atau tidak dapat dibaca.")
    return rows


def parse_payroll_rows(rows: list[list[str]]) -> list[PayrollRecord]:
    header_index = -1
    columns: dict[str, int | None] = {}
    for index, row in enumerate(rows[:30]):
        candidate = {field: find_column(row, aliases) for field, aliases in HEADER_ALIASES.items()}
        if candidate["nik"] is not None:
            header_index, columns = index, candidate
            break
    if header_index < 0:
        raise ValueError("Kolom NIK TEKNISI TACTICAL tidak ditemukan pada REKON | VALIDASI.")

    records: list[PayrollRecord] = []
    for row in rows[header_index + 1:]:
        nik = normalize_nik(cell(row, columns["nik"]))
        if not nik:
            continue
        values = {field: cell(row, columns[field]) for field in FIELD_ORDER}
        records.append(PayrollRecord(**values, nik=nik))
    return records


def row_hash(record: PayrollRecord) -> str:
    payload = "\x1f".join(record.as_dict()[field] for field in FIELD_ORDER)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sync_payroll_records(database_path: Path, records: list[PayrollRecord]) -> tuple[int, int, int]:
    """Mirror payroll rows into SQLite in one transaction.

    This function only writes to the local database. It never writes back to Google Sheets.
    Matching to a registered technician is done by normalized NIK.
    """
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    inserted = updated = unchanged = 0
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        technician_by_nik = {
            normalize_nik(row["nik"]): row["id"]
            for row in conn.execute("SELECT id, nik FROM technicians WHERE nik IS NOT NULL")
            if normalize_nik(row["nik"])
        }
        for record in records:
            digest = row_hash(record)
            technician_id = technician_by_nik.get(record.nik)
            values = record.as_dict()
            existing = conn.execute(
                "SELECT * FROM payroll_records WHERE source_row_hash = ?",
                (digest,),
            ).fetchone()
            if existing:
                unchanged += 1
                continue

            # Same logical source row may change payment/status fields later.
            # Match first on NIK + submission date + batch + task payment; this
            # keeps a changed source row from creating an accidental duplicate.
            existing = conn.execute(
                """
                SELECT id, source_row_hash FROM payroll_records
                WHERE nik = ? AND submission_date = ? AND batch = ? AND task_payment = ?
                ORDER BY id DESC LIMIT 1
                """,
                (record.nik, record.submission_date, record.batch, record.task_payment),
            ).fetchone()

            if existing:
                conn.execute(
                    """
                    UPDATE payroll_records SET
                        technician_id=?, technician_name=?, validasi_tactical=?, validasi_parameter=?,
                        hss=?, batch=?, status_rapel=?, submission_date=?, task_payment=?,
                        status_payment=?, paid_to=?, payment_information=?, source_row_hash=?, synced_at=?
                    WHERE id=?
                    """,
                    (
                        technician_id,
                        values["technician_name"], values["validasi_tactical"], values["validasi_parameter"],
                        values["hss"], values["batch"], values["status_rapel"], values["submission_date"],
                        values["task_payment"], values["status_payment"], values["paid_to"],
                        values["payment_information"], digest, now, existing["id"],
                    ),
                )
                updated += 1
                continue

            conn.execute(
                """
                INSERT INTO payroll_records (
                    technician_id, nik, technician_name, validasi_tactical, validasi_parameter,
                    hss, batch, status_rapel, submission_date, task_payment, status_payment,
                    paid_to, payment_information, source_row_hash, source, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    technician_id, record.nik, values["technician_name"], values["validasi_tactical"],
                    values["validasi_parameter"], values["hss"], values["batch"], values["status_rapel"],
                    values["submission_date"], values["task_payment"], values["status_payment"],
                    values["paid_to"], values["payment_information"], digest, PAYROLL_SOURCE, now,
                ),
            )
            inserted += 1
    return len(records), inserted, updated + unchanged


def sync_payroll_sheet(database_path: Path, spreadsheet_url: str) -> tuple[int, int, int]:
    """Read REKON | VALIDASI and mirror it locally; Google Sheets remains read-only."""
    spreadsheet_id, gid = parse_sheet_url(spreadsheet_url)
    rows = download_payroll_rows(spreadsheet_id, gid)
    records = parse_payroll_rows(rows)
    logging.info("Payroll sheet read-only sync: rows=%s spreadsheet=%s gid=%s", len(records), spreadsheet_id, gid)
    return sync_payroll_records(database_path, records)
