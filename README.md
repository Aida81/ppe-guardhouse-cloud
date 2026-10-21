# PPE Guardhouse Cloud V1 · Free-tier edition

## Architecture
Jetson detector V4.1 and existing dashboard V5 remain unchanged. A separate read-only Flask API on the Jetson exposes status, events, evidence, and a low-frame-rate camera snapshot. Tailscale Funnel forwards the API over HTTPS. A **private** Streamlit Community Cloud app fetches the API using server-side Streamlit Secrets, so the API token never appears in the browser.

**Cost:** No paid cloud components required under available free plans, subject to plan usage limits. Electricity and internet are not free. The preview is ~0.5–1 FPS snapshots, not smooth real-time video. Tailscale Funnel publishes an HTTPS endpoint publicly; the API bearer token is its access barrier. Only proceed with plantation approval and appropriate handling of worker CCTV data.

## Step 1: Jetson API setup (SSH)

Copy `jetson_api.py` from this package to `/home/aida/deploy/jetson_api.py`. **Do not replace detector_v41.py or dashboard_v5_fixed.py.**

```bash
cd /home/aida/deploy
/home/aida/ppe_gpu/bin/python -m pip install 'Flask>=3,<4'
# Generate a 48-byte random secret. Do not post it in chat.
TOKEN=$(/usr/bin/python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
printf 'PPE_CLOUD_API_TOKEN=%s\nPPE_CLOUD_FPS=1\n' "$TOKEN" > /home/aida/deploy/cloud_api.env
chmod 600 /home/aida/deploy/cloud_api.env
unset TOKEN
sudo cp /home/aida/deploy/systemd/ppe-cloud-api.service /etc/systemd/system/ppe-cloud-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now ppe-cloud-api.service
systemctl is-active ppe-cloud-api.service
```

Place the service template at `/home/aida/deploy/systemd/ppe-cloud-api.service` first, or copy it directly from wherever it was transferred. The `ppe.env` file must contain the existing `RTSP_URL`. The service listens on 127.0.0.1:8765 only.

### Local test without exposing secrets

```bash
source /home/aida/deploy/cloud_api.env
curl -fsS -H "Authorization: Bearer $PPE_CLOUD_API_TOKEN" http://127.0.0.1:8765/api/status
unset PPE_CLOUD_API_TOKEN
```

## Step 2: Tailscale Funnel

Check the command and whether Funnel is available for the account and tailnet:

```bash
tailscale version
tailscale funnel --help
tailscale funnel --bg --https=443 http://127.0.0.1:8765
tailscale funnel status
```

Tailscale may ask to enable Funnel in the admin console. **Do not enable it before confirming plantation authorization to expose a CCTV-backed API to the public internet.** Funnel HTTPS is publicly reachable; it is not private Tailscale Serve. The API requires a long random token for every endpoint. Avoid exposing port 8505 or 554.

The output provides a `https://...ts.net` address. Do not append `/api/status` in Streamlit Secrets.

## Step 3: Streamlit Community Cloud

Make a **private** GitHub repository and upload only `dashboard_cloud.py` and `requirements.txt` (copy the contents of `requirements-cloud.txt` to `requirements.txt`). Do not upload detector, credentials, evidence, CSV, or `cloud_api.env`.

Deploy on https://share.streamlit.io/ using entrypoint `dashboard_cloud.py`. Configure app privacy as private and invite only authorized viewers. In App settings > Secrets:

```toml
JETSON_API_URL = "https://YOUR-JETSON.YOUR-TAILNET.ts.net"
JETSON_API_TOKEN = "YOUR_PRIVATE_TOKEN_FROM_JETSON"
```

Save secrets in the platform UI, **never** in GitHub. The browser receives only rendered images/data from Streamlit, not the bearer token.

## Step 4: Verify

- Jetson detector service stays active and continues sending Telegram alerts.
- Jetson API returns `detector_running=true` and valid counts.
- Funnel URL requires token; requests without a token should receive HTTP 401.
- Streamlit app displays metrics, events, and refreshed snapshots.
- Disable Funnel if access is no longer required: `sudo tailscale funnel --https=443 off` (verify syntax with installed Tailscale version).

## Security / limitations

- Treat the Funnel URL as internet-accessible. Keep a random secret and rotate it if exposed. Never share it in screenshots.
- Approximate face blur in detector evidence is not guaranteed anonymization; raw preview can contain identifiable people. Ensure explicit authorization and privacy controls.
- Community Cloud may sleep when idle; the Jetson detector remains independent.
- Preview is a low-FPS image refresh. A true WebRTC 25 FPS feed requires a different streaming setup and NAT/TURN testing, which may not be reliably free.
- No Supabase needed; records and evidence remain on the Jetson. If the Jetson or internet connection is offline, the cloud dashboard cannot show current data.
- `jetson_api.py` reads the CSV on every status request, suitable for small/medium datasets; optimize later if records become very large.
