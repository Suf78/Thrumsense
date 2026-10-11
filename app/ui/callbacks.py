from datetime import datetime, timedelta
from typing import Any, Dict, List
from dash import Input, Output, State, callback_context, html, clientside_callback
import dash_bootstrap_components as dbc

from app.services import (
    get_sim_state,
    get_series,
    get_alerts,
    get_kpis,
    get_health,
    ALL_SENSORS,
)
from app.replay import replay_engine
from app.detect import get_thresholds_for_sensor
from app.ui.charts import create_timeseries_figure, create_benchmark_figure
from app.benchmark import run_benchmark_suite
from app.db import get_benchmarks_col

def register_callbacks(app) -> None:
    """Register all dashboard callbacks communicating strictly via services.py (AGENTS rule 9)."""

    # Replay Controls Callback - directly updates replay_engine state and triggers UI refresh
    @app.callback(
        Output("control-signal-store", "data"),
        Input("btn-play", "n_clicks"),
        Input("btn-pause", "n_clicks"),
        Input("btn-reset", "n_clicks"),
        Input("btn-speed-1", "n_clicks"),
        Input("btn-speed-10", "n_clicks"),
        Input("btn-speed-60", "n_clicks"),
        State("control-signal-store", "data"),
        prevent_initial_call=True,
    )
    def handle_controls(play_c, pause_c, reset_c, s1_c, s10_c, s60_c, current_sig):
        ctx = callback_context
        if not ctx.triggered:
            return current_sig or 0
        button_id = ctx.triggered[0]["prop_id"].split(".")[0]

        if button_id == "btn-play":
            replay_engine.play()
        elif button_id == "btn-pause":
            replay_engine.pause()
        elif button_id == "btn-reset":
            replay_engine.reset()
        elif button_id == "btn-speed-1":
            replay_engine.set_speed(1)
        elif button_id == "btn-speed-10":
            replay_engine.set_speed(10)
        elif button_id == "btn-speed-60":
            replay_engine.set_speed(60)

        return (current_sig or 0) + 1

    # Clientside theme toggle callback updating document dataset theme attribute
    app.clientside_callback(
        """
        function(n_clicks, current_theme) {
            if (!n_clicks) return current_theme || 'dark';
            var next_theme = (current_theme === 'dark') ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', next_theme);
            return next_theme;
        }
        """,
        Output("theme-store", "data"),
        Input("theme-toggle-btn", "n_clicks"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )

    # Main Refresh Callback (triggered by interval timer, controls signal, or filter changes)
    @app.callback(
        Output("sim-clock-display", "children"),
        Output("cache-status-badge", "children"),
        Output("cache-status-badge", "className"),
        Output("kpi-sensors-ok", "children"),
        Output("kpi-alerts-count", "children"),
        Output("kpi-data-quality", "children"),
        Output("kpi-fleet-score", "children"),
        Output("timeseries-chart", "figure"),
        Output("alert-feed-container", "children"),
        Output("sensor-health-grid", "children"),
        Input("interval-timer", "n_intervals"),
        Input("control-signal-store", "data"),
        Input("sensor-select", "value"),
        Input("range-select", "value"),
        State("theme-store", "data"),
    )
    def refresh_dashboard(n_intervals, control_sig, selected_sensor, range_val, theme):
        sim = get_sim_state()
        clock_dt = sim["clock_dt"]
        clock_str = clock_dt.strftime("%d %b %Y %H:%M") + (" (STREAMING)" if sim["running"] else " (PAUSED)")

        # KPI Data
        kpi = get_kpis()
        sensors_ok_text = f"{kpi['sensors_ok']} / {kpi['total_sensors']}"
        alerts_count_text = str(kpi["active_alerts"])
        data_quality_text = f"{kpi['data_quality_pct']}%"
        fleet_score_text = f"{kpi['fleet_score']} / 100"

        # Cache Badge
        cache_stats = kpi["cache_stats"]
        if cache_stats.get("online"):
            cache_badge_text = f"Redis Online ({cache_stats['ratio']}% Hit Ratio)"
            cache_badge_class = "badge bg-success"
        else:
            cache_badge_text = "Redis Offline (Falling back to Mongo)"
            cache_badge_class = "badge bg-warning text-dark"

        # Time range window
        if range_val == "24h":
            start_dt = clock_dt - timedelta(hours=24)
        elif range_val == "30d":
            start_dt = clock_dt - timedelta(days=30)
        else:
            start_dt = clock_dt - timedelta(days=7)

        # Time Series Chart bounded by current stream clock
        series_data = get_series(selected_sensor, start=start_dt, end=clock_dt)
        thresholds = get_thresholds_for_sensor(selected_sensor)
        alerts_data = get_alerts(sensor_id=selected_sensor, limit=50)
        fig = create_timeseries_figure(
            series_data=series_data,
            sensor_id=selected_sensor,
            thresholds=thresholds,
            alerts=alerts_data,
            theme=theme or "dark"
        )

        # Alert Feed List
        all_alerts = get_alerts(limit=25)
        if all_alerts:
            feed_items = []
            for a in all_alerts:
                sev = a.get("severity", "info")
                badge_class = "badge-ok" if sev == "info" else ("badge-warn" if sev == "warning" else "badge-critical")
                feed_items.append(
                    html.Div(
                        className="p-2 mb-2 rounded",
                        style={"backgroundColor": "var(--surface-2)", "borderLeft": "3px solid var(--primary)"},
                        children=[
                            html.Div(
                                className="d-flex justify-content-between align-items-center mb-1",
                                children=[
                                    html.Span(a["sensor_id"], className="fw-bold small"),
                                    html.Span(sev.upper(), className=f"badge {badge_class}"),
                                ]
                            ),
                            html.Div(a.get("explanation", ""), className="small text-muted"),
                            html.Div(a.get("timestamp", "")[:19].replace("T", " "), className="mono-text text-muted", style={"fontSize": "0.75rem"}),
                        ]
                    )
                )
            alert_feed = feed_items
        else:
            alert_feed = html.Div(
                className="text-center py-4",
                children=[
                    html.Img(src="/assets/no-alerts.png", style={"maxWidth": "150px", "opacity": "0.85", "borderRadius": "8px"}, className="mb-2"),
                    html.Div("All Telemetry Streams Healthy", className="small fw-bold text-success"),
                    html.Div("No active threshold or sensor faults detected.", className="text-muted small"),
                ]
            )

        # Health Grid Tiles
        health_info = get_health()
        sensors_dict = health_info.get("sensors", {})
        grid_tiles = []
        for s_id in ALL_SENSORS:
            s_data = sensors_dict.get(s_id, {"score": 100.0, "band": "ok"})
            score_val = s_data["score"]
            band = s_data["band"]
            tile_border = "var(--ok)" if band == "ok" else ("var(--warn)" if band == "watch" else "var(--critical)")

            grid_tiles.append(
                html.Div(
                    className="p-2 rounded text-center",
                    style={
                        "backgroundColor": "var(--surface)",
                        "border": f"1px solid {tile_border}",
                        "minWidth": "110px",
                        "flex": "1 1 calc(14% - 10px)",
                    },
                    children=[
                        html.Div(s_id, className="small fw-bold text-truncate", title=s_id),
                        html.Div(f"{score_val:.0f}", className="mono-text fw-bold mt-1", style={"color": tile_border, "fontSize": "1.2rem"}),
                        html.Div(band.upper(), className="small text-muted", style={"fontSize": "0.7rem"}),
                    ]
                )
            )

        return (
            clock_str,
            cache_badge_text,
            cache_badge_class,
            sensors_ok_text,
            alerts_count_text,
            data_quality_text,
            fleet_score_text,
            fig,
            alert_feed,
            grid_tiles,
        )

    # Benchmark Execution Callback
    @app.callback(
        Output("benchmark-chart", "figure"),
        Input("btn-run-benchmark", "n_clicks"),
        State("theme-store", "data"),
    )
    def trigger_benchmark(n_clicks, theme):
        if n_clicks and n_clicks > 0:
            results = run_benchmark_suite(iterations=10)
            return create_benchmark_figure(results, theme=theme or "dark")
        # Pre-load latest recorded benchmark runs
        latest_runs = list(get_benchmarks_col().find().sort("_id", -1).limit(12))
        return create_benchmark_figure(latest_runs, theme=theme or "dark")
