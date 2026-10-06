"""Stream robot current readings from the workshop CSV file."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd


AXIS_COLUMNS = [f"Axis #{axis_number}" for axis_number in range(1, 9)]
OUTPUT_COLUMNS = ["Trait", *AXIS_COLUMNS, "Time"]

def init_stream_table(conn):
    """Create the synthetic-test table if it does not already exist.

    Reuse AXIS_COLUMNS, converting CSV names such as "Axis #1" to the
    database names such as "axis_1" used by StreamingSimulator._to_record.
    The caller manages the connection and commits the transaction.
    """
    columns = ", ".join(
        f"{column.lower().replace(' #', '_')} DOUBLE PRECISION NOT NULL"
        for column in AXIS_COLUMNS
    )
    conn.execute(f"""CREATE TABLE IF NOT EXISTS pm_lab_scaled_stream (
        run_id UUID NOT NULL, sequence BIGINT NOT NULL,
        trait TEXT NOT NULL, reading_time TIMESTAMPTZ NOT NULL,
        {columns}, normalized_values JSONB NOT NULL,
        standardized_values JSONB NOT NULL,
        received_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(run_id, sequence))""")


class StreamingSimulator:
    """Replay robot readings as individual controller messages."""

    def __init__(self, csv_path: str | Path, interval: float = 2.0) -> None:
        if interval < 0:
            raise ValueError("interval must be non-negative")

        self.csv_path = Path(csv_path)
        self.interval = interval
        self._data = self._read_csv(self.csv_path)
        self._position = 0

    @staticmethod
    def _read_csv(csv_path: Path) -> pd.DataFrame:
        data = pd.read_csv(csv_path, usecols=OUTPUT_COLUMNS)
        data[AXIS_COLUMNS] = data[AXIS_COLUMNS].apply(pd.to_numeric, errors="coerce")
        data["Time"] = pd.to_datetime(data["Time"], utc=True)
        return data

    @staticmethod
    def _to_record(row: pd.Series) -> dict[str, Any]:
        record = {
            "trait": row["Trait"],
            **{
                f"axis_{axis_number}": row[f"Axis #{axis_number}"]
                for axis_number in range(1, 9)
            },
            "reading_time": row["Time"],
        }
        return record

    def nextDataPoint(self) -> dict[str, Any] | None:
        """Return the next normalized record, or ``None`` at end-of-file."""
        if self._position >= len(self._data):
            return None

        row = self._data.iloc[self._position]
        self._position += 1
        return self._to_record(row)

    def run(
        self,
        n_steps: int,
        on_tick: Callable[[dict[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """Replay up to ``n_steps`` records and invoke ``on_tick`` for each."""
        if n_steps < 0:
            raise ValueError("n_steps must be non-negative")

        emitted: list[dict[str, Any]] = []
        for step in range(n_steps):
            record = self.nextDataPoint()
            if record is None:
                break
            if on_tick is not None:
                on_tick(record)
            emitted.append(record)
            if self.interval and step < n_steps - 1:
                time.sleep(self.interval)
        return emitted

    def bulk_load(
        self,
        csv_path: str | Path | None = None,
        on_record: Callable[[dict[str, Any]], None] | None = None,
    ) -> pd.DataFrame:
        """Load the complete dataset without playback delays."""
        source = self.csv_path if csv_path is None else Path(csv_path)
        data = self._read_csv(source)
        normalized = pd.DataFrame([self._to_record(row) for _, row in data.iterrows()])

        if on_record is not None:
            for record in normalized.to_dict(orient="records"):
                on_record(record)
        return normalized

    def seek(self, index: int) -> None:
        """Jump the replay position to a specific reading."""
        if not 0 <= index < len(self._data):
            raise IndexError(f"index must be between 0 and {len(self._data) - 1}")
        self._position = index
