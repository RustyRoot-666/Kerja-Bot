from __future__ import annotations
import asyncio, csv, sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

def utc_now(): return datetime.utcnow().replace(microsecond=0).isoformat()+'Z'
@dataclass(frozen=True)
class Technician:
 id:int; telegram_id:int; nik:str; name:str; sto:str; created_at:str; password_hash:str|None=None; role:str='technician'; is_active:int=1
class Database:
 def __init__(self,db_path:Path): self.db_path=db_path; self.db_path.parent.mkdir(parents=True,exist_ok=True); self._lock=asyncio.Lock()
 @contextmanager
 def connection(self)->Iterable[sqlite3.Connection]:
  conn=sqlite3.connect(self.db_path); conn.row_factory=sqlite3.Row; conn.execute('PRAGMA foreign_keys = ON')
  try: yield conn; conn.commit()
  finally: conn.close()
 async def initialize(self):
  async with self._lock:
   with self.connection() as conn:
    conn.executescript("""CREATE TABLE IF NOT EXISTS technicians(id INTEGER PRIMARY KEY AUTOINCREMENT,telegram_id INTEGER NOT NULL UNIQUE,nik TEXT NOT NULL,name TEXT NOT NULL,sto TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,password_hash TEXT,role TEXT NOT NULL DEFAULT 'technician',is_active INTEGER NOT NULL DEFAULT 1);CREATE TABLE IF NOT EXISTS histories(id INTEGER PRIMARY KEY AUTOINCREMENT,technician_id INTEGER NOT NULL,telegram_id INTEGER NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('CONFIG','REPORT','STO')),ticket_id TEXT,service_number TEXT,old_sn TEXT,new_sn TEXT,ont_type TEXT,sto TEXT,valins_id TEXT,content TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE CASCADE);CREATE TABLE IF NOT EXISTS ocr_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,technician_id INTEGER,telegram_id INTEGER NOT NULL,image_path TEXT NOT NULL,raw_text TEXT NOT NULL,serial_number TEXT,model TEXT,manufacturer TEXT,confidence REAL NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE SET NULL);CREATE TABLE IF NOT EXISTS web_link_requests(id INTEGER PRIMARY KEY AUTOINCREMENT,token_hash TEXT NOT NULL UNIQUE,telegram_id INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','confirmed','expired','cancelled')),expires_at TEXT NOT NULL,confirmed_at TEXT,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS web_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,token_hash TEXT NOT NULL UNIQUE,technician_id INTEGER NOT NULL,expires_at TEXT NOT NULL,created_at TEXT NOT NULL,last_seen_at TEXT NOT NULL,FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE CASCADE);CREATE TABLE IF NOT EXISTS payroll_records(id INTEGER PRIMARY KEY AUTOINCREMENT,technician_id INTEGER,nik TEXT NOT NULL,technician_name TEXT NOT NULL DEFAULT '',validasi_tactical TEXT NOT NULL DEFAULT '',validasi_parameter TEXT NOT NULL DEFAULT '',hss TEXT NOT NULL DEFAULT '',batch TEXT NOT NULL DEFAULT '',status_rapel TEXT NOT NULL DEFAULT '',submission_date TEXT NOT NULL DEFAULT '',task_payment TEXT NOT NULL DEFAULT '',status_payment TEXT NOT NULL DEFAULT '',paid_to TEXT NOT NULL DEFAULT '',payment_information TEXT NOT NULL DEFAULT '',source_row_hash TEXT NOT NULL UNIQUE,source TEXT NOT NULL DEFAULT 'Google Sheets - REKON | VALIDASI',synced_at TEXT NOT NULL,FOREIGN KEY(technician_id) REFERENCES technicians(id) ON DELETE SET NULL);CREATE INDEX IF NOT EXISTS idx_histories_telegram ON histories(telegram_id);CREATE INDEX IF NOT EXISTS idx_histories_ticket ON histories(ticket_id);CREATE INDEX IF NOT EXISTS idx_histories_service ON histories(service_number);CREATE INDEX IF NOT EXISTS idx_histories_sn ON histories(old_sn,new_sn);CREATE INDEX IF NOT EXISTS idx_web_link_requests_telegram ON web_link_requests(telegram_id,status);CREATE INDEX IF NOT EXISTS idx_web_sessions_technician ON web_sessions(technician_id);CREATE INDEX IF NOT EXISTS idx_payroll_nik ON payroll_records(nik);CREATE INDEX IF NOT EXISTS idx_payroll_technician ON payroll_records(technician_id);CREATE INDEX IF NOT EXISTS idx_payroll_payment_status ON payroll_records(status_payment);""")
    # Preserve the existing technician migration behavior.
    with self.connection() as conn:
     columns={r['name'] for r in conn.execute('PRAGMA table_info(technicians)').fetchall()}
     for c,s in {'sto':"ALTER TABLE technicians ADD COLUMN sto TEXT NOT NULL DEFAULT ''",'password_hash':'ALTER TABLE technicians ADD COLUMN password_hash TEXT','role':"ALTER TABLE technicians ADD COLUMN role TEXT NOT NULL DEFAULT 'technician'",'is_active':'ALTER TABLE technicians ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1'}.items():
      if c not in columns: conn.execute(s)
