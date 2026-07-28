from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

DEFAULT_SPREADSHEET_ID = "18PPhNfdfIZtoAJoWvX9IqEAWysZ48swXgWKLFZIpM9Y"
DEFAULT_SHEET_GID = "0"
CACHE_TTL_SECONDS = 180
CLOSED_STATUSES = {"CLOSE", "CLOSED", "DONE", "SELESAI", "COMPLETED"}

TICKET_HEADERS = {
    "TIKET", "TICKET", "TICKET ID", "TIKET ID", "INC", "NO TIKET",
    "NO. TIKET", "NOMOR TIKET", "TICKET EXTERNAL", "TIKET EXTERNAL",
    "EXTERNAL TICKET", "INCIDENT", "INCIDENT ID", "NO INCIDENT",
}
INSERA_TICKET_HEADERS = {
    "INSERA TODAY", "TIKET INSERA", "TICKET INSERA", "INSERA",
    "INSERA TICKET", "INSERA TODAY TICKET",
}
SERVICE_HEADERS = {
    "NO INET", "NO INTERNET", "NO SERVICE", "SERVICE NUMBER",
    "INTERNET NUMBER", "INET",
}
STATUS_HEADERS = {"STATUS", "RESULT", "HASIL", "STATUS ORDER", "STATUS HASIL"}
NEW_SN_HEADERS = {
    "SN ONT NEW", "SN ONT BARU", "SN NEW", "NEW SN", "SN BARU",
    "SERIAL NUMBER BARU", "SN ONT NEW ",
}


@dataclass(frozen=True)
class ReferenceStatus:
    status: str
    new_sn: str = ""
    ticket_id: str = ""
    service_number: str = ""
    source: str = "Google Sheets"


_spreadsheet_id = DEFAULT_SPREADSHEET_ID
_sheet_gid = DEFAULT_SHEET_GID
_cache: dict[str, ReferenceStatus] = {}
_cache_time = 0.0
_cache_lock = asyncio.Lock()


def normalize(value: object) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", " ", text)


def normalize_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize(value))


def normalize_ticket(value: object) -> str:
    ticket = normalize(value)
    # Nilai seperti MANUAL bukan nomor tiket. Nomor tiket aktual diprioritaskan
    # dari kolom INSERA TODAY jika tersedia.
    if ticket in {"", "-", "MANUAL", "N/A", "NA", "NONE"}:
        return ""
    return ticket


def current_sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id}/edit?gid={_sheet_gid}"


def current_csv_url() -> str:
    return (
        f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id}/"
        f"export?format=csv&gid={_sheet_gid}"
    )


def parse_sheet_url(url: str) -> tuple[str, str]:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError("Link Google Sheets tidak valid.")
    spreadsheet_id = match.group(1)
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    gid = query.get("gid", [""])[0]
    if not gid and parsed.fragment.startswith("gid="):
        gid = parsed.fragment.split("=", 1)[1]
    return spreadsheet_id, gid or "0"


def _ensure_config_table(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _load_config(database_path: Path) -> tuple[str, str]:
    _ensure_config_table(database_path)
    with sqlite3.connect(database_path) as conn:
        rows = dict(conn.execute("SELECT key, value FROM bot_settings"))
    return (
        rows.get("google_sheet_id", DEFAULT_SPREADSHEET_ID),
        rows.get("google_sheet_gid", DEFAULT_SHEET_GID),
    )


def _save_config(database_path: Path, spreadsheet_id: str, gid: str) -> None:
    _ensure_config_table(database_path)
    with sqlite3.connect(database_path) as conn:
        conn.executemany(
            "INSERT OR REPLACE INTO bot_settings(key, value) VALUES (?, ?)",
            [("google_sheet_id", spreadsheet_id), ("google_sheet_gid", gid)],
        )
        conn.commit()


async def initialize_sheet_config(database_path: Path) -> None:
    global _spreadsheet_id, _sheet_gid
    _spreadsheet_id, _sheet_gid = await asyncio.to_thread(_load_config, database_path)


async def configure_sheet(database_path: Path, url: str) -> tuple[str, str]:
    global _spreadsheet_id, _sheet_gid, _cache, _cache_time
    spreadsheet_id, gid = parse_sheet_url(url)
    old_id, old_gid = _spreadsheet_id, _sheet_gid
    _spreadsheet_id, _sheet_gid = spreadsheet_id, gid
    _cache = {}
    _cache_time = 0.0
    try:
        await get_reference_statuses(force=True, raise_errors=True)
    except Exception:
        _spreadsheet_id, _sheet_gid = old_id, old_gid
        _cache = {}
        _cache_time = 0.0
        raise
    await asyncio.to_thread(_save_config, database_path, spreadsheet_id, gid)
    return spreadsheet_id, gid


def find_column(headers: list[str], aliases: set[str]) -> int | None:
    normalized_aliases = {normalize(alias) for alias in aliases}
    for index, header in enumerate(headers):
        if normalize(header) in normalized_aliases:
            return index
    return None


def cell(row: list[str], column: int | None) -> str:
    if column is None or column >= len(row):
        return ""
    return str(row[column] or "").strip()


def download_statuses() -> dict[str, ReferenceStatus]:
    request = Request(current_csv_url(), headers={"User-Agent": "Kerja-Bot/1.0"})
    with urlopen(request, timeout=20) as response:
        raw = response.read()
    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ValueError("Google Sheets kosong atau tidak dapat dibaca.")

    columns: tuple[int | None, int | None, int | None, int | None, int | None] = (
        None, None, None, None, None
    )
    header_index = 0
    for index, row in enumerate(rows[:20]):
        ticket_col = find_column(row, TICKET_HEADERS)
        insera_ticket_col = find_column(row, INSERA_TICKET_HEADERS)
        service_col = find_column(row, SERVICE_HEADERS)
        status_col = find_column(row, STATUS_HEADERS)
        new_sn_col = find_column(row, NEW_SN_HEADERS)
        if status_col is not None and (
            ticket_col is not None
            or insera_ticket_col is not None
            or service_col is not None
        ):
            header_index = index
            columns = (
                ticket_col,
                insera_ticket_col,
                service_col,
                status_col,
                new_sn_col,
            )
            break

    ticket_col, insera_ticket_col, service_col, status_col, new_sn_col = columns
    if status_col is None or (
        ticket_col is None and insera_ticket_col is None and service_col is None
    ):
        raise ValueError("Kolom tiket/no internet/status Google Sheets tidak ditemukan.")

    result: dict[str, ReferenceStatus] = {}
    for row in rows[header_index + 1:]:
        status = normalize(cell(row, status_col))
        if not status:
            continue

        primary_ticket = normalize_ticket(cell(row, ticket_col))
        insera_ticket = normalize_ticket(cell(row, insera_ticket_col))
        # TIKET dipakai jika benar-benar berisi nomor tiket. Jika kosong/MANUAL,
        # gunakan tiket aktual pada kolom INSERA TODAY.
        ticket_id = primary_ticket or insera_ticket
        service_number = cell(row, service_col)
        new_sn = normalize(cell(row, new_sn_col))

        reference = ReferenceStatus(
            status=status,
            new_sn=new_sn,
            ticket_id=ticket_id,
            service_number=service_number,
        )

        # Simpan kedua nomor tiket sebagai key agar pencocokan tetap berhasil
        # bila database memiliki salah satu di antaranya.
        for candidate in {primary_ticket, insera_ticket, ticket_id}:
            ticket_key = normalize_key(candidate)
            if ticket_key:
                result[f"ticket:{ticket_key}"] = reference

        service_key = normalize_key(service_number)
        if service_key:
            result[f"service:{service_key}"] = reference
    return result


async def get_reference_statuses(
    force: bool = False,
    raise_errors: bool = False,
) -> dict[str, ReferenceStatus]:
    global _cache, _cache_time
    now = time.monotonic()
    if not force and _cache and now - _cache_time < CACHE_TTL_SECONDS:
        return _cache
    async with _cache_lock:
        now = time.monotonic()
        if not force and _cache and now - _cache_time < CACHE_TTL_SECONDS:
            return _cache
        try:
            downloaded = await asyncio.to_thread(download_statuses)
        except Exception:
            logging.exception("Gagal membaca referensi status Google Sheets")
            if raise_errors:
                raise
            return _cache
        _cache = downloaded
        _cache_time = time.monotonic()
        return _cache


def status_for_order(
    statuses: dict[str, ReferenceStatus], ticket_id: str, service_number: str
) -> ReferenceStatus | None:
    ticket_key = normalize_key(ticket_id)
    if ticket_key:
        found = statuses.get(f"ticket:{ticket_key}")
        if found is not None:
            return found
    service_key = normalize_key(service_number)
    if service_key:
        return statuses.get(f"service:{service_key}")
    return None


def is_reference_closed(reference: ReferenceStatus | None) -> bool:
    return reference is not None and normalize(reference.status) in CLOSED_STATUSES
