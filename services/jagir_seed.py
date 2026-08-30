from __future__ import annotations

import sqlite3
from datetime import datetime

from services.jagir_work_orders import _ensure_tables, _resolve_tag


INITIAL_JAGIR_WO = (
    {
        "service_number": "152310108756",
        "ticket_id": "INC50753791",
        "order_type": "HVC_GOLD",
        "customer_name": "",
        "customer_phone": "",
        "address": "MEDOKAN ASRI TIMUR 6 RL-5H 22 MEDOKAN AYU SURABAYA 60295",
        "odp_name": "ODP-RKT-FGU/01 FGU/D01/01.01",
        "package": "100 Mbps",
        "onu_rx": "-24.43",
        "description": "DAPROS TSEL| REPLACEMENT ONT 200K",
    },
    {
        "service_number": "152310108180",
        "ticket_id": "INC50522420",
        "order_type": "HVC_GOLD",
        "customer_name": "",
        "customer_phone": "",
        "address": "SINGARAJA B-3 50 GUNUNG ANYAR SURABAYA 60294",
        "odp_name": "ODP-RKT-FGV/25 FGV/D02/01.25",
        "package": "100 Mbps",
        "onu_rx": "-18.6",
        "description": "DAPROS TSEL| REPLACEMENT ONT 200K",
    },
)


def seed_initial_jagir_work_orders(database_path) -> int:
    """Insert the two manually supplied JAGIR WOs once, without reopening DONE rows."""
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    inserted = 0
    with sqlite3.connect(database_path) as conn:
        _ensure_tables(conn)
        assigned_username = "agamrizky"
        assigned_telegram_id, assigned_nik, assigned_name = _resolve_tag(conn, assigned_username)

        for item in INITIAL_JAGIR_WO:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO jagir_work_orders(
                    service_number, ticket_id, order_type, customer_name, customer_phone,
                    address, odp_name, package, onu_rx, description, assigned_username,
                    assigned_telegram_id, assigned_nik, assigned_name, sto, area, status,
                    source_chat_id, source_message_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'JGR', 'JAGIR', 'OPEN', NULL, NULL, ?, ?)
                """,
                (
                    item["service_number"], item["ticket_id"], item["order_type"],
                    item["customer_name"], item["customer_phone"], item["address"],
                    item["odp_name"], item["package"], item["onu_rx"], item["description"],
                    assigned_username, assigned_telegram_id, assigned_nik, assigned_name,
                    now, now,
                ),
            )
            if cur.rowcount > 0:
                inserted += 1
        conn.commit()
    return inserted
