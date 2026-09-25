"""Entry point for the robot predictive-maintenance web dashboard.

MVP scope: a single "Live Status" tab (see live_status.py). Run directly:

    python src/web_ui/web_ui_interface.py
"""

from dash import Dash, html

try:
    from src.web_ui import live_status
except ImportError:  # pragma: no cover - direct script execution fallback
    import live_status

app = Dash(__name__)
app.layout = html.Div(
    [
        html.H1("Robot Health Monitor"),
        live_status.layout,
    ]
)
live_status.register_callbacks(app)

if __name__ == "__main__":
    app.run(debug=True)
