# VP Demo Runbook

**Purpose**

Use this runbook to start and show the local dashboard safely for a VP/demo audience.
This is basic local/demo authentication, not enterprise auth.

**Available Dashboards**

- Internal Order Rekap / Order Material Tracking
- Sales Order Dashboard
- Internal Order Dashboard

**Required Environment Variables**

Create a local `.env` file with these values:

```env
DASHBOARD_USERNAME=vp_demo
DASHBOARD_PASSWORD=change_this_password
SESSION_SECRET=change_this_long_random_secret
```

Notes:
- Do not commit real credentials.
- Keep `.env` local only.
- Use `.env.example` as the placeholder reference.

**Run Locally**

```bash
python -m uvicorn src.api:app --host 127.0.0.1 --port 8000
```

Open:

- http://127.0.0.1:8000/login

**Run on LAN / Hotspot**

1. Start the app on the demo machine.
2. Find the machine IP on the current Wi-Fi or hotspot network.
3. Open the same port from another device, for example:

```text
http://<demo-ip>:8000/login
```

4. Make sure the device is on the same network and the firewall allows port 8000.

**Login / Logout Flow**

1. Open `/login`.
2. Sign in with the local demo username and password.
3. You are redirected to `/dashboard/internal-order-rekap`.
4. Use `/logout` to clear the session.
5. After logout, dashboard routes should send you back to `/login`.

**Recommended Demo Route Order**

1. `/dashboard/internal-order-rekap`
2. `/dashboard/sales-orders`
3. `/dashboard/internal-orders`

**Default Test Internal Order**

- `426IO026`

**Standalone / Direct Sales Order Example**

- `4250385`

**What Not to Claim**

- Not final profitability
- Not accounting gross profit
- Not COGS
- Not AR/payment
- Material Search is not implemented yet
- Sales Order Perspective for Order Material Tracking supports linked IO and standalone/direct SO/JO material chain context, not product allocation

**Troubleshooting**

- Hard refresh if CSS or JS looks stale.
- Check the uvicorn terminal for errors.
- Confirm the environment variables are set correctly.
- Confirm the device is on the same Wi-Fi or hotspot network.
- If the login page fails, verify the app is running on port 8000.
