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
    status = "UPDATE"
    done_keywords = (
        "SUDAH GANTI",
        "SUDAH DIGANTI",
        "SELESAI",
        "DONE",
        "SUDAH SELESAI",
    )
    if any(keyword in value for keyword in done_keywords):
        return status, "DONE"
    if "MENOLAK" in value or "TIDAK MAU" in value or "TIDAK BERKENAN" in value:
        return status, "MENOLAK"
    if "RUKOS" in value or "RUMAH KOSONG" in value or "TIDAK ADA PENGHUNI" in value:
        return status, "RUKOS"
    if (
        "ALAMAT NOK" in value
        or "ALAMAT TIDAK" in value
        or "ALAMAT TIDAK DITEMUKAN" in value
    ):
        return status, "ALAMAT NOK"
    if "LEPAS DC" in value:
        return status, "LEPAS DC"
    if (
        "CABUT" in value
        or "PUTUS LANGGANAN" in value
        or "PUTUS INTERNET" in value
    ):
        return status, "CABUT"
    if "2 VOIP" in value or "ONT 2 VOIP" in value or "VOIP ADA 2" in value:
        return status, "ONT 2 VOIP"
    if (
        "MANJA" in value
        or "RESCHEDULE" in value
        or "JADWAL" in value
        or "BESOK" in value
        or "LUAR KOTA" in value
    ):
        return status, "MANJA"
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
        return status, "RNA"
    if "SALBON" in value:
        return status, "SALBON"
    return status, "UNSPEC"


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
    candidates: list[dict[str, Any]] = []
    unique_inets: set[str] = set()
    with_evidence = 0
    messages_in_range = 0
    rca_counts: Counter[str] = Counter()

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
        if photo:
            with_evidence += 1

        for inet in inets:
            description = compact_description(text, inet)
            status, rca = classify(description)
            unique_inets.add(inet)
            rca_counts[rca] += 1
            candidates.append(
                {
                    "message_id": message.get("id"),
                    "date": message.get("date", ""),
                    "from": message.get("from", ""),
                    "inet": inet,
                    "description": description,
                    "status": status,
                    "rca": rca,
                    "photo": photo or "",
                }
            )

    stats = {
        "messages": len(messages),
        "messages_in_range": messages_in_range,
        "candidates": len(candidates),
        "unique_inets": len(unique_inets),
        "with_evidence_messages": with_evidence,
    }
    return stats, candidates, rca_counts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Dry-run scanner history WORK ORDER MANYAR untuk kandidat Kendala."
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

    print("=== PREVIEW FINAL KENDALA HISTORY ===")
    print(f"Total pesan export    : {stats['messages']}")
    if args.since or args.until:
        print(f"Pesan dalam rentang   : {stats['messages_in_range']}")
    if args.since:
        print(f"Mulai tanggal         : {args.since.date().isoformat()}")
    if args.until:
        print(f"Sebelum tanggal       : {args.until.date().isoformat()}")
    print(f"Kandidat kendala      : {stats['candidates']}")
    print(f"INET unik             : {stats['unique_inets']}")
    print(f"Kandidat dgn eviden   : {stats['with_evidence_messages']}")
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
