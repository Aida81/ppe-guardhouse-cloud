"""PPE Guardhouse Cloud: authenticated read-only dashboard; no CCTV secrets in browser."""
from datetime import datetime
import hashlib
import hmac
import time
from urllib.parse import urlsplit

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='PPE Guardhouse Cloud', page_icon='👷', layout='wide')
st.markdown('''<style>
.block-container {max-width:1500px;padding-top:2rem}
[data-testid="stMetric"] {background:rgba(128,128,128,.08);padding:.6rem;border-radius:10px}
</style>''', unsafe_allow_html=True)

# Gate ALL CCTV, events and API requests behind a login check.
# Password is verified using PBKDF2-HMAC-SHA256; no plaintext password in GitHub.
def check_login():
    try:
        username = str(st.secrets['AUTH_USERNAME'])
        salt = bytes.fromhex(str(st.secrets['AUTH_PASSWORD_SALT']))
        expected_hash = bytes.fromhex(str(st.secrets['AUTH_PASSWORD_HASH']))
        if len(salt) < 16 or len(expected_hash) != 32 or not username:
            raise ValueError('Invalid authentication configuration')
    except (KeyError, ValueError, TypeError):
        st.error('Login is not configured. Set AUTH_USERNAME, AUTH_PASSWORD_SALT and AUTH_PASSWORD_HASH in Streamlit Secrets.')
        st.stop()

    if st.session_state.get('ppe_authenticated', False):
        with st.sidebar:
            st.success('Signed in')
            if st.button('Log out', use_container_width=True):
                st.session_state['ppe_authenticated'] = False
                st.rerun()
        return

    st.title('🔐 PPE Guardhouse Login')
    st.caption('Authorized personnel only · CCTV and worker safety records')
    locked_until = st.session_state.get('ppe_locked_until', 0.0)
    if time.monotonic() < locked_until:
        st.error('Too many attempts. Please wait five minutes before trying again.')
        st.stop()

    with st.form('ppe_login_form', clear_on_submit=True):
        supplied_user = st.text_input('Username')
        supplied_password = st.text_input('Password', type='password')
        submitted = st.form_submit_button('Sign in', use_container_width=True)

    if submitted:
        candidate = hashlib.pbkdf2_hmac('sha256', supplied_password.encode('utf-8'), salt, 310_000)
        # Compare both credentials without a short-circuit on password validation.
        user_ok = hmac.compare_digest(supplied_user.encode('utf-8'), username.encode('utf-8'))
        pass_ok = hmac.compare_digest(candidate, expected_hash)
        if user_ok and pass_ok:
            st.session_state['ppe_authenticated'] = True
            st.session_state['ppe_failed_attempts'] = 0
            st.rerun()
        else:
            attempts = st.session_state.get('ppe_failed_attempts', 0) + 1
            st.session_state['ppe_failed_attempts'] = attempts
            if attempts >= 5:
                st.session_state['ppe_locked_until'] = time.monotonic() + 300
                st.session_state['ppe_failed_attempts'] = 0
                st.error('Too many attempts. Please wait five minutes before trying again.')
            else:
                st.error('Invalid username or password.')
    st.stop()


check_login()

try:
    BASE_URL = str(st.secrets['JETSON_API_URL']).rstrip('/')
    TOKEN = str(st.secrets['JETSON_API_TOKEN'])
    u = urlsplit(BASE_URL)
    if u.scheme != 'https' or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError('JETSON_API_URL must be a clean HTTPS URL')
except (KeyError, ValueError) as exc:
    st.error(f'Configure JETSON_API_URL and JETSON_API_TOKEN in Streamlit Secrets. {exc}')
    st.stop()


def get_json(path, params=None):
    response = requests.get(BASE_URL + path,
                            headers={'Authorization': 'Bearer ' + TOKEN},
                            params=params, timeout=7)
    response.raise_for_status()
    return response.json()


def get_image(path):
    response = requests.get(BASE_URL + path,
                            headers={'Authorization': 'Bearer ' + TOKEN}, timeout=7)
    response.raise_for_status()
    if 'image/jpeg' not in response.headers.get('content-type', ''):
        raise ValueError('Expected JPEG image')
    return response.content


st.title('👷 PPE Guardhouse Cloud Monitoring')
st.caption('Jetson Orin · YOLOv12 · Read-only cloud dashboard · Camera refresh ~1 FPS')
left, right = st.columns([1, 2.2], gap='large')

with left:
    @st.fragment(run_every='5s')
    def summary():
        try:
            data = get_json('/api/status')
        except (requests.RequestException, ValueError) as exc:
            st.error(f'Jetson not reachable: {type(exc).__name__}')
            return
        st.success('● Detector RUNNING') if data['detector_running'] else st.warning('● Detector STOPPED')
        today = data['today']
        a, b = st.columns(2)
        a.metric('Alert groups', today['alert_groups'])
        b.metric('Flagged records', today['flagged_records'])
        counts = today['categories']
        a, b = st.columns(2)
        a.metric('No Helmet', counts.get('No Safety Helmet', 0))
        b.metric('No Vest', counts.get('No Vest', 0))
        a.metric('No Safety Shoe', counts.get('No Safety Shoe', 0))
        b.metric('Disk used', f"{data['disk_used_percent']}%")
        st.caption(f"Jetson date: {today['date']} · Free disk: {data['disk_free_gb']} GB")
        st.caption('Counts refer to CSV events, not unique workers.')
        st.markdown('#### Recent violations')
        try:
            events = get_json('/api/events', {'limit': 30})['events']
        except (requests.RequestException, ValueError, KeyError):
            st.warning('Could not load events')
            return
        if not events:
            st.info('No violation records yet.')
            return
        rows = [{'Time': x['timestamp'], 'Violations': x['violations'].replace(';', ', ')}
                for x in events[:10]]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch', height=265)
        with st.expander('Latest evidence photo'):
            first = next((x for x in events if x.get('image_file')), None)
            if first:
                try:
                    st.image(get_image('/api/evidence/' + first['image_file']), width='stretch')
                except (requests.RequestException, ValueError):
                    st.warning('Evidence unavailable')
            else:
                st.info('No evidence photos yet.')
    summary()

with right:
    st.subheader('Live CCTV · Guardhouse')
    st.caption('Near-live preview: JPEG snapshot every ~2 seconds, not 25–30 FPS video.')
    enabled = st.toggle('Camera preview', value=True)
    @st.fragment(run_every='2s')
    def camera():
        if not enabled:
            st.info('Preview paused. Jetson detector continues running.')
            return
        try:
            st.image(get_image('/api/snapshot'), width='stretch')
        except (requests.RequestException, ValueError):
            st.warning('Camera unavailable or Jetson connection interrupted.')
    camera()
