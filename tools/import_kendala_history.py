from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from services.google_sheet_reference import (
    DEFAULT_SPREADSHEET_ID,
    download_statuses,
    status_for_order,
)

INET_RE = re.compile(r"\b15\d{10,13}\b")
LABEL_PATTERNS = (
    re.compile(r"NO\s*INET\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
    re.compile(r"INET\s*/\s*VOIP\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
    re.compile(r"NO\s*SERVICE\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
)

KENDALA_KEYWORDS = (
    "NOK", "MANJA", "MENOLAK", "TIDAK MAU", "TIDAK BERKENAN",
    "RUKOS", "RUMAH KOSONG", "RNA", "ALAMAT NOK", "LEPAS DC",
    "CABUT", "SALBON", "HISTORY NOK", "CP NOK", "CP NO WA", "KENDALA",
    "RESCHEDULE", "JADWAL", "BESOK", "TIDAK RESPON", "NO RESPON",
    "TIDAK ADA RESPON", "TIDAK BISA DIHUBUNGI", "PUTUS LANGGANAN",
    "PUTUS INTERNET", "LUAR KOTA", "SUDAH DIGANTI", "SUDAH GANTI",
    "ONT OFF", "NO INET DAN SN BEDA",
)

IGNORE_MARKERS = (
    "/STO", "/CONFIG", "/REPORT", "#REQOPENTIKET", "MOBAN ASSIGN LENSA CHAT",
)

HEADERS = [
    "TANGGAL", "INET", "NAMA PELANGGAN", "ALAMAT", "CP", "TIKET",
    "TEKNISI", "STATUS", "RCA", "KETERANGAN", "EVIDEN",
]


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return ""


def extract_inets(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for pattern in LABEL_PATTERNS:
        for match in pattern.findall(text):
            if match not in seen:
                seen.add(match)
                found.append(match)
    if found:
        return found
    for match in INET_RE.findall(text):
        if match not in seen:
            seen.add(match)
            found.append(match)
    return found


def looks_like_kendala(text: str) -> bool:
    upper = " ".join(text.upper().split())
    if not upper:
        return False
    if any(marker in upper for marker in IGNORE_MARKERS):
        return False
    return any(keyword in upper for keyword in KENDALA_KEYWORDS)


def compact_description(text: str, inet: str) -> str:
    lines = [" ".join(line.split()) for line in text.splitlines() if line.strip()]
    cleaned: list[str] = []
    for line in lines:
        upper = line.upper()
        if inet in line and ("NO INET" in upper or "INET / VOIP" in upper or "NO SERVICE" in upper):
            continue
        if upper.startswith("TYPE :") or upper.startswith("NAMA / CP :"):
            continue
        if upper.startswith("ALAMAT :") or upper.startswith("NAMA ODP :"):
            continue
        if upper.startswith("REDAMAN :") or upper.startswith("LINK SCC :"):
            continue
        if upper.startswith("TEKNISI :"):
            continue
        if "KETERANGAN :" in upper:
            line = re.split(r"KETERANGAN\s*:\s*", line, flags=re.IGNORECASE, maxsplit=1)[-1]
        cleaned.append(line)
    return " | ".join(cleaned).strip(" |")[:500]


def classify(description: str) -> tuple[str, str]:
    value = " ".join(description.upper().split())
    done_keywords = ("SUDAH GANTI", "SUDAH DIGANTI", "SELESAI", "DONE", "SUDAH SELESAI")
    if any(keyword in value for keyword in done_keywords):
        return "CLOSE", "DONE"
    if "MENOLAK" in value or "TIDAK MAU" in value or "TIDAK BERKENAN" in value:
        return "UPDATE", "MENOLAK"
    if "RUKOS" in value or "RUMAH KOSONG" in value or "TIDAK ADA PENGHUNI" in value:
        return "UPDATE", "RUKOS"
    if "ALAMAT NOK" in value or "ALAMAT TIDAK" in value or "ALAMAT TIDAK DITEMUKAN" in value:
        return "UPDATE", "ALAMAT NOK"
    if "LEPAS DC" in value:
        return "UPDATE", "LEPAS DC"
    if "CABUT" in value or "PUTUS LANGGANAN" in value or "PUTUS INTERNET" in value:
        return "UPDATE", "CABUT"
    if "2 VOIP" in value or "ONT 2 VOIP" in value or "VOIP ADA 2" in value:
        return "UPDATE", "ONT 2 VOIP"
    if "MANJA" in value or "RESCHEDULE" in value or "JADWAL" in value or "BESOK" in value or "LUAR KOTA" in value:
        return "UPDATE", "MANJA"
    if (
        "RNA" in value or "TIDAK RESPON" in value or "NO RESPON" in value
        or "TIDAK ADA RESPON" in value or "TIDAK BISA DIHUBUNGI" in value
        or "CP NOK" in value or "CP NO WA" in value or "HISTORY NOK" in value
    ):
        return "UPDATE", "RNA"
    if "SALBON" in value:
        return "UPDATE", "SALBON"
    return "UPDATE", "UNSPEC"


def _parse_message_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def scan(export_path: Path, since: datetime | None = None, until: datetime | None = None) -> tuple[dict[str, int], list[dict[str, Any]], Counter[str]]:
    data = json.loads(export_path.read_text(encoding="utf-8"))
    messages = data.get("messages", [])
    latest_by_inet: dict[str, dict[str, Any]] = {}
    messages_in_range = 0
    skipped_done = 0
    total_active_updates = 0

    for message in messages:
        if message.get("type") != "message":
            continue
        message_date = _parse_message_date(message.get("date", ""))
        if since is not None and (message_date is None or message_date < since):
            continue
        if until is not None and (message_date is None or message_date >= until):
            continue
        messages_in_range += 1

        text = flatten_text(message.get("text", ""))
        if not looks_like_kendala(text):
            continue
        inets = extract_inets(text)
        if not inets:
            continue

        photo = message.get("photo") or ""
        for inet in inets:
            description = compact_description(text, inet)
            status, rca = classify(description)
            if rca == "DONE":
                skipped_done += 1
                continue
            total_active_updates += 1
            item = {
                "message_id": message.get("id"),
                "date": message.get("date", ""),
                "from": message.get("from", ""),
                "inet": inet,
                "description": description,
                "status": status,
                "rca": rca,
                "photo": photo,
            }
            previous = latest_by_inet.get(inet)
            previous_date = _parse_message_date(previous["date"]) if previous else None
            if previous is None or previous_date is None or (message_date is not None and message_date >= previous_date):
                latest_by_inet[inet] = item

    candidates = sorted(latest_by_inet.values(), key=lambda item: item["date"])
    rca_counts = Counter(item["rca"] for item in candidates)
    with_evidence = sum(1 for item in candidates if item["photo"])
    stats = {
        "messages": len(messages),
        "messages_in_range": messages_in_range,
        "skipped_done": skipped_done,
        "active_updates": total_active_updates,
        "older_updates_skipped": total_active_updates - len(candidates),
        "candidates": len(candidates),
        "unique_inets": len(candidates),
        "with_evidence_messages": with_evidence,
    }
    return stats, candidates, rca_counts


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _credentials_path() -> Path:
    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    options = []
    if raw:
        options.append(Path(raw))
    options.extend([
        _repo_root() / "secrets" / "google-service-account.json",
        Path("/app/secrets/google-service-account.json"),
    ])
    for path in options:
        if path.exists():
            return path
    raise RuntimeError("Credential Google Service Account tidak ditemukan.")


def _sheet_name() -> str:
    return os.getenv("KENDALA_SHEET_NAME", "Kendala").strip() or "Kendala"


def _copy_history_evidence(export_path: Path, item: dict[str, Any]) -> str:
    photo = str(item.get("photo") or "").strip()
    if not photo:
        return "-"
    source = export_path.parent / photo
    if not source.exists():
        return "-"
    parsed = _parse_message_date(item["date"]) or datetime.now()
    root = _repo_root() / "evidence"
    directory = root / f"{parsed.year:04d}" / f"{parsed.month:02d}" / item["inet"]
    directory.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix.lower() or ".jpg"
    destination = directory / f"history_{item['message_id']}{suffix}"
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination.relative_to(_repo_root()).as_posix()


def _format_date(value: str) -> str:
    parsed = _parse_message_date(value)
    return parsed.strftime("%d/%m/%Y %H:%M:%S") if parsed else value


def _build_rows(export_path: Path, candidates: list[dict[str, Any]], apply: bool) -> tuple[list[list[str]], list[str]]:
    statuses = download_statuses()
    rows: list[list[str]] = []
    missing: list[str] = []
    for item in candidates:
        reference = status_for_order(statuses, "", item["inet"])
        if reference is None:
            missing.append(item["inet"])
            continue
        evidence = _copy_history_evidence(export_path, item) if apply else (item["photo"] or "-")
        rows.append([
            _format_date(item["date"]),
            item["inet"],
            reference.customer_name or "",
            reference.address or "",
            reference.customer_phone or "",
            reference.ticket_id or "",
            str(item["from"] or ""),
            "UPDATE",
            item["rca"],
            item["description"] or "-",
            evidence,
        ])
    return rows, missing


def _apply_rows(rows: list[list[str]]) -> tuple[int, int]:
    credentials = service_account.Credentials.from_service_account_file(
        str(_credentials_path()), scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build("sheets", "v4", credentials=credentials, cache_discovery=False)
    spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID", DEFAULT_SPREADSHEET_ID).strip() or DEFAULT_SPREADSHEET_ID
    sheet = _sheet_name().replace("'", "''")
    prefix = f"'{sheet}'"

    current = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id, range=f"{prefix}!A:K"
    ).execute().get("values", [])

    if not current:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{prefix}!A1:K1",
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()
        current = [HEADERS]

    existing_rows: dict[str, int] = {}
    for index, row in enumerate(current[1:], start=2):
        if len(row) > 1:
            inet = str(row[1]).strip()
            if inet:
                existing_rows[inet] = index

    updates = []
    appends = []
    for row in rows:
        inet = row[1]
        row_number = existing_rows.get(inet)
        if row_number:
            updates.append({"range": f"{prefix}!A{row_number}:K{row_number}", "values": [row]})
        else:
            appends.append(row)

    if updates:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": updates},
        ).execute()
    if appends:
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{prefix}!A:K",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": appends},
        ).execute()
    return len(appends), len(updates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import history WORK ORDER MANYAR ke Sheet Kendala, 1 INET = update terbaru.")
    parser.add_argument("export_json", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview aman, tidak menulis apa pun.")
    mode.add_argument("--apply", action="store_true", help="Tulis/update data ke Sheet Kendala.")
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--since", type=lambda value: datetime.strptime(value, "%Y-%m-%d"))
    parser.add_argument("--until", type=lambda value: datetime.strptime(value, "%Y-%m-%d"))
    args = parser.parse_args()

    if not args.export_json.exists():
        raise SystemExit(f"File tidak ditemukan: {args.export_json}")

    stats, candidates, rca_counts = scan(args.export_json, args.since, args.until)
    print("=== PREVIEW KENDALA AKTIF TERBARU PER INET ===")
    print(f"Total pesan export         : {stats['messages']}")
    print(f"Pesan dalam rentang        : {stats['messages_in_range']}")
    if args.since:
        print(f"Mulai tanggal              : {args.since.date().isoformat()}")
    if args.until:
        print(f"Sebelum tanggal            : {args.until.date().isoformat()}")
    print(f"DONE/CLOSE diabaikan       : {stats['skipped_done']}")
    print(f"Update kendala ditemukan   : {stats['active_updates']}")
    print(f"Update lama diabaikan      : {stats['older_updates_skipped']}")
    print(f"Kandidat kendala terbaru   : {stats['candidates']}")
    print(f"INET unik                  : {stats['unique_inets']}")
    print(f"Kandidat dgn eviden        : {stats['with_evidence_messages']}")
    print()

    if rca_counts:
        print("RCA hasil klasifikasi:")
        for rca, count in sorted(rca_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {rca:<12} : {count}")
        print()

    rows, missing = _build_rows(args.export_json, candidates, apply=args.apply)
    if missing:
        print(f"INET tidak ditemukan di ORDER: {len(missing)}")
        for inet in missing:
            print(f"  - {inet}")
        if args.apply:
            raise SystemExit("APPLY DIBATALKAN agar tidak terjadi import parsial. Perbaiki INET ORDER di atas dulu.")
        print()

    limit = max(0, args.limit)
    for idx, item in enumerate(candidates[:limit], 1):
        print(f"[{idx}] {item['date']} | {item['from']}")
        print(f"INET    : {item['inet']}")
        print(f"STATUS  : {item['status']}")
        print(f"RCA     : {item['rca']}")
        print(f"KENDALA : {item['description'] or '-'}")
        print(f"EVIDEN  : {item['photo'] or '-'}")
        print()

    if len(candidates) > limit:
        print(f"... {len(candidates) - limit} kandidat lain tidak ditampilkan.")

    if args.dry_run:
        print("DRY RUN SELESAI. Tidak ada database atau Google Sheet yang diubah.")
        return

    inserted, updated = _apply_rows(rows)
    print("=== APPLY SELESAI ===")
    print(f"Baris baru ditambahkan : {inserted}")
    print(f"Baris INET diperbarui  : {updated}")
    print(f"Total aktif diolah     : {inserted + updated}")
    print("Satu INET hanya memiliki satu baris; apply ulang aman karena baris lama akan diperbarui.")


if __name__ == "__main__":
    main()
