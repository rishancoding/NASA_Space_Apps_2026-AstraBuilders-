"""FireSafe: entry point.  Run:  .venv/bin/streamlit run app/main.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

st.set_page_config(page_title="FireSafe - NASA microgravity fire data", page_icon=":material/local_fire_department:",
                   layout="wide")

PAGES = Path(__file__).resolve().parent / "pages"
nav = st.navigation([
    st.Page(PAGES / "advisor.py", title="Material Advisor", icon=":material/science:", default=True),
    st.Page(PAGES / "assistant.py", title="Research Assistant", icon=":material/forum:"),
    st.Page(PAGES / "predictor.py", title="Combustion Predictor", icon=":material/tune:"),
    st.Page(PAGES / "model_card.py", title="Model Performance", icon=":material/monitoring:"),
    st.Page(PAGES / "explorer.py", title="NASA Data Explorer", icon=":material/travel_explore:"),
])
with st.sidebar:
    st.markdown("**FireSafe**")
    st.caption("Built on NASA's fire experiments in orbit (BASS, BASS-II, Saffire, FLEX). Every number comes from "
               "NASA's data or our trained model; the AI only explains them. Outcome labels were verified by the project team.")
nav.run()
