from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
import pandas as pd

# Color tokens mapping
COLORS = {
    "primary": "#2DD4BF",
    "accent": "#818CF8",
    "ok": "#34D399",
    "warn": "#FBBF24",
    "critical": "#F87171",
    "info": "#60A5FA",
    "surface": "#111A2E",
    "border": "#22304F",
    "text": "#E6EDF7",
    "text_muted": "#8FA1BF",
}

def create_timeseries_figure(
    series_data: List[Dict[str, Any]],
    sensor_id: str,
    thresholds: Dict[str, float],
    alerts: List[Dict[str, Any]],
    theme: str = "dark"
) -> go.Figure:
    """
    Main time-series chart with threshold band and anomaly markers (DESIGN.md §2).
    """
    fig = go.Figure()

    if not series_data:
        fig.update_layout(
            template="plotly_dark" if theme == "dark" else "plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            annotations=[{
                "text": "No data available in this time range",
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 14, "color": COLORS["text_muted"]}
            }]
        )
        return fig

    df = pd.DataFrame(series_data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values("timestamp")

    # Main series line
    fig.add_trace(go.Scatter(
        x=df["timestamp"],
        y=df["value"],
        mode="lines",
        name=sensor_id,
        line={"color": COLORS["primary"], "width": 2},
        connectgaps=False,
    ))

    # Static threshold boundaries
    low = thresholds.get("low")
    high = thresholds.get("high")

    if low is not None and low != float("-inf"):
        fig.add_hline(
            y=low,
            line_dash="dash",
            line_color=COLORS["warn"],
            annotation_text=f"p1 ({low:.1f})",
            annotation_position="bottom right"
        )
    if high is not None and high != float("inf"):
        fig.add_hline(
            y=high,
            line_dash="dash",
            line_color=COLORS["warn"],
            annotation_text=f"p99 ({high:.1f})",
            annotation_position="top right"
        )

    # Anomaly markers
    sensor_alerts = [a for a in alerts if a.get("sensor_id") == sensor_id]
    if sensor_alerts:
        alert_times = [pd.to_datetime(a["timestamp"]) for a in sensor_alerts]
        alert_vals = [a.get("value") for a in sensor_alerts]
        alert_texts = [f"{a.get('type')}: {a.get('explanation')}" for a in sensor_alerts]

        fig.add_trace(go.Scatter(
            x=alert_times,
            y=alert_vals,
            mode="markers",
            name="Anomaly",
            marker={"color": COLORS["critical"], "size": 8, "symbol": "circle-open", "line": {"width": 2}},
            text=alert_texts,
            hoverinfo="x+y+text"
        ))

    fig.update_layout(
        template="plotly_dark" if theme == "dark" else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 20, "t": 30, "b": 40},
        xaxis={"showgrid": True, "gridcolor": COLORS["border"]},
        yaxis={"showgrid": True, "gridcolor": COLORS["border"]},
        legend={"orientation": "h", "y": 1.1, "x": 0.0},
        font={"family": "Inter, sans-serif", "color": COLORS["text"]},
    )
    return fig

def create_benchmark_figure(benchmark_results: List[Dict[str, Any]], theme: str = "dark") -> go.Figure:
    """Grouped bar chart showing mean latency by query and condition (TECHNICAL §5.10)."""
    fig = go.Figure()
    if not benchmark_results:
        fig.update_layout(
            template="plotly_dark" if theme == "dark" else "plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            annotations=[{
                "text": "Click 'Run Benchmark Suite' to measure real database timings",
                "xref": "paper",
                "yref": "paper",
                "showarrow": False,
                "font": {"size": 14, "color": COLORS["text_muted"]}
            }]
        )
        return fig

    df = pd.DataFrame(benchmark_results)
    conditions = df["condition"].unique()

    color_map = {
        "C1_no_index": "#F87171",
        "C2_index_no_cache": "#FBBF24",
        "C3_index_cache_miss": "#60A5FA",
        "C4_index_cache_hit": "#34D399",
    }

    for cond in conditions:
        sub_df = df[df["condition"] == cond]
        fig.add_trace(go.Bar(
            name=cond,
            x=sub_df["query"],
            y=sub_df["mean_ms"],
            marker_color=color_map.get(cond, COLORS["primary"]),
            text=[f"{v:.2f} ms" for v in sub_df["mean_ms"]],
            textposition="auto",
        ))

    fig.update_layout(
        barmode="group",
        template="plotly_dark" if theme == "dark" else "plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 40, "r": 20, "t": 30, "b": 40},
        xaxis={"title": "Query Type", "gridcolor": COLORS["border"]},
        yaxis={"title": "Mean Execution Time (ms)", "gridcolor": COLORS["border"]},
        legend={"orientation": "h", "y": 1.15, "x": 0.0},
        font={"family": "Inter, sans-serif", "color": COLORS["text"]},
    )
    return fig
