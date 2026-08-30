from __future__ import annotations

import sqlite3
from datetime import datetime

from config import settings
from services.jagir_work_orders import _ensure_tables, _resolve_tag


USERNAME = "sikirno"
WORK_ORDERS = (
    ("152310205282", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT ASRI UTARA 5 10-C RUNGKUT KIDUL SURABAYA 60293", "ODP-RKT-FGJ/33 FGJ/D04/33.01", "100 Mbps", "-16.12", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310217860", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT ASRI UTARA 9 1A RT 2 10 KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGL/03 FGL/D01/01.03", "100 Mbps", "-18.15", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310217049", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 1 17 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FGY/08 FGY/D01/01.08", "100 Mbps", "-18.29", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310204982", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 1 9 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/60 FHB/D05/60.01", "100 Mbps", "-16.69", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310230738", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 12 16 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/50 FHB/D04/01.50", "100 Mbps", "-20.91", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310102339", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 12 25 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/50 FHB/D04/01.50", "100 Mbps", "-17.16", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310213159", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 19 8 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FGZ/04 FGZ/D01/01.04", "100 Mbps", "-20.91", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310221673", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 20 8 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FGZ/11 FGZ/D01/01.11", "100 Mbps", "-19.54", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310235892", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 26 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FGZ/36 FGZ/D03/01.36", "100 Mbps", "-17.79", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310205881", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 3 21 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/09 FHB/D01/01.09", "100 Mbps", "-19.06", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310218315", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 4 NO 1 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/16 FHB/D01/01.16", "100 Mbps", "-17.79", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310233919", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 6 8 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/30 FHB/D02/01.30", "100 Mbps", "-23.46", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310208556", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 8 11 SG-13 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FGZ/23 FGZ/D02/01.23", "100 Mbps", "-16.67", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310203549", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT BARATA 8 7 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FGZ/23 FGZ/D02/01.23", "100 Mbps", "-16.57", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310220282", "MANUAL", "HVC_GOLD", "TITO", "811344015", "RUNGKUT BARATA NO 2 RUNGKUT MENANGGAL SURABAYA 60293", "ODP-RKT-FHB/45 FHB/D03/01.45", "100 Mbps", "-17.28", "DAPROS TA | REPLACEMENT ONT 200K"),
    ("152310202559", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT HARAPAN A BLOK C 46 KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGK/25 FGK/D02/06.25", "100 Mbps", "-16.19", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310219913", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT HARAPAN A K-34 KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGL/60 FGL/D06/60.01", "100 Mbps", "-22.44", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310215464", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT HARAPAN A L-14 KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGY/03 FGY/D01/01.03", "100 Mbps", "-19.39", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310233735", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT HARAPAN A-38 KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGL/41 FGL/D04/03.41", "100 Mbps", "-18.47", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310229368", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT HARAPAN C-39 KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGK/26 FGK/D02/06.26", "100 Mbps", "-17.33", "DAPROS TSEL| REPLACEMENT ONT 200K"),
    ("152310204343", "MANUAL", "HVC_GOLD", "", "", "RUNGKUT HARAPAN E 11-A KALI RUNGKUT SURABAYA 60293", "ODP-RKT-FGK/23 FGK/D02/06.23", "100 Mbps", "-16.25", "DAPROS TSEL| REPLACEMENT ONT 200K"),
)


def seed(database_path) -> tuple[int, int]:
    now = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    inserted = 0
    existing = 0
    with sqlite3.connect(database_path) as conn:
        _ensure_tables(conn)
        assigned_telegram_id, assigned_nik, assigned_name = _resolve_tag(conn, USERNAME)
        for item in WORK_ORDERS:
            row = conn.execute(
                "SELECT status FROM jagir_work_orders WHERE service_number=?",
                (item[0],),
            ).fetchone()
            if row is not None:
                existing += 1
                continue
            conn.execute(
                """
                INSERT INTO jagir_work_orders(
                    service_number, ticket_id, order_type, customer_name, customer_phone,
                    address, odp_name, package, onu_rx, description, assigned_username,
                    assigned_telegram_id, assigned_nik, assigned_name, sto, area, status,
                    source_chat_id, source_message_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'JGR', 'JAGIR', 'OPEN', NULL, NULL, ?, ?)
                """,
                (*item, USERNAME, assigned_telegram_id, assigned_nik, assigned_name, now, now),
            )
            inserted += 1
        conn.commit()
    return inserted, existing


if __name__ == "__main__":
    inserted, existing = seed(settings.database_path)
    print(f"JAGIR Sukirno seed selesai: {inserted} WO baru, {existing} sudah ada")
