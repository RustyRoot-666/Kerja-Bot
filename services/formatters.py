from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError

from database import Technician


def value(data: dict, key: str) -> str:
    return str(data.get(key) or "-").strip()


def line(label: str, text: str, width: int = 17) -> str:
    return f"{label:<{width}}: {text}"


def generate_config(technician: Technician, data: dict) -> str:
    rows = [
        "==============================",
        "/CONFIG REPLACEMENT ONT",
        "==============================",
        line("NIK", technician.nik),
        line("NAMA", technician.name),
        line("TIKET ID", value(data, "ticket_id")),
        line("NO SERVICE", value(data, "service_number")),
        line("NO VOIP", value(data, "voip")),
        line("SN ONT LAMA", value(data, "old_sn")),
        line("SN ONT BARU", value(data, "new_sn")),
        line("TYPE ONT", value(data, "ont_type")),
        line("STO", value(data, "sto")),
        line("KETERANGAN", value(data, "description")),
    ]
    return "\n".join(rows)


def generate_report(technician: Technician, data: dict, timezone: str) -> str:
    try:
        today = datetime.now(ZoneInfo(timezone)).strftime("%d/%m/%Y")
    except ZoneInfoNotFoundError:
        today = datetime.now().strftime("%d/%m/%Y")
    rows = [
        "==============================",
        "/REPORT REPLACEMENT ONT",
        "==============================",
        line("TANGGAL", today),
        line("NIK", technician.nik),
        line("NAMA", value(data, "customer_name")),
        line("TIKET ID", value(data, "ticket_id")),
        line("NO INET", value(data, "internet_number")),
        line("SN ONT LAMA", value(data, "old_sn")),
        line("SN ONT BARU", value(data, "new_sn")),
        line("VALINS ID", value(data, "valins_id")),
        line("RESULT", value(data, "result")),
        line("KETERANGAN", value(data, "description")),
        "==============================",
    ]
    return "\n".join(rows)


def generate_sto(technician: Technician, data: dict) -> str:
    rows = [
        line("/STO", value(data, "sto")),
        line("TIKET", value(data, "ticket_id")),
        line("NO SERVICE", value(data, "service_number")),
        line("SN ONT LAMA", value(data, "old_sn")),
        line("SN ONT BARU", value(data, "new_sn")),
        line("TYPE ONT", value(data, "ont_type")),
        line("STO", value(data, "sto")),
        line("VALIN ID", value(data, "valins_id")),
        line("KETERANGAN", value(data, "description")),
        line("NAMA", value(data, "customer_name")),
        line("ALAMAT", value(data, "address")),
        line("CP", value(data, "customer_phone")),
        line("NIK NAMA TEKNISI", f"{technician.nik} | {technician.name}"),
    ]
    return "\n".join(rows)
