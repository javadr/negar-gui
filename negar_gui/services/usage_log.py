"""Append-only JSON Lines log of AI requests: one line per HTTP request sent to a provider."""

import json
import logging
from datetime import datetime

from negar_gui.constants import SETTING_FILE

USAGE_FILE = SETTING_FILE.parent / "usage.jsonl"
logger = logging.getLogger(__name__)


def log_request(provider, model, prompt, status, ok, path=USAGE_FILE):
    row = {
        "ts": datetime.now().astimezone().isoformat(timespec="seconds"),  # local time: "today" = the user's day
        "provider": provider,
        "model": model,
        "prompt": prompt,
        "status": status,
        "ok": ok,
    }
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:  # logging must never break the AI button
        logger.error("usage log write failed: %s", e)


def counts(provider, path=USAGE_FILE):
    """(today, total) successful requests for `provider`; plain Python so startup needs no DuckDB."""
    today = datetime.now().astimezone().date().isoformat()
    n_today = n_total = 0
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:  # a half-written last line
                    continue
                if row.get("provider") == provider and row.get("ok"):
                    n_total += 1
                    n_today += row["ts"][:10] == today
    except OSError:
        pass
    return n_today, n_total


_SOURCE = """read_json(?, format='newline_delimited',
    columns={'ts': 'VARCHAR', 'provider': 'VARCHAR', 'prompt': 'VARCHAR', 'ok': 'BOOLEAN'})"""


def _query(select, rest, path):
    """`SELECT <select> FROM <the log> <rest>` via DuckDB (imported lazily: reports only)."""
    if not path.exists() or path.stat().st_size == 0:
        return []
    import duckdb

    return duckdb.execute(f"SELECT {select} FROM {_SOURCE} {rest}", [str(path)]).fetchall()


def report(path=USAGE_FILE):
    """Rows (day, provider, ok, failed), newest day first."""
    return _query(
        "substr(ts, 1, 10) AS day, provider, count(*) FILTER (WHERE ok), count(*) FILTER (WHERE NOT ok)",
        "GROUP BY ALL ORDER BY day DESC, provider",
        path,
    )


def daily(days=30, path=USAGE_FILE):
    """Rows (day, ok, failed) for the last `days` days that have requests, oldest first."""
    rows = _query(
        "substr(ts, 1, 10) AS day, count(*) FILTER (WHERE ok), count(*) FILTER (WHERE NOT ok)",
        f"GROUP BY day ORDER BY day DESC LIMIT {int(days)}",
        path,
    )
    return rows[::-1]


def share(column, path=USAGE_FILE):
    """Rows (value, successful requests) of `column` ('provider' or 'prompt'), biggest first."""
    assert column in ("provider", "prompt")
    return _query(f"{column}, count(*) AS n", f"WHERE ok GROUP BY {column} ORDER BY n DESC", path)


if __name__ == "__main__":
    import tempfile
    from pathlib import Path

    p = Path(tempfile.mkdtemp()) / "u.jsonl"
    assert counts("gemini", p) == (0, 0) and report(p) == []
    log_request("gemini", "m", "Fix", 200, True, p)
    log_request("gemini", "m", "Fix", 429, False, p)
    log_request("groq", "m", "Fix", 200, True, p)
    assert counts("gemini", p) == (1, 1)
    rows = report(p)
    assert sorted(rows, key=lambda r: r[1]) == [(rows[0][0], "gemini", 1, 1), (rows[0][0], "groq", 1, 0)], rows
    day = rows[0][0]
    assert daily(30, p) == [(day, 2, 1)], daily(30, p)
    assert sorted(share("provider", p)) == [("gemini", 1), ("groq", 1)]
    assert share("prompt", p) == [("Fix", 2)]
    print("ok")
