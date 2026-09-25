"""Live Status tab: layout + callbacks for the polling live chart and the debug bulk-load button."""

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate

try:
    from src.web_ui import db
except ImportError:  # pragma: no cover - direct script execution fallback
    import db

AXIS_COLUMNS = [f"axis_{i}" for i in range(1, 9)]
# Same validated palette, in the same axis order, as the notebook. Each joint keeps
# one colour across both views so nobody has to re-learn them. These eight were
# checked for colourblind separation; plotly's defaults were not.
AXIS_COLORS = [
    "#2a78d6",  # axis_1 blue
    "#eb6834",  # axis_2 orange
    "#1baf7a",  # axis_3 aqua
    "#eda100",  # axis_4 yellow
    "#e87ba4",  # axis_5 magenta
    "#008300",  # axis_6 green
    "#4a3aa7",  # axis_7 violet
    "#e34948",  # axis_8 red
]

# Poll every 2 seconds, matching the reading interval the workshop specifies.
# Each poll takes the next batch of readings, the way a real dashboard picks up
# whatever has landed since it last looked.
POLL_INTERVAL_MS = 2000
ROLLING_WINDOW_SECONDS = 90

layout = html.Div(
    [
        html.H3("Realtime Current (Amps, stacked)"),
        html.Button("Live", id="live-button", n_clicks=0),
        html.Button("Bulk Load (debug)", id="bulk-load-button", n_clicks=0),
        html.Span(id="bulk-load-status", style={"marginLeft": "12px", "color": "#666"}),
        dcc.Graph(id="live-status-chart"),
        dcc.Interval(id="poll-interval", interval=POLL_INTERVAL_MS, n_intervals=0),
        dcc.Store(id="buffer-store", data=[]),
    ]
)


def _to_records(df: pd.DataFrame) -> list[dict]:
    out = df.copy()
    out["reading_time"] = out["reading_time"].astype(str)
    return out.to_dict("records")


def _from_records(records: list[dict]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=["trait", *AXIS_COLUMNS, "reading_time"])
    df = pd.DataFrame(records)
    df["reading_time"] = pd.to_datetime(df["reading_time"], format="ISO8601")
    return df


def _trim_to_window(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    cutoff = df["reading_time"].max() - pd.Timedelta(seconds=ROLLING_WINDOW_SECONDS)
    return df[df["reading_time"] >= cutoff]


def _build_figure(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    if df.empty:
        fig.update_layout(title="Waiting for data...")
        return fig

    for axis, color in zip(AXIS_COLUMNS, AXIS_COLORS):
        fig.add_trace(
            go.Scatter(
                x=df["reading_time"],
                y=df[axis],
                name=axis.replace("_", " ").title(),
                mode="lines",
                stackgroup="axes",
                line=dict(width=0.5, color=color),
            )
        )

    fig.update_layout(
        xaxis_title="Time",
        yaxis_title="Current (A)",
        legend_title="Axis",
        margin=dict(l=40, r=20, t=20, b=40),
    )
    return fig


def register_callbacks(app: Dash) -> None:
    @app.callback(
        Output("buffer-store", "data"),
        Output("bulk-load-status", "children"),
        Output("poll-interval", "disabled"),
        Input("poll-interval", "n_intervals"),
        Input("live-button", "n_clicks"),
        Input("bulk-load-button", "n_clicks"),
        State("buffer-store", "data"),
        prevent_initial_call=True,
    )
    def update_buffer(_n_intervals, _live_clicks, _bulk_clicks, current_records):
        trigger = ctx.triggered_id

        if trigger == "bulk-load-button":
            # Stop live refresh entirely and plot the whole CSV in one shot.
            full_df = db.fetch_all()
            status = f"Bulk loaded {len(full_df)} rows from the CSV."
            return _to_records(full_df), status, True

        if trigger == "live-button":
            # Resume live refresh from a clean slate.
            db.reset_cursor()
            return [], "Live refresh resumed.", False

        # Interval tick: append newly-arrived rows, keep only the rolling window.
        new_rows = db.fetch_next_batch()
        if new_rows.empty:
            raise PreventUpdate

        current = _from_records(current_records or [])
        combined = pd.concat([current, new_rows], ignore_index=True)
        combined = _trim_to_window(combined)
        return _to_records(combined), "", False

    @app.callback(
        Output("live-status-chart", "figure"),
        Input("buffer-store", "data"),
    )
    def redraw_chart(records):
        df = _from_records(records)
        return _build_figure(df)
