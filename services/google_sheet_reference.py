from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import time
from dataclasses import dataclass
from urllib.request import Request, urlopen


SPREADSHEET_ID = "18PPhNfdfIZtoAJoWvX9IqEAWysZ48swXgWKLFZIpM9Y"
SHEET_GID = "0"
CSV_URL = (
    f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/"
    f"export?format=csv&gid={SHEET_GID}"
)
CACHE_TTL_SECONDS = 180
CLOSED_STATUSES = {"CLOSE", "CLOSED", "DONE", "SELESAI", "COMPLETED"}

TICKET_HEADERS = {
    "TIKET",
    "TICKET",
    "TICKET ID",
    "TIKET ID",
    "INC",
    "NO TIKET",
}
SERVICE_HEADERS = {
    "NO INET",
    "NO INTERNET",
    "NO SERVICE",
    "SERVICE NUMBER",
    "INTERNET NUMBER",
    "INET",
}
STATUS_HEADERS = {
    "STATUS",
    "RESULT",
    "HASIL",
    "STATUS ORDER",
    "STATUS HASIL",
}


@dataclass(frozen=True)
class ReferenceStatus:
    status: str
    source: str = "Google Sheets"


_cache: dict[str, ReferenceStatus] = {}
_cache_time = 0.0
_cache_lock = asyncio.Lock()


def normalize(value: object) -> str:
    text = str(value or "").strip().upper()
    return re.sub(r"\s+", " ", text)


def normalize_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", normalize(value))


def find_column(headers: list[str], aliases: set[str]) -> int | None:
    normalized_aliases = {normalize(alias) for alias in aliases}
    for index, header in enumerate(headers):
        if normalize(header) in normalized_aliases:
            return index
    return None


def download_statuses() -> dict[str, ReferenceStatus]:
    request = Request(CSV_URL, headers={"User-Agent": "Kerja-Bot/1.0"})
    with urlopen(request, timeout=20) as response:
        raw = response.read()

    text = raw.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}

    header_index = 0
    columns: tuple[int | None, int | None, int | None] = (None, None, None)
    for index, row in enumerate(rows[:20]):
        ticket_col = find_column(row, TICKET_HEADERS)
        service_col = find_column(row, SERVICE_HEADERS)
        status_col = find_column(row, STATUS_HEADERS)
        if status_col is not None and (ticket_col is not None or service_col is not None):
            header_index = index
            columns = (ticket_col, service_col, status_col)
            break

    ticket_col, service_col, status_col = columns
    if status_col is None or (ticket_col is None and service_col is None):
        raise ValueError("Kolom tiket/no internet/status Google Sheets tidak ditemukan.")

    result: dict[str, ReferenceStatus] = {}
    for row in rows[header_index + 1 :]:
        status = normalize(row[status_col] if status_col < len(row) else "")
        if not status:
            continue
        reference = ReferenceStatus(status=status)

        if ticket_col is not None and ticket_col < len(row):
            key = normalize_key(row[ticket_col])
            if key:
                result[f"ticket:{key}"] = reference

        if service_col is not None and service_col < len(row):
            key = normalize_key(row[service_col])
            if key:
                result[f"service:{key}"] = reference

    return result


async def get_reference_statuses(force: bool = False) -> dict[str, ReferenceStatus]:
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
