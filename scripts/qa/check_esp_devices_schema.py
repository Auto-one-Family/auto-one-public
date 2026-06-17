"""Quick esp_devices schema + hardware_type check for AUT-525 verify."""
import json
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parents[2] / "El Servador" / "god_kaiser_server" / "god_kaiser_dev.db"

if not DB.exists():
    print(f"DB not found: {DB}")
    raise SystemExit(1)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("PRAGMA table_info(esp_devices)")
cols = [(r[1], r[2], r[3]) for r in cur.fetchall()]
print("=== esp_devices columns ===")
for name, typ, notnull in cols:
    print(f"  {name:25} {typ:15} NOT NULL={bool(notnull)}")

print("\nboard_type present:", any(c[0] == "board_type" for c in cols))
print("hardware_type present:", any(c[0] == "hardware_type" for c in cols))

cur.execute(
    "SELECT device_id, hardware_type, device_metadata FROM esp_devices "
    "WHERE device_id LIKE 'ESP_%' ORDER BY device_id LIMIT 10"
)
print("\n=== sample devices ===")
for device_id, hardware_type, metadata_raw in cur.fetchall():
    meta = json.loads(metadata_raw) if metadata_raw else {}
    ih = meta.get("initial_heartbeat") or meta.get("last_heartbeat") or {}
    print(
        f"{device_id}: hardware_type={hardware_type!r}, "
        f"heartbeat.hardware_type={ih.get('hardware_type')!r}"
    )

conn.close()
