"""
Ram-Z Revenue Band Selection Portal
------------------------------------
Dual-purpose app:
  - GM view: Select a revenue band for their store (token-based)
  - DM view: Review and approve/reject GM submissions (token-based)
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
    .pending-card {
        background: #FFF8E1;
        border-left: 4px solid #F9A825;
        border-radius: 4px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .submitted-card {
        background: #F5F0EB;
        border-left: 4px solid var(--ramz-gold);
        border-radius: 4px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .approved-card {
        background: #E8F5E9;
        border-left: 4px solid #4CAF50;
        border-radius: 4px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .overdue-card {
        background: #FFDADA;
        border-left: 4px solid #C62828;
        border-radius: 4px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .summary-bar {
        background: var(--ramz-navy);
        color: white;
        border-radius: 8px;
        padding: 1rem 1.5rem;
        margin-bottom: 1.5rem;
        display: flex;
        justify-content: space-around;
        text-align: center;
    }
    .summary-stat h2 { color: var(--ramz-gold); margin: 0; }
    .summary-stat p { color: #ccc; margin: 0; font-size: 0.85rem; }
    div[data-testid="stSelectbox"] label {
        color: var(--ramz-navy);
        font-weight: 600;
        font-size: 1.1rem;
    }
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fmt_currency(val):
    if val is None:
        return "N/A"
    return f"${val:,.0f}"


def fmt_minutes(seconds):
    if seconds is None:
        return "N/A"
    return f"{seconds / 60:.1f} min"


def load_store_performance(location_id, week_start):
    """Load sales, SoS, VOTG data for a store relative to a week."""
    from datetime import date as date_type
    ws_date = datetime.strptime(week_start, "%Y-%m-%d").date()

    # Anchor to last COMPLETED Thu-Wed week (not the upcoming target week)
    today = date_type.today()
    days_since_thu = (today.weekday() - 3) % 7
    current_week_start = today - timedelta(days=days_since_thu)
    last_complete_week = current_week_start - timedelta(weeks=1)
    two_weeks_ago     = current_week_start - timedelta(weeks=2)

    def get_week_sales(week_thu):
        """Sum all sale_date rows in a Thu–Wed window (handles daily or weekly storage)."""
        week_end = week_thu + timedelta(days=7)
        resp = sb.table("store_sales").select("sale_date,net_sales").eq(
            "location_id", location_id
        ).gte("sale_date", str(week_thu)).lt("sale_date", str(week_end)).execute()
        total = sum(float(r.get("net_sales") or 0) for r in (resp.data or []))
        return total if total > 0 else None

    # Prior year: same Thu–Wed week 52 weeks ago (relative to last complete week)
    py_sales = get_week_sales(last_complete_week - timedelta(weeks=52))

    # Last 2 completed weeks
    prev_sales = [get_week_sales(last_complete_week), get_week_sales(two_weeks_ago)]

    valid_prev = [s for s in prev_sales if s is not None]
    avg_prev = sum(valid_prev) / len(valid_prev) if valid_prev else None

    # SoS (last 4 weeks) — uses store_sos_weekly with total_time as "MM:SS"
    avg_sos = last_sos_rank = last_sos_total = None
    try:
        sos_rows = sb.table("store_sos_weekly").select(
            "week_start, good_shift_rank, total_stores, total_time"
        ).eq("location_id", location_id).gte(
            "week_start", str(current_week_start - timedelta(weeks=4))
        ).lt("week_start", str(current_week_start)).order("week_start", desc=True).execute().data or []

        if sos_rows:
            last_sos_rank  = sos_rows[0].get("good_shift_rank")
            last_sos_total = sos_rows[0].get("total_stores")
            secs = []
            for r in sos_rows:
                tt = str(r.get("total_time") or "")
                if ":" in tt:
                    try:
                        m, s = tt.split(":")
                        secs.append(int(m) * 60 + int(s))
                    except (ValueError, IndexError):
                        pass
            avg_sos = sum(secs) / len(secs) if secs else None
    except Exception:
        pass

    # VOTG (last 4 weeks) — uses store_votg_weekly
    avg_neg = last_votg_rank = last_votg_total = None
    try:
        votg_rows = sb.table("store_votg_weekly").select(
            "week_start, total_negative_reviews, votg_rank, total_stores"
        ).eq("location_id", location_id).gte(
            "week_start", str(current_week_start - timedelta(weeks=4))
        ).lt("week_start", str(current_week_start)).order("week_start", desc=True).execute().data or []

        if votg_rows:
            last_votg_rank  = votg_rows[0].get("votg_rank")
            last_votg_total = votg_rows[0].get("total_stores")
            negs = [float(r.get("total_negative_reviews") or 0) for r in votg_rows]
            avg_neg = sum(negs) / len(negs) if negs else None
    except Exception:
        pass

    return {
        "py_sales": py_sales,
        "prev_week_1": prev_sales[0],
        "prev_week_2": prev_sales[1],
        "avg_prev_2": avg_prev,
        "avg_sos": avg_sos,
        "last_sos_rank": last_sos_rank,
        "last_sos_total": last_sos_total,
        "avg_neg_reviews": avg_neg,
        "last_votg_rank": last_votg_rank,
        "last_votg_total": last_votg_total,
    }


def display_performance_cards(perf):
    """Render the performance data cards."""
    # Sales
    st.markdown('<div class="data-card"><h4>📊 Sales Performance</h4>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Prior Year (Same Week)", fmt_currency(perf["py_sales"]))
        st.metric("2 Weeks Ago", fmt_currency(perf["prev_week_2"]))
    with c2:
        st.metric("Last Week", fmt_currency(perf["prev_week_1"]))
        st.metric("Avg (Last 2 Weeks)", fmt_currency(perf["avg_prev_2"]))
    st.markdown('</div>', unsafe_allow_html=True)

    # SoS
    st.markdown('<div class="data-card"><h4>⏱️ Speed of Service</h4>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.metric("Avg SoS (Last 4 Weeks)", fmt_minutes(perf["avg_sos"]))
    with c2:
        if perf["last_sos_rank"] and perf["last_sos_total"]:
            st.metric("SoS Rank (Last Week)", f"{perf['last_sos_rank']} of {perf['last_sos_total']}")
        else:
            st.metric("SoS Rank (Last Week)", "N/A")
    st.markdown('</div>', unsafe_allow_html=True)

    # VOTG
    st.markdown('<div class="data-card"><h4>📋 Voice of the Guest</h4>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        if perf["avg_neg_reviews"] is not None:
            st.metric("Avg Negative Reviews (Last 4 Weeks)", f"{perf['avg_neg_reviews']:.1f}")
        else:
            st.metric("Avg Negative Reviews (Last 4 Weeks)", "N/A")
    with c2:
        if perf["last_votg_rank"] and perf["last_votg_total"]:
            st.metric("VOTG Rank (Last Week)", f"{perf['last_votg_rank']} of {perf['last_votg_total']}")
        else:
            st.metric("VOTG Rank (Last Week)", "N/A")
    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Route: GM view vs DM view
# ---------------------------------------------------------------------------
token = st.query_params.get("token", None)
role = st.query_params.get("role", "gm")

if not token:
    st.markdown("""
    <div class="expired-box">
        <h3>No Access Token</h3>
        <p>Please use the link from your email to access this page.</p>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ===========================================================================
# DM VIEW
# ===========================================================================
if role == "dm":
    # Validate DM token — look up the DM name from the token
    # The DM token is stored in app_settings or we derive it from the submissions
    # For now, the DM token matches a specific week + DM combo
    dm_resp = sb.table("rev_band_submissions").select("*").eq("token", token).execute()

    # If single token lookup fails, try dm_token field approach
    if not dm_resp.data:
        st.markdown("""
        <div class="expired-box">
            <h3>Invalid Link</h3>
            <p>This link is not valid. Please check your email for the correct link.</p>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # Get the DM name and week from the first submission
    first_sub = dm_resp.data[0]
    week_start = first_sub["week_start"]

    # Look up the store to get DM name
    store_resp = sb.table("reference_data").select("dm").eq(
        "location_id", first_sub["location_id"]).execute()
    dm_name = store_resp.data[0]["dm"] if store_resp.data else "Unknown"

    # Load ALL stores for this DM
    dm_stores_resp = sb.table("reference_data").select("*").eq("dm", dm_name).execute()
    dm_stores = {s["location_id"]: s for s in dm_stores_resp.data} if dm_stores_resp.data else {}
    dm_store_ids = list(dm_stores.keys())

    # Load ALL submissions for this week for DM's stores
    all_subs_resp = sb.table("rev_band_submissions").select("*").eq(
        "week_start", week_start).execute()
    all_subs = {s["location_id"]: s for s in all_subs_resp.data
                if s["location_id"] in dm_store_ids}

    # Load band goals
    bands_resp = sb.table("band_goals").select("revenue_band, hourly_goal").order("hourly_goal").execute()
    band_goals = {b["revenue_band"]: b["hourly_goal"] for b in bands_resp.data} if bands_resp.data else {}

    # ---------------------------------------------------------------------------
    # DM Header
    # ---------------------------------------------------------------------------
    st.markdown(f"""
    <div class="main-header">
        <div class="store-title">DM Review — {dm_name}</div>
        <div class="week-label">Week of {week_start}</div>
    </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------------------------
    # Summary bar
    # ---------------------------------------------------------------------------
    total_stores = len(dm_store_ids)
    submitted = sum(1 for sid in dm_store_ids
                    if sid in all_subs and all_subs[sid]["status"] != "pending_gm")
    approved = sum(1 for sid in dm_store_ids
                   if sid in all_subs and all_subs[sid]["status"] in ("pending_admin", "approved"))
    pending_gm = total_stores - submitted

    st.markdown(f"""
    <div class="summary-bar">
        <div class="summary-stat">
            <h2>{total_stores}</h2>
            <p>Total Stores</p>
        </div>
        <div class="summary-stat">
            <h2>{submitted}</h2>
            <p>Submitted</p>
        </div>
        <div class="summary-stat">
            <h2>{approved}</h2>
            <p>Approved</p>
        </div>
        <div class="summary-stat">
            <h2>{pending_gm}</h2>
            <p>Awaiting GM</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------------------------
    # Store filter
    # ---------------------------------------------------------------------------
    store_names = {sid: dm_stores[sid]["store_name"] for sid in dm_store_ids}
    filter_options = ["All Stores"] + sorted(store_names.values())
    selected_filter = st.selectbox("Filter by Store", filter_options)

    if selected_filter != "All Stores":
        dm_store_ids = [sid for sid, name in store_names.items() if name == selected_filter]

    st.divider()

    # ---------------------------------------------------------------------------
    # Pending GM submissions (not yet submitted)
    # ---------------------------------------------------------------------------
    pending_ids = [sid for sid in dm_store_ids
                   if sid not in all_subs or all_subs[sid]["status"] == "pending_gm"]

    if pending_ids:
        st.markdown("### ⏳ Awaiting GM Submission")
        for sid in sorted(pending_ids, key=lambda x: store_names.get(x, "")):
            s = dm_stores[sid]
            sub = all_subs.get(sid)
            missed = sub.get("gm_deadline_missed", False) if sub else False
            card_class = "overdue-card" if missed else "pending-card"
            status_text = "⚠️ OVERDUE" if missed else "Waiting for GM"

            st.markdown(f"""
            <div class="{card_class}">
                <strong>{s['store_name']}</strong> &nbsp;|&nbsp;
                Current Band: {s.get('revenue_band', 'N/A')} &nbsp;|&nbsp;
                <em>{status_text}</em>
            </div>
            """, unsafe_allow_html=True)
        st.divider()

    # ---------------------------------------------------------------------------
    # Submitted — ready for DM review
    # ---------------------------------------------------------------------------
    review_ids = [sid for sid in dm_store_ids
                  if sid in all_subs and all_subs[sid]["status"] == "pending_dm"]

    if review_ids:
        st.markdown("### 📋 Ready for Your Approval")
        for sid in sorted(review_ids, key=lambda x: store_names.get(x, "")):
            s = dm_stores[sid]
            sub = all_subs[sid]
            selected_band = sub["selected_band"]
            current_band = s.get("revenue_band", "N/A")
            band_changed = selected_band != current_band

            st.markdown(f"""
            <div class="submitted-card">
                <strong>{s['store_name']}</strong>
            </div>
            """, unsafe_allow_html=True)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**Current Band:** {current_band}")
                if current_band in band_goals:
                    st.markdown(f"Goal: {band_goals[current_band]:.0f} hrs")
            with col2:
                st.markdown(f"**Selected Band:** {selected_band}")
                if selected_band in band_goals:
                    st.markdown(f"Goal: {band_goals[selected_band]:.0f} hrs")
            with col3:
                if band_changed:
                    st.warning("Band changed")
                else:
                    st.success("No change")

            # Expandable performance data
            with st.expander(f"View {s['store_name']} Performance Data"):
                perf = load_store_performance(sid, week_start)
                display_performance_cards(perf)

            # Approve / Reject buttons
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button(f"✅ Approve", key=f"approve_{sid}", use_container_width=True):
                    sb.table("rev_band_submissions").update({
                        "status": "pending_admin",
                        "dm_approved_at": datetime.utcnow().isoformat(),
                        "dm_approved_by": dm_name,
                    }).eq("id", sub["id"]).execute()
                    st.success(f"Approved {s['store_name']}")
                    st.rerun()

            with btn_col2:
                if st.button(f"❌ Reject", key=f"reject_{sid}", use_container_width=True):
                    st.session_state[f"rejecting_{sid}"] = True

            # Rejection reason input
            if st.session_state.get(f"rejecting_{sid}", False):
                reason = st.text_input(
                    f"Rejection reason for {s['store_name']}",
                    key=f"reason_{sid}",
                    placeholder="Enter reason for rejection..."
                )
                if st.button(f"Confirm Rejection", key=f"confirm_reject_{sid}"):
                    sb.table("rev_band_submissions").update({
                        "status": "rejected",
                        "rejected_at": datetime.utcnow().isoformat(),
                        "rejected_by": dm_name,
                        "rejection_reason": reason,
                    }).eq("id", sub["id"]).execute()
                    st.session_state[f"rejecting_{sid}"] = False
                    st.warning(f"Rejected {s['store_name']}")
                    st.rerun()

            st.divider()

    # ---------------------------------------------------------------------------
    # Already approved
    # ---------------------------------------------------------------------------
    approved_ids = [sid for sid in dm_store_ids
                    if sid in all_subs and all_subs[sid]["status"] in ("pending_admin", "approved")]

    if approved_ids:
        st.markdown("### ✅ Approved")
        for sid in sorted(approved_ids, key=lambda x: store_names.get(x, "")):
            s = dm_stores[sid]
            sub = all_subs[sid]
            st.markdown(f"""
            <div class="approved-card">
                <strong>{s['store_name']}</strong> &nbsp;|&nbsp;
                Band: {sub['selected_band']} &nbsp;|&nbsp;
                Goal: {band_goals.get(sub['selected_band'], 'N/A')} hrs &nbsp;|&nbsp;
                <em>Approved ✓</em>
            </div>
            """, unsafe_allow_html=True)

    # ---------------------------------------------------------------------------
    # Rejected
    # ---------------------------------------------------------------------------
    rejected_ids = [sid for sid in dm_store_ids
                    if sid in all_subs and all_subs[sid]["status"] == "rejected"]

    if rejected_ids:
        st.markdown("### 🚫 Rejected")
        for sid in sorted(rejected_ids, key=lambda x: store_names.get(x, "")):
            s = dm_stores[sid]
            sub = all_subs[sid]
            st.markdown(f"""
            <div class="overdue-card">
                <strong>{s['store_name']}</strong> &nbsp;|&nbsp;
                Band: {sub['selected_band']} &nbsp;|&nbsp;
                Reason: {sub.get('rejection_reason', 'N/A')}
            </div>
            """, unsafe_allow_html=True)

    st.stop()


# ===========================================================================
# GM VIEW (default)
# ===========================================================================

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
        pass

# Load store info
store_resp = sb.table("reference_data").select("*").eq("location_id", location_id).execute()
if not store_resp.data:
    st.error("Store not found. Please contact your manager.")
    st.stop()

store = store_resp.data[0]
store_name = store["store_name"]
dm_name = store.get("dm", "Unknown")

# Header
st.markdown(f"""
<div class="main-header">
    <div class="store-title">{store_name}</div>
    <div class="week-label">Revenue Band Selection — Week of {week_start}</div>
</div>
""", unsafe_allow_html=True)

st.divider()

# Load and display performance data
perf = load_store_performance(location_id, week_start)
display_performance_cards(perf)

# ---------------------------------------------------------------------------
# Revenue Band Selection
# ---------------------------------------------------------------------------
st.divider()

bands_resp = sb.table("band_goals").select("revenue_band, hourly_goal").order("hourly_goal").execute()
band_options = [b["revenue_band"] for b in bands_resp.data] if bands_resp.data else []
band_goals = {b["revenue_band"]: b["hourly_goal"] for b in bands_resp.data} if bands_resp.data else {}

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

if not st.session_state.get("submitted") and st.button("Submit Revenue Band", type="primary", use_container_width=True):
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
                api_key = st.secrets.get("sendgrid", {}).get("api_key", "")
                from_email = st.secrets.get("sendgrid", {}).get("from_email", "")

                if api_key and from_email:
                    from sendgrid import SendGridAPIClient
                    from sendgrid.helpers.mail import Mail

                    # DM gets a link to the same app with role=dm
                    dm_url = f"https://ramz-gm-select.streamlit.app/?token={token}&role=dm"

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
                                    <td style="padding:10px;">{band_goals.get(selected_band, 0):.0f} hours</td>
                                </tr>
                                <tr style="background:#F5F0EB;">
                                    <td style="padding:10px;font-weight:600;">Current Band</td>
                                    <td style="padding:10px;">{current_band}</td>
                                </tr>
                            </table>
                            <div style="text-align:center;margin:24px 0;">
                                <a href="{dm_url}" style="background:#C49A5C;color:white;
                                   padding:12px 32px;border-radius:6px;text-decoration:none;
                                   font-weight:600;">Review All Stores</a>
                            </div>
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
        except Exception:
            pass  # Don't block submission if DM email fails

        st.session_state["submitted"] = True
        st.markdown("""
        <div class="success-box">
            <h3>✅ Submitted Successfully!</h3>
            <p>Your revenue band selection has been sent to your District Manager for approval.
            You can close this page.</p>
        </div>
        """, unsafe_allow_html=True)

        st.balloons()
        st.stop()

    except Exception as e:
        st.error(f"Something went wrong. Please try again or contact your manager. Error: {str(e)}")
