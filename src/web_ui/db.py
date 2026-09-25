"""DB access for the Live Status dashboard.

This was a CSV-backed stub while Rangeetha's module was being built. That module
now exists and is connected to Neon, so the four interface functions below come
straight from it and the dashboard's imports are unchanged.

fetch_since(last_ts) was proposed here and has been adopted into the real
interface, where it runs
    SELECT * FROM robot_readings WHERE reading_time > %s ORDER BY reading_time

The replay cursor stays in this file on purpose. The stored readings are from
October 2022, so polling for "rows newer than now" returns nothing unless the
simulator happens to be inserting at that moment. For the demo the dashboard
replays stored rows in order instead, which looks the same on screen. Use
fetch_since() from the real module when you want true new-row polling.
"""

import sys
from pathlib import Path

import pandas as pd

_agent_dir = Path(__file__).resolve().parents[1] / "data_collection"
if str(_agent_dir) not in sys.path:
    sys.path.insert(0, str(_agent_dir))

try:
    from src.data_collection.data_collection_agent import (  # type: ignore
        fetch_all,
        fetch_since,
        get_connection,
        insert_reading,
    )
except ImportError:  # pragma: no cover - direct script execution fallback
    from data_collection_agent import (  # type: ignore
        fetch_all,
        fetch_since,
        get_connection,
        insert_reading,
    )

__all__ = [
    "get_connection",
    "insert_reading",
    "fetch_all",
    "fetch_since",
    "fetch_next_batch",
    "reset_cursor",
]

_replay_df: pd.DataFrame | None = None

# The recording opens during an idle stretch, so replaying from row 0 shows a flat
# line at zero. Start where the notebook's Step 2 demo starts, so both views show
# the same window of the robot actually working.
START_AT_READING = 11_604

# One reading per poll. With live_status polling every 2 seconds this advances at
# exactly the rate the workshop specifies, and at the same rate as the notebook's
# Step 2 demo, so both views move through the data together. Raise this to fill the
# 90-second window faster at the cost of that alignment.
BATCH_SIZE = 1

_cursor = START_AT_READING


def fetch_next_batch(batch_size: int = BATCH_SIZE) -> pd.DataFrame:
    """Return the next slice of stored readings, advancing a replay cursor."""
    global _replay_df, _cursor

    if _replay_df is None:
        _replay_df = fetch_all()

    end = min(_cursor + batch_size, len(_replay_df))
    batch = _replay_df.iloc[_cursor:end].copy()
    _cursor = end
    return batch


def reset_cursor() -> None:
    """Restart the replay from the start of the active window."""
    global _cursor
    _cursor = START_AT_READING
