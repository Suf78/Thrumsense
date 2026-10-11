import logging
from pathlib import Path
import dash
import dash_bootstrap_components as dbc

from app.config import DASH_HOST, DASH_PORT, DASH_DEBUG, REPLAY_IN_PROCESS, BASE_DIR
from app.ui.layout import create_main_layout
from app.ui.callbacks import register_callbacks
from app.replay import replay_engine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Explicit assets folder pointing to BASE_DIR / 'assets'
ASSETS_PATH = str(BASE_DIR / "assets")

app = dash.Dash(
    __name__,
    title="Thrumsense — Real-Time IoT Sensor Monitoring",
    assets_folder=ASSETS_PATH,
    external_stylesheets=[dbc.themes.DARKLY],
    suppress_callback_exceptions=True,
)

# Attach layout and callbacks
app.layout = create_main_layout()
register_callbacks(app)

if __name__ == "__main__":
    logger.info("Starting Thrumsense Dashboard from %s...", ASSETS_PATH)
    if REPLAY_IN_PROCESS:
        logger.info("Starting Replay Engine background worker thread...")
        replay_engine.start_background()

    app.run(
        host=DASH_HOST,
        port=DASH_PORT,
        debug=DASH_DEBUG,
    )
