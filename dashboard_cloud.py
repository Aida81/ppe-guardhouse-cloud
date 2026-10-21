"""PPE Guardhouse Cloud V2: CCTV-first industrial dashboard.

Server-side Jetson API requests; authenticated access; no credentials in the client.
"""
import hashlib
import hmac
import time
from urllib.parse import quote, urlsplit

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="PPE Guardhouse | Live Control", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
:root {color-scheme: dark;}
.stApp {background: radial-gradient(ellipse at 82% -15%, rgba(27,112,67,.22), transparent 42%),
                 linear-gradient(145deg,#09130f 0%,#0b1211 46%,#101816 100%);
        color:#e8f4eb;}
[data-testid="stHeader"] {background:transparent;}
.block-container {max-width:1500px; padding-top:1.35rem; padding-bottom:3rem;}
[data-testid="stSidebar"] {background:#0d1a15;}
h1,h2,h3 {letter-spacing:-.035em;}
h1 {font-size:clamp(1.8rem,3vw,2.65rem)!important;}
h3 {font-size:1.1rem!important;}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:rgba(112,185,134,.22)!important;
 background:rgba(14,29,22,.70); border-radius:16px!important;}
[data-testid="stImage"] img {border-radius:12px;}
[data-testid="stDataFrame"] {border:1px solid rgba(102,161,116,.20);border-radius:12px;overflow:hidden;}
[data-testid="stAlert"] {border-radius:10px;}
[data-testid="stToggle"] label {font-weight:600;}
[data-testid="stButton"] button[kind="primary"] {background:#287d4e; border-color:#399963;}
[data-testid="stButton"] button:hover {border-color:#66d18d;}
[data-testid="stCaptionContainer"] {color:#a2b8a9;}
.ppe-kicker {color:#6bd68e;font-size:.74rem;font-weight:800;letter-spacing:.20em;margin-bottom:.3rem;}
.ppe-title {font-size:clamp(1.8rem,3vw,2.6rem);font-weight:800;letter-spacing:-.045em;
 color:#f2fff5;line-height:1.12;margin:0 0 .35rem 0;}
.ppe-subtitle {font-size:.88rem;color:#9bb6a3;margin-bottom:1.2rem;}
.ppe-chip {display:inline-block;padding:.30rem .75rem;border:1px solid #346b4a;border-radius:100px;
 color:#8ce8a9;background:#12291b;font-size:.75rem;font-weight:700;letter-spacing:.06em;}
.ppe-section {color:#e7f5e9;font-size:1.10rem;font-weight:750;letter-spacing:-.02em;margin:0 0 .25rem 0;}
.ppe-eyebrow {font-size:.76rem;color:#92b49c;letter-spacing:.035em;}
.ppe-footnote {color:#82998a;font-size:.74rem;}
</style>
""", unsafe_allow_html=True)


def check_login():
    try:
        username = str(st.secrets["AUTH_USERNAME"])
        salt = bytes.fromhex(str(st.secrets["AUTH_PASSWORD_SALT"]))
        expected_hash = bytes.fromhex(str(st.secrets["AUTH_PASSWORD_HASH"]))
        if not username or len(salt) < 16 or len(expected_hash) != 32:
            raise ValueError("Invalid login configuration")
    except (KeyError, ValueError, TypeError):
        st.error("Login configuration missing. Check AUTH_USERNAME, AUTH_PASSWORD_SALT and AUTH_PASSWORD_HASH in Streamlit Secrets.")
        st.stop()

    if st.session_state.get("ppe_authenticated", False):
        with st.sidebar:
            st.success("● Authorized session")
            st.caption("PPE Guardhouse Control")
            if st.button("Log out", use_container_width=True):
                st.session_state["ppe_authenticated"] = False
                st.rerun()
        return

    st.markdown('<div class="ppe-kicker">SECURE ACCESS / PPE CONTROL</div>', unsafe_allow_html=True)
    st.markdown('<div class="ppe-title">PPE Guardhouse</div>', unsafe_allow_html=True)
    st.caption("Sign in to access CCTV preview and safety violation records.")
    if time.monotonic() < st.session_state.get("ppe_locked_until", 0):
        st.error("Too many attempts. Please wait five minutes.")
        st.stop()
    with st.form("login", clear_on_submit=True):
        supplied_user = st.text_input("Username")
        supplied_password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", use_container_width=True, type="primary")
    if submitted:
        candidate = hashlib.pbkdf2_hmac("sha256", supplied_password.encode("utf-8"), salt, 310_000)
        user_ok = hmac.compare_digest(supplied_user.encode("utf-8"), username.encode("utf-8"))
        pass_ok = hmac.compare_digest(candidate, expected_hash)
        if user_ok and pass_ok:
            st.session_state["ppe_authenticated"] = True
            st.session_state["ppe_failed_attempts"] = 0
            st.rerun()
        attempts = st.session_state.get("ppe_failed_attempts", 0) + 1
        st.session_state["ppe_failed_attempts"] = attempts
        if attempts >= 5:
            st.session_state["ppe_locked_until"] = time.monotonic() + 300
            st.session_state["ppe_failed_attempts"] = 0
            st.error("Too many attempts. Please wait five minutes.")
        else:
            st.error("Invalid username or password.")
    st.stop()


check_login()

try:
    BASE_URL = str(st.secrets["JETSON_API_URL"]).rstrip("/")
    TOKEN = str(st.secrets["JETSON_API_TOKEN"])
    parsed = urlsplit(BASE_URL)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not TOKEN:
        raise ValueError("JETSON_API_URL must be a clean HTTPS URL; API token must be nonempty")
except (KeyError, ValueError):
    st.error("Jetson API configuration missing or invalid. Check Streamlit Secrets.")
    st.stop()


def api_get(path, params=None):
    response = requests.get(BASE_URL + path, headers={"Authorization": "Bearer " + TOKEN},
                            params=params, timeout=9)
    response.raise_for_status()
    return response


def get_json(path, params=None):
    return api_get(path, params).json()


def get_jpeg(path):
    response = api_get(path)
    if "image/jpeg" not in response.headers.get("content-type", "").lower():
        raise ValueError("Expected JPEG response")
    return response.content


st.markdown('<div class="ppe-kicker">INDUSTRIAL SAFETY INTELLIGENCE / CONTROL ROOM</div>', unsafe_allow_html=True)
st.markdown('<div class="ppe-title">PPE Guardhouse <span style="color:#6bd68e">Live Control</span></div>', unsafe_allow_html=True)
st.markdown('<div class="ppe-subtitle">Jetson Orin &nbsp;•&nbsp; YOLOv12 &nbsp;•&nbsp; CCTV Guardhouse &nbsp;•&nbsp; Secure cloud preview</div>', unsafe_allow_html=True)

# CCTV is intentionally first and takes the full content width.
with st.container(border=True):
    title_col, toggle_col = st.columns([4, 1], vertical_alignment="center")
    with title_col:
        st.markdown('<div class="ppe-section">◉ &nbsp; LIVE CCTV / GUARDHOUSE</div>', unsafe_allow_html=True)
        st.markdown('<div class="ppe-eyebrow">PRIMARY MONITOR &nbsp;•&nbsp; Near-live JPEG preview, not continuous video</div>', unsafe_allow_html=True)
    with toggle_col:
        camera_enabled = st.toggle("Camera preview", value=True)

    @st.fragment(run_every="2s")
    def camera_panel():
        if not camera_enabled:
            st.info("Camera preview paused. PPE detection continues on Jetson.")
            return
        try:
            st.image(get_jpeg("/api/snapshot"), width="stretch")
        except (requests.RequestException, ValueError):
            st.warning("CCTV preview unavailable. Jetson detector may still be running.")

    camera_panel()

st.write("")

# Graph under the camera, using today's category totals from the existing API.
with st.container(border=True):
    st.markdown('<div class="ppe-section">▥ &nbsp; VIOLATION ANALYTICS</div>', unsafe_allow_html=True)
    st.markdown('<div class="ppe-eyebrow">TODAY\'S DETECTIONS &nbsp;•&nbsp; Counts are category occurrences, not unique workers</div>', unsafe_allow_html=True)

    @st.fragment(run_every="15s")
    def analytics_panel():
        try:
            status = get_json("/api/status")
            today = status["today"]
            counts = today.get("categories", {})
            chart = pd.DataFrame({
                "Violation": ["No Safety Helmet", "No Vest", "No Safety Shoe"],
                "Count": [int(counts.get("No Safety Helmet", 0)),
                          int(counts.get("No Vest", 0)),
                          int(counts.get("No Safety Shoe", 0))],
            }).set_index("Violation")
            if status.get("detector_running"):
                st.markdown('<span class="ppe-chip">● DETECTOR ONLINE</span>', unsafe_allow_html=True)
            else:
                st.warning("Detector offline or stopped")
            st.bar_chart(chart, y="Count", color="#52b979", horizontal=True, height=230)
            st.caption(f"Jetson date: {today.get('date', 'N/A')} · Alert groups: {today.get('alert_groups', 0)} · Flagged records: {today.get('flagged_records', 0)}")
        except (requests.RequestException, ValueError, KeyError, TypeError):
            st.warning("Violation analytics unavailable right now.")

    analytics_panel()

st.write("")

# Operational information only: recent table and latest JPEG evidence, no history page.
left, right = st.columns([1.15, 1], gap="large")
with left:
    with st.container(border=True):
        st.markdown('<div class="ppe-section">≡ &nbsp; RECENT VIOLATIONS</div>', unsafe_allow_html=True)
        st.markdown('<div class="ppe-eyebrow">LATEST EVENTS &nbsp;•&nbsp; Full notification history is available in Telegram</div>', unsafe_allow_html=True)

        @st.fragment(run_every="15s")
        def violations_panel():
            try:
                events = get_json("/api/events", {"limit": 15}).get("events", [])
            except (requests.RequestException, ValueError, KeyError, TypeError):
                st.warning("Could not load recent violations.")
                return
            if not events:
                st.info("No violation events recorded yet.")
                return
            rows = [{"Time": str(item.get("timestamp", "")),
                     "Violation": str(item.get("violations", "")).replace(";", ", ")}
                    for item in events[:10]]
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=370)

        violations_panel()

with right:
    with st.container(border=True):
        st.markdown('<div class="ppe-section">▣ &nbsp; LATEST EVIDENCE</div>', unsafe_allow_html=True)
        st.markdown('<div class="ppe-eyebrow">MOST RECENT EVIDENCE PHOTO &nbsp;•&nbsp; Video clips not yet supported by Jetson API</div>', unsafe_allow_html=True)

        @st.fragment(run_every="15s")
        def evidence_panel():
            try:
                events = get_json("/api/events", {"limit": 15}).get("events", [])
                latest = next((e for e in events if e.get("image_file")), None)
                if not latest:
                    st.info("No evidence image available yet.")
                    return
                filename = str(latest["image_file"])
                # URL-encode the filename so it cannot change the endpoint path.
                st.image(get_jpeg("/api/evidence/" + quote(filename, safe="")), width="stretch")
                st.caption(f"Captured: {latest.get('timestamp', 'N/A')} · {str(latest.get('violations', '')).replace(';', ', ')}")
            except (requests.RequestException, ValueError, KeyError, TypeError):
                st.warning("Latest evidence photo unavailable.")

        evidence_panel()

st.markdown('<div class="ppe-footnote">PPE GUARDHOUSE CLOUD V2 &nbsp;·&nbsp; Read-only monitor &nbsp;·&nbsp; Jetson processes CCTV locally &nbsp;·&nbsp; Authorized users only</div>', unsafe_allow_html=True)
