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

HEADER_ALIASES: dict[str, set[str]] = {
    "ticket": {"TIKET", "TICKET", "TICKET ID", "TIKET ID", "INC", "NO TIKET", "NO. TIKET", "NOMOR TIKET"},
    "insera_ticket": {"INSERA TODAY", "TIKET INSERA", "TICKET INSERA", "INSERA", "INSERA TICKET"},
    "service_number": {"NO INET", "NO INTERNET", "NO SERVICE", "SERVICE NUMBER", "INTERNET NUMBER", "INET"},
    "status": {"STATUS", "RESULT", "HASIL", "STATUS ORDER", "STATUS HASIL"},
    "voip_number": {"NO VOIP", "VOIP", "VOICE", "NO VOICE"},
    "customer_name": {"NAMA PELANGGAN", "CUSTOMER NAME", "NAMA CUSTOMER", "NAMA"},
    "address": {"ALAMAT", "ADDRESS", "ALAMAT PELANGGAN"},
    "customer_phone": {"CP", "NO HP", "NO. HP", "NOMOR HP", "CP / NO HP", "CONTACT PERSON", "PHONE"},
    "package": {"PAKET", "KECEPATAN", "SPEED", "SPEED PAKET", "PAKET INTERNET", "BANDWIDTH", "SPEED BY TACPRO"},
    "old_sn": {"SN ONT LAMA", "SN LAMA", "OLD SN", "SN OLD", "SERIAL NUMBER LAMA"},
    "new_sn": {"SN ONT NEW", "SN ONT BARU", "SN NEW", "NEW SN", "SN BARU", "SERIAL NUMBER BARU"},
    "ont_type": {"TYPE ONT", "TIPE ONT", "MODEL ONT", "MODEL ONT BARU", "TYPE ONT BARU", "TIPE ONT BARU"},
    "sto": {"STO", "KODE STO"},
    "valins_id": {"VALINS ID", "ID VALINS", "VALINS"},
    "config_description": {"KETERANGAN CONFIG", "KETERANGAN KONFIG", "DESKRIPSI CONFIG", "KET CONFIG"},
    "report_description": {"KETERANGAN REPORT/STO", "KETERANGAN REPORT", "KETERANGAN STO", "KET REPORT/STO", "KET REPORT"},
}


@dataclass(frozen=True)
class ReferenceStatus:
    status: str = ""
    new_sn: str = ""
    ticket_id: str = ""
    service_number: str = ""
    voip_number: str = ""
    customer_name: str = ""
    address: str = ""
    customer_phone: str = ""
    package: str = ""
    old_sn: str = ""
    ont_type: str = ""
    sto: str = ""
    valins_id: str = ""
    config_description: str = ""
    report_description: str = ""
    source: str = "Google Sheets"

    def order_fields(self) -> dict[str, str]:
        return {
            "ticket_id": self.ticket_id,
            "service_number": self.service_number,
            "voip_number": self.voip_number,
            "customer_name": self.customer_name,
            "address": self.address,
            "customer_phone": self.customer_phone,
            "old_sn": self.old_sn,
            "new_sn": self.new_sn,
            "ont_type": self.ont_type,
            "sto": self.sto,
            "valins_id": self.valins_id,
            "result": self.status,
            "config_description": self.config_description,
            "report_description": self.report_description,
        }


_spreadsheet_id = DEFAULT_SPREADSHEET_ID
_sheet_gid = DEFAULT_SHEET_GID
_cache: dict[str, ReferenceStatus] = {}
_cache_time = 0.0
_cache_lock = asyncio.Lock()


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().upper())


def normalize_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize(value))


def normalize_ticket(value: object) -> str:
    ticket = normalize(value)
    return "" if ticket in {"", "-", "MANUAL", "N/A", "NA", "NONE"} else ticket


def current_sheet_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id}/edit?gid={_sheet_gid}"


def current_csv_url() -> str:
    return f"https://docs.google.com/spreadsheets/d/{_spreadsheet_id}/export?format=csv&gid={_sheet_gid}"


def parse_sheet_url(url: str) -> tuple[str, str]:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError("Link Google Sheets tidak valid.")
    parsed = urlparse(url)
    gid = parse_qs(parsed.query).get("gid", [""])[0]
    if not gid and parsed.fragment.startswith("gid="):
        gid = parsed.fragment.split("=", 1)[1]
    return match.group(1), gid or "0"


def _ensure_config_table(database_path: Path) -> None:
    with sqlite3.connect(database_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")


def _load_config(database_path: Path) -> tuple[str, str]:
    _ensure_config_table(database_path)
    with sqlite3.connect(database_path) as conn:
        rows = dict(conn.execute("SELECT key, value FROM bot_settings"))
    return rows.get("google_sheet_id", DEFAULT_SPREADSHEET_ID), rows.get("google_sheet_gid", DEFAULT_SHEET_GID)


def _save_config(database_path: Path, spreadsheet_id: str, gid: str) -> None:
    _ensure_config_table(database_path)
    with sqlite3.connect(database_path) as conn:
        conn.executemany("INSERT OR REPLACE INTO bot_settings(key, value) VALUES (?, ?)", [("google_sheet_id", spreadsheet_id), ("google_sheet_gid", gid)])


async def initialize_sheet_config(database_path: Path) -> None:
    global _spreadsheet_id, _sheet_gid
    _spreadsheet_id, _sheet_gid = await asyncio.to_thread(_load_config, database_path)


async def configure_sheet(database_path: Path, url: str) -> tuple[str, str]:
    global _spreadsheet_id, _sheet_gid, _cache, _cache_time
    spreadsheet_id, gid = parse_sheet_url(url)
    old = (_spreadsheet_id, _sheet_gid)
    _spreadsheet_id, _sheet_gid, _cache, _cache_time = spreadsheet_id, gid, {}, 0.0
    try:
        await get_reference_statuses(force=True, raise_errors=True)
    except Exception:
        _spreadsheet_id, _sheet_gid = old
        _cache, _cache_time = {}, 0.0
        raise
    await asyncio.to_thread(_save_config, database_path, spreadsheet_id, gid)
    return spreadsheet_id, gid


def find_column(headers: list[str], aliases: set[str]) -> int | None:
    wanted = {normalize(alias) for alias in aliases}
    return next((i for i, header in enumerate(headers) if normalize(header) in wanted), None)


def cell(row: list[str], column: int | None) -> str:
    return "" if column is None or column >= len(row) else str(row[column] or "").strip()


def download_statuses() -> dict[str, ReferenceStatus]:
    request = Request(current_csv_url(), headers={"User-Agent": "Kerja-Bot/1.0"})
    with urlopen(request, timeout=20) as response:
        rows = list(csv.reader(io.StringIO(response.read().decode("utf-8-sig", errors="replace"))))
    if not rows:
        raise ValueError("Google Sheets kosong atau tidak dapat dibaca.")

    header_index = -1
    columns: dict[str, int | None] = {}
    for index, row in enumerate(rows[:20]):
        candidate = {key: find_column(row, aliases) for key, aliases in HEADER_ALIASES.items()}
        if candidate["service_number"] is not None and candidate["status"] is not None:
            header_index, columns = index, candidate
            break
    if header_index < 0:
        raise ValueError("Kolom INET/NO SERVICE dan STATUS Google Sheets tidak ditemukan.")

    result: dict[str, ReferenceStatus] = {}
    for row in rows[header_index + 1:]:
        service_number = cell(row, columns["service_number"])
        primary_ticket = normalize_ticket(cell(row, columns["ticket"]))
        insera_ticket = normalize_ticket(cell(row, columns["insera_ticket"]))
        ticket_id = primary_ticket or insera_ticket
        if not service_number and not ticket_id:
            continue

        values = {key: cell(row, column) for key, column in columns.items()}
        reference = ReferenceStatus(
            status=normalize(values["status"]), ticket_id=ticket_id,
            service_number=service_number, voip_number=values["voip_number"],
            customer_name=values["customer_name"], address=values["address"],
            customer_phone=values["customer_phone"], package=values["package"],
            old_sn=normalize(values["old_sn"]), new_sn=normalize(values["new_sn"]),
            ont_type=normalize(values["ont_type"]), sto=normalize(values["sto"]),
            valins_id=values["valins_id"], config_description=values["config_description"],
            report_description=values["report_description"],
        )
        for candidate in {primary_ticket, insera_ticket, ticket_id}:
            key = normalize_key(candidate)
            if key:
                result[f"ticket:{key}"] = reference
        key = normalize_key(service_number)
        if key:
            result[f"service:{key}"] = reference
    return result


async def get_reference_statuses(force: bool = False, raise_errors: bool = False) -> dict[str, ReferenceStatus]:
    global _cache, _cache_time
    now = time.monotonic()
    if not force and _cache and now - _cache_time < CACHE_TTL_SECONDS:
        return _cache
    async with _cache_lock:
        if not force and _cache and time.monotonic() - _cache_time < CACHE_TTL_SECONDS:
            return _cache
        try:
            _cache = await asyncio.to_thread(download_statuses)
            _cache_time = time.monotonic()
        except Exception:
            logging.exception("Gagal membaca referensi Google Sheets")
            if raise_errors:
                raise
        return _cache


def status_for_order(statuses: dict[str, ReferenceStatus], ticket_id: str, service_number: str) -> ReferenceStatus | None:
    ticket_key = normalize_key(ticket_id)
    if ticket_key and (found := statuses.get(f"ticket:{ticket_key}")) is not None:
        return found
    service_key = normalize_key(service_number)
    return statuses.get(f"service:{service_key}") if service_key else None


def is_reference_closed(reference: ReferenceStatus | None) -> bool:
    return reference is not None and normalize(reference.status) in CLOSED_STATUSES
