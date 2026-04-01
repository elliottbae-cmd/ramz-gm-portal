"""
Ram-Z GM Revenue Band Selection Portal
---------------------------------------
GMs receive an email with a unique token link. They land here,
see their store's performance data, select a revenue band,
and submit. The submission routes to their DM for approval.
"""

import streamlit as st
from datetime import datetime, timedelta
from supabase import create_client

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Ram-Z Revenue Band Selection",
    page_icon="🍔",
    layout="centered",
)

# ---------------------------------------------------------------------------
# Supabase connection (cached)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

sb = get_supabase()

# ---------------------------------------------------------------------------
# Ram-Z branding CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    :root {
        --ramz-navy: #2B3A4E;
        --ramz-gold: #C49A5C;
    }
    .main-header {
        text-align: center;
        padding: 1rem 0 0.5rem;
    }
    .main-header img {
        max-width: 200px;
        margin-bottom: 0.5rem;
    }
    .store-title {
        color: var(--ramz-navy);
        font-size: 1.8rem;
        font-weight: 700;
        text-align: center;
        margin-bottom: 0.2rem;
    }
    .week-label {
        color: var(--ramz-gold);
        font-size: 1.1rem;
        text-align: center;
        margin-bottom: 1.5rem;
    }
    .data-card {
        background: #F5F0EB;
        border-radius: 8px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .data-card h4 {
        color: var(--ramz-navy);
        margin: 0 0 0.5rem 0;
        font-size: 1rem;
    }
    .metric-row {
        display: flex;
        justify-content: space-between;
        padding: 0.3rem 0;
        border-bottom: 1px solid #E0D5C9;
    }
    .metric-row:last-child {
        border-bottom: none;
    }
    .metric-label { color: #666; font-size: 0.9rem; }
    .metric-value { color: var(--ramz-navy); font-weight: 600; font-size: 0.9rem; }
    .success-box {
        background: #D6F0DA;
        border-radius: 8px;
        padding: 1.5rem;
        text-align: center;
        margin: 2rem 0;
    }
    .success-box h3 { color: #2E7D32; margin-bottom: 0.5rem; }
    .expired-box {
        background: #FFDADA;
        border-radius: 8px;
        padding: 1.5rem;
        text-align: center;
        margin: 2rem 0;
    }
    .expired-box h3 { color: #C62828; margin-bottom: 0.5rem; }
    div[data-testid="stSelectbox"] label {
        color: var(--ramz-navy);
        font-weight: 600;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helper: format currency
# ---------------------------------------------------------------------------
def fmt_currency(val):
    if val is None:
        return "N/A"
    return f"${val:,.0f}"


def fmt_minutes(seconds):
    if seconds is None:
        return "N/A"
    mins = seconds / 60
    return f"{mins:.1f} min"


# ---------------------------------------------------------------------------
# Token validation
# ---------------------------------------------------------------------------
token = st.query_params.get("token", None)

if not token:
    st.markdown("""
    <div class="expired-box">
        <h3>No Access Token</h3>
        <p>Please use the link from your email to access this page.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Look up the submission record by token
resp = sb.table("rev_band_submissions").select("*").eq("token", token).execute()

if not resp.data:
    st.markdown("""
    <div class="expired-box">
        <h3>Invalid Link</h3>
        <p>This link is not valid. Please check your email for the correct link.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

submission = resp.data[0]
location_id = submission["location_id"]
week_start = submission["week_start"]
status = submission["status"]
token_expires = submission.get("token_expires_at")

# Check if already submitted
if status != "pending_gm":
    st.markdown("""
    <div class="success-box">
        <h3>Already Submitted</h3>
        <p>The revenue band for this week has already been submitted.
        If you need to make changes, please contact your DM.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# Check token expiration
if token_expires:
    try:
        exp_dt = datetime.fromisoformat(token_expires.replace("Z", "+00:00"))
        if datetime.now(exp_dt.tzinfo) > exp_dt:
            # Mark deadline as missed
            sb.table("rev_band_submissions").update({
                "gm_deadline_missed": True
            }).eq("token", token).execute()

            st.markdown("""
            <div class="expired-box">
                <h3>Link Expired</h3>
                <p>The deadline for this week's submission has passed.
                Please contact your DM.</p>
            </div>
            """, unsafe_allow_html=True)
            st.stop()
    except Exception:
        pass  # If we can't parse, allow access

# ---------------------------------------------------------------------------
# Load store info
# ---------------------------------------------------------------------------
store_resp = sb.table("reference_data").select("*").eq("location_id", location_id).execute()
if not store_resp.data:
    st.error("Store not found. Please contact your manager.")
    st.stop()

store = store_resp.data[0]
store_name = store["store_name"]
dm_name = store.get("dm", "Unknown")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="main-header">
    <div class="store-title">{store_name}</div>
    <div class="week-label">Revenue Band Selection — Week of {week_start}</div>
</div>
""", unsafe_allow_html=True)

st.divider()

# ---------------------------------------------------------------------------
# Load performance data
# ---------------------------------------------------------------------------

# --- Sales data ---
# Prior year same week
py_week_start = (datetime.strptime(week_start, "%Y-%m-%d") - timedelta(weeks=52)).strftime("%Y-%m-%d")
py_sales_resp = sb.table("store_sales").select("net_sales").eq(
    "location_id", location_id
).eq("week_start", py_week_start).execute()
py_sales = py_sales_resp.data[0]["net_sales"] if py_sales_resp.data else None

# Last 2 weeks of current year
ws_date = datetime.strptime(week_start, "%Y-%m-%d")
prev_weeks = []
for i in range(1, 3):
    pw = (ws_date - timedelta(weeks=i)).strftime("%Y-%m-%d")
    pw_resp = sb.table("store_sales").select("net_sales").eq(
        "location_id", location_id
    ).eq("week_start", pw).execute()
    if pw_resp.data:
        prev_weeks.append(pw_resp.data[0]["net_sales"])
    else:
        prev_weeks.append(None)

prev_week_1 = prev_weeks[0]  # most recent
prev_week_2 = prev_weeks[1]  # 2 weeks ago

# Average of last 2 weeks
valid_prev = [w for w in prev_weeks if w is not None]
avg_prev_2 = sum(valid_prev) / len(valid_prev) if valid_prev else None

# --- SoS data (last 4 weeks) ---
sos_data = []
for i in range(1, 5):
    sw = (ws_date - timedelta(weeks=i)).strftime("%Y-%m-%d")
    sos_resp = sb.table("store_sos").select("sos_seconds, sos_rank, total_stores").eq(
        "location_id", location_id
    ).eq("week_start", sw).execute()
    if sos_resp.data:
        sos_data.append(sos_resp.data[0])

avg_sos = None
if sos_data:
    sos_vals = [s["sos_seconds"] for s in sos_data if s.get("sos_seconds")]
    avg_sos = sum(sos_vals) / len(sos_vals) if sos_vals else None

last_sos_rank = sos_data[0].get("sos_rank") if sos_data else None
last_sos_total = sos_data[0].get("total_stores") if sos_data else None

# --- VOTG data (last 4 weeks) ---
votg_data = []
for i in range(1, 5):
    vw = (ws_date - timedelta(weeks=i)).strftime("%Y-%m-%d")
    votg_resp = sb.table("store_votg").select(
        "total_negative_reviews, votg_rank, total_stores"
    ).eq("location_id", location_id).eq("week_start", vw).execute()
    if votg_resp.data:
        votg_data.append(votg_resp.data[0])

avg_neg_reviews = None
if votg_data:
    neg_vals = [v["total_negative_reviews"] for v in votg_data if v.get("total_negative_reviews")]
    avg_neg_reviews = sum(neg_vals) / len(neg_vals) if neg_vals else None

last_votg_rank = votg_data[0].get("votg_rank") if votg_data else None
last_votg_total = votg_data[0].get("total_stores") if votg_data else None

# ---------------------------------------------------------------------------
# Display performance data
# ---------------------------------------------------------------------------

# Sales card
st.markdown('<div class="data-card"><h4>📊 Sales Performance</h4>', unsafe_allow_html=True)
col1, col2 = st.columns(2)
with col1:
    st.metric("Prior Year (Same Week)", fmt_currency(py_sales))
    st.metric("2 Weeks Ago", fmt_currency(prev_week_2))
with col2:
    st.metric("Last Week", fmt_currency(prev_week_1))
    st.metric("Avg (Last 2 Weeks)", fmt_currency(avg_prev_2))
st.markdown('</div>', unsafe_allow_html=True)

# SoS card
st.markdown('<div class="data-card"><h4>⏱️ Speed of Service</h4>', unsafe_allow_html=True)
sos_col1, sos_col2 = st.columns(2)
with sos_col1:
    st.metric("Avg SoS (Last 4 Weeks)", fmt_minutes(avg_sos))
with sos_col2:
    if last_sos_rank and last_sos_total:
        st.metric("SoS Rank (Last Week)", f"{last_sos_rank} of {last_sos_total}")
    else:
        st.metric("SoS Rank (Last Week)", "N/A")
st.markdown('</div>', unsafe_allow_html=True)

# VOTG card
st.markdown('<div class="data-card"><h4>📋 Voice of the Guest</h4>', unsafe_allow_html=True)
votg_col1, votg_col2 = st.columns(2)
with votg_col1:
    if avg_neg_reviews is not None:
        st.metric("Avg Negative Reviews (Last 4 Weeks)", f"{avg_neg_reviews:.1f}")
    else:
        st.metric("Avg Negative Reviews (Last 4 Weeks)", "N/A")
with votg_col2:
    if last_votg_rank and last_votg_total:
        st.metric("VOTG Rank (Last Week)", f"{last_votg_rank} of {last_votg_total}")
    else:
        st.metric("VOTG Rank (Last Week)", "N/A")
st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Revenue Band Selection
# ---------------------------------------------------------------------------
st.divider()

# Load available bands
bands_resp = sb.table("band_goals").select("revenue_band, hourly_goal").order("hourly_goal").execute()
band_options = [b["revenue_band"] for b in bands_resp.data] if bands_resp.data else []
band_goals = {b["revenue_band"]: b["hourly_goal"] for b in bands_resp.data} if bands_resp.data else {}

# Current band
current_band = store.get("revenue_band", "")

st.markdown(f"**Current Revenue Band:** {current_band}")
if current_band in band_goals:
    st.markdown(f"**Current Hourly Goal:** {band_goals[current_band]:.0f} hours")

st.markdown("")

selected_band = st.selectbox(
    "Select Revenue Band for This Week",
    options=band_options,
    index=band_options.index(current_band) if current_band in band_options else 0,
    help="Choose the revenue band that best matches your expected sales for this week."
)

if selected_band in band_goals:
    st.info(f"Hourly Goal for **{selected_band}**: **{band_goals[selected_band]:.0f} hours**")

# ---------------------------------------------------------------------------
# Submit
# ---------------------------------------------------------------------------
st.markdown("")

if st.button("Submit Revenue Band", type="primary", use_container_width=True):
    try:
        # Update the submission record
        sb.table("rev_band_submissions").update({
            "selected_band": selected_band,
            "submitted_at": datetime.utcnow().isoformat(),
            "status": "pending_dm",
        }).eq("token", token).execute()

        # Send notification to DM
        try:
            dm_resp = sb.table("dm_list").select("email").eq("dm_name", dm_name).execute()
            if dm_resp.data and dm_resp.data[0].get("email"):
                dm_email = dm_resp.data[0]["email"]
                # Import email service from the main app's secrets
                api_key = st.secrets.get("sendgrid", {}).get("api_key", "")
                from_email = st.secrets.get("sendgrid", {}).get("from_email", "")

                if api_key and from_email:
                    from sendgrid import SendGridAPIClient
                    from sendgrid.helpers.mail import Mail

                    dm_token = submission.get("token", "")
                    portal_url = f"https://ramz-dm-portal.streamlit.app/?token={dm_token}&role=dm"

                    html = f"""
                    <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;
                                border:1px solid #E0D5C9;border-radius:8px;overflow:hidden;">
                        <div style="background:#2B3A4E;padding:20px;text-align:center;">
                            <h2 style="color:#C49A5C;margin:0;">Revenue Band Approval</h2>
                        </div>
                        <div style="padding:24px;">
                            <p>The GM at <strong>{store_name}</strong> has submitted their
                            revenue band selection for the week of <strong>{week_start}</strong>.</p>
                            <table style="width:100%;border-collapse:collapse;margin:16px 0;">
                                <tr style="background:#F5F0EB;">
                                    <td style="padding:10px;font-weight:600;">Selected Band</td>
                                    <td style="padding:10px;">{selected_band}</td>
                                </tr>
                                <tr>
                                    <td style="padding:10px;font-weight:600;">Hourly Goal</td>
                                    <td style="padding:10px;">{band_goals.get(selected_band, 'N/A'):.0f} hours</td>
                                </tr>
                                <tr style="background:#F5F0EB;">
                                    <td style="padding:10px;font-weight:600;">Current Band</td>
                                    <td style="padding:10px;">{current_band}</td>
                                </tr>
                            </table>
                            <p>Please review and approve or reject this selection.</p>
                        </div>
                        <div style="padding:12px 24px;background:#F5F0EB;text-align:center;">
                            <p style="color:#888;font-size:12px;">Ram-Z Restaurant Group</p>
                        </div>
                    </div>
                    """

                    message = Mail(
                        from_email=from_email,
                        to_emails=dm_email,
                        subject=f"Revenue Band Approval Needed: {store_name} — Week of {week_start}",
                        html_content=html,
                    )
                    sg = SendGridAPIClient(api_key)
                    sg.send(message)

                    # Log the email
                    sb.table("email_log").insert({
                        "location_id": location_id,
                        "week_start": week_start,
                        "recipient_type": "dm",
                        "recipient_email": dm_email,
                        "email_type": "dm_approval_request",
                        "reminder_number": 0,
                    }).execute()
        except Exception as e:
            pass  # Don't block submission if DM email fails

        st.markdown("""
        <div class="success-box">
            <h3>✅ Submitted Successfully!</h3>
            <p>Your revenue band selection has been sent to your District Manager for approval.
            You can close this page.</p>
        </div>
        """, unsafe_allow_html=True)

        st.balloons()

    except Exception as e:
        st.error(f"Something went wrong. Please try again or contact your manager. Error: {str(e)}")
