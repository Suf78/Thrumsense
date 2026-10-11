from dash import html, dcc
import dash_bootstrap_components as dbc
from app.services import ALL_SENSORS

def create_top_bar() -> html.Div:
    """Top bar with brand logo, controls, sensor filter, and replay engine toggles (DESIGN.md §5)."""
    return html.Div(
        className="d-flex justify-content-between align-items-center mb-4 pb-3 border-bottom flex-wrap gap-2",
        style={"borderColor": "var(--border)"},
        children=[
            html.Div(
                className="d-flex align-items-center gap-2",
                children=[
                    html.Img(src="/assets/logo.png", height="34px", className="me-1 rounded", style={"objectFit": "contain"}),
                    html.H4("Thrumsense", className="mb-0 fw-bold", style={"color": "var(--primary)"}),
                    html.Span("IoT Observability Control Room", className="text-muted small ms-2 d-none d-md-inline"),
                ]
            ),
            html.Div(
                className="d-flex align-items-center gap-2 flex-wrap",
                children=[
                    html.Div(
                        style={"width": "190px"},
                        children=[
                            dcc.Dropdown(
                                id="sensor-select",
                                options=[{"label": s, "value": s} for s in ALL_SENSORS],
                                value="PT08.S1(CO)",
                                clearable=False,
                                className="dash-dropdown",
                            )
                        ]
                    ),
                    html.Div(
                        style={"width": "150px"},
                        children=[
                            dcc.Dropdown(
                                id="range-select",
                                options=[
                                    {"label": "Trailing 24h", "value": "24h"},
                                    {"label": "Trailing 7d", "value": "7d"},
                                    {"label": "Trailing 30d", "value": "30d"},
                                ],
                                value="7d",
                                clearable=False,
                                className="dash-dropdown",
                            )
                        ]
                    ),
                    dbc.ButtonGroup([
                        dbc.Button([
                            html.Img(src="/assets/icons/play.png", height="14px", className="me-1"),
                            "Play"
                        ], id="btn-play", color="primary", size="sm"),
                        dbc.Button([
                            html.Img(src="/assets/icons/pause.png", height="14px", className="me-1"),
                            "Pause"
                        ], id="btn-pause", color="secondary", size="sm"),
                        dbc.Button([
                            html.Img(src="/assets/icons/rewind.png", height="14px", className="me-1"),
                            "Reset"
                        ], id="btn-reset", color="dark", size="sm"),
                    ]),
                    dbc.ButtonGroup([
                        dbc.Button("1×", id="btn-speed-1", size="sm", outline=True, color="info"),
                        dbc.Button("10×", id="btn-speed-10", size="sm", outline=True, color="info"),
                        dbc.Button("60×", id="btn-speed-60", size="sm", outline=True, color="info"),
                    ]),
                    dbc.Button("Theme", id="theme-toggle-btn", size="sm", outline=True, color="secondary"),
                ]
            )
        ]
    )

def create_kpi_strip() -> dbc.Row:
    """KPI cards strip: sensors ok, active alerts, data quality, fleet score (DESIGN.md §5)."""
    return dbc.Row(
        className="g-3 mb-4",
        children=[
            dbc.Col(
                dbc.Card(
                    className="bento-card",
                    children=[
                        html.Span("Sensors Healthy", className="text-muted small text-uppercase fw-bold"),
                        html.Div(id="kpi-sensors-ok", className="kpi-value text-success mt-2", children="-- / --"),
                    ]
                ),
                width=12, sm=6, md=3,
            ),
            dbc.Col(
                dbc.Card(
                    className="bento-card",
                    children=[
                        html.Span("Active Alerts (24h)", className="text-muted small text-uppercase fw-bold"),
                        html.Div(id="kpi-alerts-count", className="kpi-value text-warning mt-2", children="--"),
                    ]
                ),
                width=12, sm=6, md=3,
            ),
            dbc.Col(
                dbc.Card(
                    className="bento-card",
                    children=[
                        html.Span("Data Quality", className="text-muted small text-uppercase fw-bold"),
                        html.Div(id="kpi-data-quality", className="kpi-value mt-2", style={"color": "var(--primary)"}, children="--%"),
                    ]
                ),
                width=12, sm=6, md=3,
            ),
            dbc.Col(
                dbc.Card(
                    className="bento-card",
                    children=[
                        html.Span("Fleet Health Score", className="text-muted small text-uppercase fw-bold"),
                        html.Div(id="kpi-fleet-score", className="kpi-value mt-2", style={"color": "var(--accent)"}, children="-- / 100"),
                    ]
                ),
                width=12, sm=6, md=3,
            ),
        ]
    )

def create_main_layout() -> dbc.Container:
    """Full Bento dashboard grid structure."""
    return dbc.Container(
        fluid=True,
        className="py-3 px-4",
        children=[
            dcc.Interval(id="interval-timer", interval=1000, n_intervals=0),
            dcc.Store(id="theme-store", data="dark"),
            dcc.Store(id="control-signal-store", data=0),

            create_top_bar(),

            # Sim clock status banner
            html.Div(
                className="d-flex justify-content-between align-items-center mb-3 px-3 py-2 rounded flex-wrap gap-2",
                style={"backgroundColor": "var(--surface)", "border": "1px solid var(--border)"},
                children=[
                    html.Div(
                        className="d-flex align-items-center",
                        children=[
                            html.Img(src="/assets/icons/radio_telemetry.png", height="18px", className="me-2"),
                            html.Span("Simulated Stream Time: ", className="text-muted small me-1"),
                            html.Span(id="sim-clock-display", className="mono-text fw-bold", style={"color": "var(--primary)"}, children="--"),
                        ]
                    ),
                    html.Div([
                        html.Span("Cache Status: ", className="text-muted small me-1"),
                        html.Span(id="cache-status-badge", className="badge bg-secondary", children="Checking..."),
                    ])
                ]
            ),

            create_kpi_strip(),

            # Main Visuals Row: Time Series + Alerts & Health
            dbc.Row(
                className="g-3 mb-4",
                children=[
                    dbc.Col(
                        dbc.Card(
                            className="bento-card",
                            children=[
                                html.Div(
                                    className="d-flex justify-content-between align-items-center mb-2",
                                    children=[
                                        html.H5("Live Sensor Readings & Anomaly Envelope", className="mb-0"),
                                        html.Span(id="chart-unit-label", className="text-muted small"),
                                    ]
                                ),
                                dcc.Graph(id="timeseries-chart", config={"displayModeBar": False}, style={"height": "360px"}),
                            ]
                        ),
                        width=12, lg=8,
                    ),
                    dbc.Col(
                        dbc.Card(
                            className="bento-card",
                            style={"height": "100%", "maxHeight": "430px", "overflowY": "auto"},
                            children=[
                                html.H5("Live Alert Feed", className="mb-3"),
                                html.Div(id="alert-feed-container", children="No alerts recorded."),
                            ]
                        ),
                        width=12, lg=4,
                    ),
                ]
            ),

            # Sensor Health Grid
            dbc.Row(
                className="g-3 mb-4",
                children=[
                    dbc.Col(
                        dbc.Card(
                            className="bento-card",
                            children=[
                                html.H5("Fleet Sensor Health Grid (0 - 100)", className="mb-3"),
                                html.Div(id="sensor-health-grid", className="d-flex flex-wrap gap-2"),
                            ]
                        ),
                        width=12,
                    )
                ]
            ),

            # Bottom Tabs: Benchmark Lab
            dbc.Tabs(
                id="main-tabs",
                active_tab="tab-benchmark",
                children=[
                    dbc.Tab(
                        label="Benchmark Lab",
                        tab_id="tab-benchmark",
                        children=[
                            dbc.Card(
                                className="bento-card mt-3",
                                children=[
                                    html.Div(
                                        className="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2",
                                        children=[
                                            html.Div([
                                                html.H5("In-App Latency Benchmark Suite", className="mb-1"),
                                                html.P(
                                                    "Empirical comparison: No-Index (C1) vs Index (C2) vs Cache-Miss (C3) vs Cache-Hit (C4)",
                                                    className="text-muted small mb-0",
                                                ),
                                            ]),
                                            dbc.Button("Run Benchmark Suite (10 runs)", id="btn-run-benchmark", color="primary", size="sm"),
                                        ]
                                    ),
                                    dcc.Loading(
                                        id="benchmark-loading",
                                        type="circle",
                                        children=dcc.Graph(id="benchmark-chart", config={"displayModeBar": False}, style={"height": "340px"})
                                    )
                                ]
                            )
                        ]
                    )
                ]
            )
        ]
    )
