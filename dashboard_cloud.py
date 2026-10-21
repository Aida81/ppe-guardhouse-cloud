"""PPE Guardhouse Cloud: read-only private dashboard; no CCTV secrets in browser."""
from datetime import datetime
from urllib.parse import urlsplit

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='PPE Guardhouse Cloud', page_icon='👷', layout='wide')
st.markdown('''<style>
.block-container {max-width:1500px;padding-top:2rem}
[data-testid="stMetric"] {background:rgba(128,128,128,.08);padding:.6rem;border-radius:10px}
</style>''', unsafe_allow_html=True)

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
