import os
import sqlite3
from typing import Optional, Dict, Any, List
from app.config import settings


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def connect() -> sqlite3.Connection:
    _ensure_dir(settings.DB_PATH)
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = connect()
    cur = conn.cursor()

    # ================= EXISTING TABLES =================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sender_stats (
      sender_email TEXT PRIMARY KEY,
      sender_name TEXT,
      total_count INTEGER DEFAULT 0,
      high_count INTEGER DEFAULT 0,
      medium_count INTEGER DEFAULT 0,
      low_count INTEGER DEFAULT 0,
      avg_priority REAL DEFAULT 0.0,
      last_seen_ts INTEGER DEFAULT 0,
      vip INTEGER DEFAULT 0,
      blocked INTEGER DEFAULT 0
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS accounts (
      email TEXT PRIMARY KEY,
      provider TEXT NOT NULL,
      access_token TEXT,
      refresh_token TEXT,
      expires_at INTEGER
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS kv (
      k TEXT PRIMARY KEY,
      v TEXT
    );
    """)

    # ================= NEW TABLES (CORRECT PLACE) =================

    cur.execute("""
    CREATE TABLE IF NOT EXISTS followup_reminders (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email_id TEXT,
      thread_id TEXT,
      remind_at INTEGER,
      status TEXT DEFAULT 'pending',
      note TEXT,
      created_at INTEGER,
      subject TEXT,
      sender TEXT,
      provider TEXT DEFAULT 'gmail',
      triggered_at INTEGER,
      completed_at INTEGER
    );
    """)

    for col_sql in [
        "ALTER TABLE followup_reminders ADD COLUMN subject TEXT",
        "ALTER TABLE followup_reminders ADD COLUMN sender TEXT",
        "ALTER TABLE followup_reminders ADD COLUMN provider TEXT DEFAULT 'gmail'",
        "ALTER TABLE followup_reminders ADD COLUMN triggered_at INTEGER",
        "ALTER TABLE followup_reminders ADD COLUMN completed_at INTEGER",
    ]:
        try:
            cur.execute(col_sql)
        except sqlite3.OperationalError:
            pass

    cur.execute("""
    CREATE TABLE IF NOT EXISTS email_events (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email_id TEXT,
      event_type TEXT,
      metadata TEXT,
      created_at INTEGER
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS thread_summaries (
      thread_id TEXT PRIMARY KEY,
      summary TEXT,
      created_at INTEGER
    );
    """)

    conn.commit()
    conn.close()


# ================= ACCOUNT FUNCTIONS =================

def get_account(email: str) -> Optional[Dict[str, Any]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM accounts WHERE email=?", (email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_account(email: str, provider: str, access_token: str, refresh_token: str, expires_at: int) -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO accounts(email, provider, access_token, refresh_token, expires_at)
        VALUES(?,?,?,?,?)
        ON CONFLICT(email) DO UPDATE SET
            access_token=excluded.access_token,
            refresh_token=excluded.refresh_token,
            expires_at=excluded.expires_at
    """, (email, provider, access_token, refresh_token, expires_at))
    conn.commit()
    conn.close()


# ================= KV STORE =================

def kv_get(key: str) -> Optional[str]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT v FROM kv WHERE k=?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["v"] if row else None


def kv_set(key: str, value: str) -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (key, value),
    )
    conn.commit()
    conn.close()


# ================= SENDER STATS =================

def upsert_sender(sender_email: str, sender_name: str, priority: float, label: str, ts: int) -> None:
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT * FROM sender_stats WHERE sender_email=?", (sender_email,))
    row = cur.fetchone()

    high = 1 if label == "HIGH" else 0
    med = 1 if label == "MEDIUM" else 0
    low = 1 if label == "LOW" else 0

    if not row:
        cur.execute("""
          INSERT INTO sender_stats(sender_email, sender_name, total_count, high_count, medium_count, low_count, avg_priority, last_seen_ts)
          VALUES(?,?,?,?,?,?,?,?)
        """, (sender_email, sender_name, 1, high, med, low, float(priority), int(ts)))
    else:
        total = int(row["total_count"]) + 1
        prev_avg = float(row["avg_priority"])
        new_avg = prev_avg + (float(priority) - prev_avg) / total

        cur.execute("""
          UPDATE sender_stats
          SET sender_name=?,
              total_count=?,
              high_count=high_count+?,
              medium_count=medium_count+?,
              low_count=low_count+?,
              avg_priority=?,
              last_seen_ts=MAX(last_seen_ts, ?)
          WHERE sender_email=?
        """, (sender_name, total, high, med, low, new_avg, int(ts), sender_email))

    conn.commit()
    conn.close()


def set_sender_flag(sender_email: str, vip: Optional[int] = None, blocked: Optional[int] = None) -> None:
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT sender_email FROM sender_stats WHERE sender_email=?", (sender_email,))
    if not cur.fetchone():
        cur.execute("INSERT INTO sender_stats(sender_email) VALUES(?)", (sender_email,))

    if vip is not None:
        cur.execute("UPDATE sender_stats SET vip=? WHERE sender_email=?", (int(vip), sender_email))

    if blocked is not None:
        cur.execute("UPDATE sender_stats SET blocked=? WHERE sender_email=?", (int(blocked), sender_email))

    conn.commit()
    conn.close()


def get_sender(sender_email: str) -> Optional[Dict[str, Any]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sender_stats WHERE sender_email=?", (sender_email,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def top_senders(limit: int = 20) -> List[Dict[str, Any]]:
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
      SELECT sender_email, sender_name, total_count, high_count, avg_priority, vip, blocked
      FROM sender_stats
      ORDER BY high_count DESC, avg_priority DESC, total_count DESC
      LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]