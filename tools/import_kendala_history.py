from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

INET_RE = re.compile(r"\b15\d{10,13}\b")
LABEL_PATTERNS = (
    re.compile(r"NO\s*INET\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
    re.compile(r"INET\s*/\s*VOIP\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
    re.compile(r"NO\s*SERVICE\s*[:\-]?\s*(15\d{10,13})", re.IGNORECASE),
)

KENDALA_KEYWORDS = (
    "NOK",
    "MANJA",
    "MENOLAK",
    "TIDAK MAU",
    "TIDAK BERKENAN",
    "RUKOS",
    "RUMAH KOSONG",
    "RNA",
    "ALAMAT NOK",
    "LEPAS DC",
    "CABUT",
    "SALBON",
    "HISTORY NOK",
    "CP NOK",
    "CP NO WA",
    "KENDALA",
    "RESCHEDULE",
    "JADWAL",
    "BESOK",
    "TIDAK RESPON",
    "NO RESPON",
    "TIDAK ADA RESPON",
    "TIDAK BISA DIHUBUNGI",
    "PUTUS LANGGANAN",
    "PUTUS INTERNET",
    "LUAR KOTA",
    "SUDAH DIGANTI",
    "SUDAH GANTI",
    "ONT OFF",
    "NO INET DAN SN BEDA",
)

IGNORE_MARKERS = (
    "/STO",
    "/CONFIG",
    "/REPORT",
    "#REQOPENTIKET",
    "MOBAN ASSIGN LENSA CHAT",
)


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
        if inet in line and (
            "NO INET" in upper
            or "INET / VOIP" in upper
            or "NO SERVICE" in upper
        ):
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
    description = " | ".join(cleaned).strip(" |")
    return description[:500]


def classify(description: str) -> tuple[str, str]:
    value = " ".join(description.upper().split())
    done_keywords = (
        "SUDAH GANTI",
        "SUDAH DIGANTI",
        "SELESAI",
        "DONE",
        "SUDAH SELESAI",
    )
    if any(keyword in value for keyword in done_keywords):
        return "CLOSE", "DONE"
    if "MENOLAK" in value or "TIDAK MAU" in value or "TIDAK BERKENAN" in value:
        return "UPDATE", "MENOLAK"
    if "RUKOS" in value or "RUMAH KOSONG" in value or "TIDAK ADA PENGHUNI" in value:
        return "UPDATE", "RUKOS"
    if (
        "ALAMAT NOK" in value
        or "ALAMAT TIDAK" in value
        or "ALAMAT TIDAK DITEMUKAN" in value
    ):
        return "UPDATE", "ALAMAT NOK"
    if "LEPAS DC" in value:
        return "UPDATE", "LEPAS DC"
    if (
        "CABUT" in value
        or "PUTUS LANGGANAN" in value
        or "PUTUS INTERNET" in value
    ):
        return "UPDATE", "CABUT"
    if "2 VOIP" in value or "ONT 2 VOIP" in value or "VOIP ADA 2" in value:
        return "UPDATE", "ONT 2 VOIP"
    if (
        "MANJA" in value
        or "RESCHEDULE" in value
        or "JADWAL" in value
        or "BESOK" in value
        or "LUAR KOTA" in value
    ):
        return "UPDATE", "MANJA"
    if (
        "RNA" in value
        or "TIDAK RESPON" in value
        or "NO RESPON" in value
        or "TIDAK ADA RESPON" in value
        or "TIDAK BISA DIHUBUNGI" in value
        or "CP NOK" in value
        or "CP NO WA" in value
        or "HISTORY NOK" in value
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


def scan(
    export_path: Path,
    since: datetime | None = None,
    until: datetime | None = None,
) -> tuple[dict[str, int], list[dict[str, Any]], Counter[str]]:
    data = json.loads(export_path.read_text(encoding="utf-8"))
    messages = data.get("messages", [])
    latest_by_inet: dict[str, dict[str, Any]] = {}
    messages_in_range = 0
    skipped_done = 0
    raw_kendala = 0

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

        photo = message.get("photo")

        for inet in inets:
            description = compact_description(text, inet)
            status, rca = classify(description)
            if rca == "DONE":
                skipped_done += 1
                continue

            raw_kendala += 1
            candidate = {
                "message_id": message.get("id"),
                "date": message.get("date", ""),
                "date_obj": message_date,
                "from": message.get("from", ""),
                "inet": inet,
                "description": description,
                "status": status,
                "rca": rca,
                "photo": photo or "",
            }

            previous = latest_by_inet.get(inet)
            if previous is None:
                latest_by_inet[inet] = candidate
                continue

            previous_date = previous.get("date_obj")
            if previous_date is None or (
                message_date is not None and message_date >= previous_date
            ):
                latest_by_inet[inet] = candidate

    candidates = sorted(
        latest_by_inet.values(),
        key=lambda item: (
            item.get("date_obj") or datetime.min,
            str(item.get("message_id") or ""),
        ),
    )

    with_evidence = sum(1 for item in candidates if item.get("photo"))
    rca_counts: Counter[str] = Counter(item["rca"] for item in candidates)
    older_updates_ignored = raw_kendala - len(candidates)

    for item in candidates:
        item.pop("date_obj", None)

    stats = {
        "messages": len(messages),
        "messages_in_range": messages_in_range,
        "raw_kendala": raw_kendala,
        "candidates": len(candidates),
        "unique_inets": len(candidates),
        "with_evidence_messages": with_evidence,
        "skipped_done": skipped_done,
        "older_updates_ignored": older_updates_ignored,
    }
    return stats, candidates, rca_counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run scanner history WORK ORDER MANYAR untuk kendala aktif terbaru per INET."
    )
    parser.add_argument("export_json", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="Mode aman; tidak menulis apa pun.")
    parser.add_argument("--limit", type=int, default=25, help="Jumlah contoh kandidat yang ditampilkan.")
    parser.add_argument(
        "--since",
        type=lambda value: datetime.strptime(value, "%Y-%m-%d"),
        help="Hanya proses pesan mulai tanggal ini (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--until",
        type=lambda value: datetime.strptime(value, "%Y-%m-%d"),
        help="Hanya proses pesan sebelum tanggal ini (YYYY-MM-DD).",
    )
    args = parser.parse_args()

    if not args.export_json.exists():
        raise SystemExit(f"File tidak ditemukan: {args.export_json}")

    if not args.dry_run:
        raise SystemExit("Untuk saat ini tool ini hanya mendukung --dry-run. Tidak ada data yang akan ditulis.")

    stats, candidates, rca_counts = scan(args.export_json, since=args.since, until=args.until)

    print("=== PREVIEW KENDALA AKTIF TERBARU PER INET ===")
    print(f"Total pesan export        : {stats['messages']}")
    if args.since or args.until:
        print(f"Pesan dalam rentang       : {stats['messages_in_range']}")
    if args.since:
        print(f"Mulai tanggal             : {args.since.date().isoformat()}")
    if args.until:
        print(f"Sebelum tanggal           : {args.until.date().isoformat()}")
    print(f"DONE/CLOSE diabaikan      : {stats['skipped_done']}")
    print(f"Update kendala ditemukan  : {stats['raw_kendala']}")
    print(f"Update lama diabaikan     : {stats['older_updates_ignored']}")
    print(f"Kandidat kendala terbaru  : {stats['candidates']}")
    print(f"INET unik                 : {stats['unique_inets']}")
    print(f"Kandidat dgn eviden       : {stats['with_evidence_messages']}")
    print()

    if rca_counts:
        print("RCA hasil klasifikasi:")
        for rca, count in sorted(rca_counts.items(), key=lambda item: (-item[1], item[0])):
            print(f"  {rca:<12} : {count}")
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
        print(f"... {len(candidates) - limit} kandidat lain tidak ditampilkan. Gunakan --limit untuk menambah contoh.")

    print("DRY RUN SELESAI. Tidak ada database atau Google Sheet yang diubah.")


if __name__ == "__main__":
    main()
