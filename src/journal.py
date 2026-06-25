"""SQLite journal: every signal, its outcome, executions, and stats."""
import sqlite3
import time

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    setup TEXT,
    side TEXT NOT NULL DEFAULT 'long',   -- long | short
    score REAL,
    entry REAL, stop_loss REAL, tp1 REAL, tp2 REAL, tp3 REAL,
    reasoning TEXT,
    status TEXT NOT NULL DEFAULT 'open',  -- open | tp1 | tp2 | tp3 | stopped | breakeven
    closed_at INTEGER,
    result_r REAL,
    -- live-trade execution fields (null until executed)
    executed INTEGER NOT NULL DEFAULT 0,
    qty REAL, fill_price REAL, oco_id TEXT
);
CREATE TABLE IF NOT EXISTS claude_calls (day TEXT PRIMARY KEY, count INTEGER NOT NULL);
"""

_MIGRATIONS = [  # idempotent ADD COLUMN for DBs created before these fields existed
    ("signals", "executed", "INTEGER NOT NULL DEFAULT 0"),
    ("signals", "qty", "REAL"),
    ("signals", "fill_price", "REAL"),
    ("signals", "oco_id", "TEXT"),
    ("signals", "side", "TEXT NOT NULL DEFAULT 'long'"),
]


def conn():
    c = sqlite3.connect(config.DB_PATH)
    c.executescript(SCHEMA)
    c.row_factory = sqlite3.Row
    for table, col, decl in _MIGRATIONS:
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    return c


def add_signal(sig: dict) -> int:
    with conn() as c:
        side = "short" if sig.get("signal") == "short" else "long"
        cur = c.execute(
            "INSERT INTO signals (created_at, symbol, setup, side, score, entry, stop_loss, tp1, tp2, tp3, reasoning)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                int(time.time()), sig["symbol"], sig.get("setup"), side, sig.get("score"),
                sig["entry"], sig["stop_loss"], sig["tp1"], sig["tp2"], sig["tp3"],
                sig.get("reasoning", ""),
            ),
        )
        return cur.lastrowid


def get_signal(sig_id: int) -> dict | None:
    with conn() as c:
        row = c.execute("SELECT * FROM signals WHERE id=?", (sig_id,)).fetchone()
        return dict(row) if row else None


def mark_executed(sig_id: int, qty: float, fill_price: float, oco_id: str | None):
    with conn() as c:
        c.execute("UPDATE signals SET executed=1, qty=?, fill_price=?, oco_id=? WHERE id=?",
                  (qty, fill_price, oco_id, sig_id))


def open_signals():
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT * FROM signals WHERE status IN ('open','tp1','tp2','breakeven')"
        )]


def update_status(sig_id: int, status: str, result_r: float | None = None, close: bool = False):
    with conn() as c:
        if close:
            c.execute("UPDATE signals SET status=?, result_r=?, closed_at=? WHERE id=?",
                      (status, result_r, int(time.time()), sig_id))
        else:
            c.execute("UPDATE signals SET status=? WHERE id=?", (status, sig_id))


def signals_today() -> int:
    cutoff = int(time.time()) - 86400
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM signals WHERE created_at > ?", (cutoff,)).fetchone()[0]


def recent_signal_for(symbol: str, hours: int) -> bool:
    cutoff = int(time.time()) - hours * 3600
    with conn() as c:
        return c.execute("SELECT COUNT(*) FROM signals WHERE symbol=? AND created_at > ?",
                         (symbol, cutoff)).fetchone()[0] > 0


def realized_r_today() -> float:
    cutoff = int(time.time()) - 86400
    with conn() as c:
        rows = c.execute("SELECT result_r FROM signals WHERE closed_at > ? AND result_r IS NOT NULL",
                         (cutoff,)).fetchall()
    return round(sum(r[0] for r in rows), 2)


def claude_calls_today() -> int:
    day = time.strftime("%Y-%m-%d")
    with conn() as c:
        row = c.execute("SELECT count FROM claude_calls WHERE day=?", (day,)).fetchone()
        return row[0] if row else 0


def bump_claude_calls():
    day = time.strftime("%Y-%m-%d")
    with conn() as c:
        c.execute("INSERT INTO claude_calls(day,count) VALUES(?,1)"
                  " ON CONFLICT(day) DO UPDATE SET count=count+1", (day,))


def _agg(rows: list[dict]) -> dict:
    wins = [r for r in rows if r["result_r"] and r["result_r"] > 0]
    total_r = sum(r["result_r"] for r in rows if r["result_r"] is not None)
    return {
        "closed": len(rows),
        "wins": len(wins),
        "win_rate": round(100 * len(wins) / len(rows), 1) if rows else 0,
        "total_r": round(total_r, 2),
    }


def setup_performance(days: int = 30) -> dict:
    """Per-setup win-rate over recent closed signals — fed back to Claude."""
    cutoff = int(time.time()) - days * 86400
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT setup, result_r FROM signals WHERE closed_at > ? AND result_r IS NOT NULL", (cutoff,))]
    out = {}
    for setup in {r["setup"] for r in rows}:
        out[setup] = _agg([r for r in rows if r["setup"] == setup])
    return out


def weekly_stats() -> dict:
    cutoff = int(time.time()) - 7 * 86400
    with conn() as c:
        rows = [dict(r) for r in c.execute(
            "SELECT * FROM signals WHERE closed_at > ? AND result_r IS NOT NULL", (cutoff,))]
    stats = _agg(rows)
    stats["open"] = len(open_signals())
    stats["by_setup"] = {s: _agg([r for r in rows if r["setup"] == s])
                         for s in sorted({r["setup"] for r in rows if r["setup"]})}
    return stats
