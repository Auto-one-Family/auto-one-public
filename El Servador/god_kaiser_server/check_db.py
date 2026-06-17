from sqlalchemy import create_engine, text
engine = create_engine('postgresql://postgres:postgres@localhost:5432/god_kaiser')
with engine.connect() as conn:
    r = conn.execute(text('SELECT COUNT(*) FROM esp_heartbeat_logs'))
    print('Count:', r.fetchone()[0])

