#!/usr/bin/env python3
"""
EMI Calculator Web App - Streamlit
Supports:
1. Normal Reducing Balance EMI Loans (Principal + Interest)
2. OD / Gold Loans - Interest Only (Bullet principal at end)
With full support for Adhoc + Flexible Recurring Extra Payments,
Remaining Principal lookup, Repayment Schedules, and What-If analysis.
Run with: streamlit run emi_calculator_app.py
"""

import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import io

# Try to import Streamlit (only needed when running the web app)
try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None


# ====================== INDIAN NUMBER FORMATTING ======================

def format_inr(amount: float, compact: bool = False) -> str:
    """
    Format amount in Indian numbering system.
    compact=True  → ₹12.50 Lakh or ₹1.25 Cr   (ideal for big metric cards)
    compact=False → ₹12,50,000.00             (full Indian comma format for tables)
    """
    if amount is None:
        return "₹ 0.00"
    n = float(amount)
    sign = "₹ " if n >= 0 else "-₹ "
    n = abs(n)

    if compact:
        if n >= 10000000:      # 1 Crore+
            return f"{sign}{n/10000000:.2f} Cr"
        elif n >= 100000:      # 1 Lakh+
            return f"{sign}{n/100000:.2f} Lakh"
        else:
            return f"{sign}{n:,.2f}"
    else:
        # Full Indian comma format (1,00,00,000 style)
        s = f"{n:,.2f}"
        int_part, dec_part = s.split('.')
        int_part = int_part.replace(',', '')

        if len(int_part) <= 3:
            formatted = int_part
        else:
            result = int_part[-3:]
            int_part = int_part[:-3]
            while int_part:
                result = int_part[-2:] + ',' + result
                int_part = int_part[:-2]
            formatted = result
        return f"{sign}{formatted}.{dec_part}"


# ====================== CORE CALCULATION FUNCTIONS ======================

def calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Standard EMI formula for reducing balance loans."""
    if annual_rate <= 0:
        return round(principal / tenure_months, 2)
    monthly_rate = annual_rate / 12 / 100
    if monthly_rate == 0:
        return round(principal / tenure_months, 2)
    emi = principal * monthly_rate * (1 + monthly_rate) ** tenure_months / \
          ((1 + monthly_rate) ** tenure_months - 1)
    return round(emi, 2)


def generate_schedule(
    principal: float,
    annual_rate: float,
    tenure_months: int,
    loan_type: str = "normal",
    monthly_emi: float = None,
    extras: list = None,
    start_date: datetime = None,
    strategy: str = "reduce_tenure"
) -> tuple[pd.DataFrame, dict]:
    """
    Core simulation engine.
    Returns (schedule_df, summary)
    loan_type: "normal" or "interest_only"
    extras: list of dicts [{"month": 5, "amount": 25000}, ...]
    strategy: "reduce_tenure" (default, recommended) or "keep_tenure"
    """
    if extras is None:
        extras = []
    if start_date is None:
        start_date = datetime.now().replace(day=1)

    monthly_rate = annual_rate / 12 / 100.0

    # Calculate base EMI if not provided (for normal loans)
    if monthly_emi is None:
        if loan_type == "normal":
            monthly_emi = calculate_emi(principal, annual_rate, tenure_months)
        else:
            monthly_emi = round(principal * monthly_rate, 2)  # initial interest only

    extra_map = {}
    for e in extras:
        m = e.get("month", 0)
        if m > 0:
            extra_map[m] = extra_map.get(m, 0) + e.get("amount", 0)

    schedule = []
    outstanding = float(principal)
    total_interest_paid = 0.0
    total_amount_paid = 0.0
    current_payment = monthly_emi

    max_months = tenure_months + 120  # safety
    actual_tenure = tenure_months

    for month_num in range(1, max_months + 1):
        if outstanding <= 0.01:
            actual_tenure = month_num - 1
            break

        interest = outstanding * monthly_rate
        extra_this_month = extra_map.get(month_num, 0.0)

        if loan_type == "normal":
            # Normal reducing EMI
            payment = current_payment
            if outstanding + interest < payment + 1:
                payment = outstanding + interest

            interest_component = interest
            principal_component = payment - interest_component

            if principal_component > outstanding:
                principal_component = outstanding
                payment = interest_component + principal_component

        else:
            # Interest Only (OD/Gold)
            interest_component = interest
            # Regular payment = interest. Extra reduces principal.
            principal_component = extra_this_month
            payment = interest_component + principal_component

            # On last original month or when loan is closing, add bullet principal
            is_final_month = (month_num == tenure_months)
            remaining_after_extra = outstanding - principal_component
            if is_final_month or remaining_after_extra <= 0.01:
                bullet = max(0, outstanding - principal_component)
                principal_component += bullet
                payment += bullet

        # Apply payment
        outstanding = max(0.0, outstanding - principal_component)
        total_interest_paid += interest_component
        total_amount_paid += payment

        payment_date = start_date + relativedelta(months=month_num - 1)

        schedule.append({
            "Month": month_num,
            "Payment Date": payment_date.strftime("%d %b %Y"),
            "Payment (₹)": round(payment, 2),
            "Interest (₹)": round(interest_component, 2),
            "Principal (₹)": round(principal_component, 2),
            "Extra (₹)": round(extra_this_month, 2),
            "Outstanding Principal (₹)": round(outstanding, 2),
            "Cumulative Interest (₹)": round(total_interest_paid, 2)
        })

        if outstanding <= 0.01:
            actual_tenure = month_num
            break

    df = pd.DataFrame(schedule)

    # Summary
    original_total_interest = 0.0
    if loan_type == "normal" and monthly_emi:
        # Rough original interest estimate
        original_total_interest = (monthly_emi * tenure_months) - principal
    else:
        original_total_interest = principal * monthly_rate * tenure_months

    summary = {
        "principal": round(principal, 2),
        "annual_rate": annual_rate,
        "tenure_months": tenure_months,
        "loan_type": loan_type,
        "monthly_payment": round(monthly_emi, 2),
        "total_interest_paid": round(total_interest_paid, 2),
        "total_amount_paid": round(total_amount_paid, 2),
        "actual_tenure_months": actual_tenure,
        "months_saved": max(0, tenure_months - actual_tenure),
        "interest_saved_vs_original": round(max(0, original_total_interest - total_interest_paid), 2),
        "strategy_used": strategy
    }

    return df, summary


def make_display_schedule(df: pd.DataFrame) -> pd.DataFrame:
    """Create a copy of schedule with Indian-formatted money columns for nice display."""
    if df.empty:
        return df
    display_df = df.copy()
    money_cols = ["Payment (₹)", "Interest (₹)", "Principal (₹)", "Extra (₹)", 
                  "Outstanding Principal (₹)", "Cumulative Interest (₹)"]
    for col in money_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: format_inr(x, compact=False))
    return display_df


def get_remaining_balance(schedule_df: pd.DataFrame, after_month: int) -> dict:
    """Get remaining principal and interest paid after a specific month."""
    if schedule_df.empty or after_month < 1:
        return {"error": "Invalid month"}

    row = schedule_df[schedule_df["Month"] == after_month]
    if row.empty:
        # Find closest
        row = schedule_df[schedule_df["Month"] <= after_month].tail(1)

    if row.empty:
        return {"error": "Month not found in schedule"}

    r = row.iloc[0]
    return {
        "after_month": int(r["Month"]),
        "outstanding_principal": r["Outstanding Principal (₹)"],
        "cumulative_interest_paid": r["Cumulative Interest (₹)"],
        "total_paid_till_then": schedule_df[schedule_df["Month"] <= after_month]["Payment (₹)"].sum()
    }


def generate_recurring_extras(frequency: str, extra_amount: float, start_month: int, max_month: int) -> list:
    """Generate list of extra payment dicts based on frequency."""
    extras = []
    if extra_amount <= 0 or start_month < 1:
        return extras

    step = 1
    if frequency == "Every 3 Months":
        step = 3
    elif frequency == "Every 6 Months":
        step = 6
    elif frequency == "Every 12 Months":
        step = 12

    for m in range(start_month, max_month + 1, step):
        extras.append({"month": m, "amount": extra_amount})
    return extras


# ====================== STREAMLIT UI ======================

if STREAMLIT_AVAILABLE:
    st.set_page_config(
        page_title="EMI Calculator - Normal & OD/Gold Loans",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Custom CSS: bigger sidebar, larger numbers, more vertical/clean layout
    st.markdown("""
    <style>
    /* Make left sidebar (panel) bigger */
    [data-testid="stSidebar"] {
        width: 420px !important;
        min-width: 380px !important;
    }
    
    /* Larger numbers in metric cards */
    [data-testid="stMetricValue"] {
        font-size: 26px !important;
        font-weight: 600 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 14px !important;
    }
    
    /* Bigger readable text in tables */
    .stDataFrame {
        font-size: 14.5px !important;
    }
    
    /* Slightly larger input labels */
    label, .stNumberInput label, .stSlider label, .stSelectbox label {
        font-size: 15px !important;
    }
    
    /* Constrain main content width for less horizontal stretch, more vertical friendly */
    .main .block-container {
        max-width: 1080px !important;
        padding-left: 1.5rem !important;
        padding-right: 1.5rem !important;
    }
    
    /* Better vertical spacing in tabs */
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 0.75rem;
    }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 Advanced EMI Calculator")
st.markdown("**Normal Reducing EMI Loans** vs **Interest-Only OD/Gold Loans** with Adhoc & Recurring Extra Payments")

# Initialize session state
if "extras" not in st.session_state:
    st.session_state.extras = []
if "last_params" not in st.session_state:
    st.session_state.last_params = {}
if "original_schedule" not in st.session_state:
    st.session_state.original_schedule = pd.DataFrame()
if "with_extras_schedule" not in st.session_state:
    st.session_state.with_extras_schedule = pd.DataFrame()
if "original_summary" not in st.session_state:
    st.session_state.original_summary = {}
if "with_extras_summary" not in st.session_state:
    st.session_state.with_extras_summary = {}

# ====================== SIDEBAR INPUTS ======================
with st.sidebar:
    st.header("Loan Inputs")

    loan_type = st.radio(
        "Loan Type",
        options=["Normal Reducing EMI (Principal + Interest)", "Interest-Only (OD / Gold Loan)"],
        index=0,
        help="Normal = Standard EMI with P+I | Interest-Only = Pay only interest monthly, principal as bullet at end or via prepayments"
    )
    loan_type_key = "normal" if "Normal" in loan_type else "interest_only"

    principal = st.number_input("Principal Amount (₹)", min_value=10000, max_value=100000000, value=1000000, step=10000, format="%d")

    annual_rate = st.slider("Annual Interest Rate (%)", min_value=1.0, max_value=36.0, value=10.5, step=0.1)
    annual_rate = st.number_input("Annual Interest Rate (fine tune)", min_value=1.0, max_value=36.0, value=annual_rate, step=0.01)

    tenure_months = st.slider("Tenure (Months)", min_value=3, max_value=360, value=60, step=1)
    tenure_months = st.number_input("Tenure in Months (fine tune)", min_value=3, max_value=360, value=tenure_months, step=1)

    start_date = st.date_input("Loan Start Date", value=datetime.now().date())

    st.divider()
    st.caption("💡 Tip: Change any value above — calculations update automatically")

# ====================== MAIN DASHBOARD ======================
col1, col2, col3 = st.columns(3)

# Calculate base values
if loan_type_key == "normal":
    base_monthly = calculate_emi(principal, annual_rate, tenure_months)
else:
    base_monthly = round(principal * (annual_rate / 12 / 100), 2)

total_original_interest = (base_monthly * tenure_months) - principal if loan_type_key == "normal" else (principal * (annual_rate / 12 / 100) * tenure_months)

with col1:
    st.metric("Monthly Payment", format_inr(base_monthly, compact=True), 
              help="Normal EMI or Interest-only amount (initial)")

with col2:
    st.metric("Total Interest (Original)", format_inr(total_original_interest, compact=True))

with col3:
    st.metric("Total Amount Payable", format_inr(principal + total_original_interest, compact=True))

st.divider()

# ====================== TABS ======================
tab_schedule, tab_extras, tab_remaining = st.tabs([
    "📊 Repayment Schedule", 
    "🔄 Extra Payments & What-If", 
    "📍 Remaining Balance Checker"
])

# Generate original schedule (no extras)
original_df, original_summary = generate_schedule(
    principal=principal,
    annual_rate=annual_rate,
    tenure_months=tenure_months,
    loan_type=loan_type_key,
    monthly_emi=base_monthly,
    extras=[],
    start_date=datetime.combine(start_date, datetime.min.time())
)

st.session_state.original_schedule = original_df
st.session_state.original_summary = original_summary

# ====================== TAB 1: SCHEDULE ======================
with tab_schedule:
    st.subheader("Original Repayment Schedule (No Extra Payments)")

    if not original_df.empty:
        display_df = make_display_schedule(original_df)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

        # Download
        csv_buffer = io.StringIO()
        original_df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="⬇️ Download Original Schedule as CSV",
            data=csv_buffer.getvalue(),
            file_name=f"original_schedule_{loan_type_key}.csv",
            mime="text/csv"
        )
    else:
        st.warning("Could not generate schedule. Please check inputs.")

# ====================== TAB 2: EXTRA PAYMENTS ======================
with tab_extras:
    st.subheader("Extra Payments Simulator (Adhoc + Recurring)")

    # Current extras display
    if st.session_state.extras:
        st.info(f"**Active Extra Payments:** {len(st.session_state.extras)} entries | Total extra amount: ₹ {sum(e['amount'] for e in st.session_state.extras):,.2f}")
        with st.expander("View / Clear Current Extras"):
            extras_df = pd.DataFrame(st.session_state.extras)
            st.dataframe(extras_df, use_container_width=True, hide_index=True)
            if st.button("🗑️ Clear All Extra Payments", type="secondary"):
                st.session_state.extras = []
                st.rerun()
    else:
        st.caption("No extra payments added yet. Use the sections below.")

    st.divider()

    # --- ADHOC PREPAYMENT ---
    st.markdown("### 1. Adhoc / One-time Part Payment")
    with st.expander("ℹ️ What is 'Month Number'? (Click to understand)", expanded=False):
        st.info("""
        **Month Number** = Which EMI payment you want to make the extra payment with.
        
        - **Month 1** = Your very first EMI
        - **Month 6** = After 6 months of regular EMIs
        - **Month 12** = After exactly 1 year
        - **Month 24** = After 2 years, and so on.
        
        This lets you simulate "I will pay an extra lump sum after X months of regular payments".
        """)

    col_a, col_b, col_c = st.columns([2, 2, 1])
    with col_a:
        adhoc_month = st.number_input("Month Number (1 = First EMI)", min_value=1, max_value=tenure_months + 60, value=12, step=1, key="adhoc_month")
    with col_b:
        adhoc_amount = st.number_input("Extra Amount (₹)", min_value=0, value=50000, step=5000, key="adhoc_amount")
    with col_c:
        if st.button("➕ Add Adhoc Payment", type="primary"):
            if adhoc_amount > 0:
                st.session_state.extras.append({"month": int(adhoc_month), "amount": float(adhoc_amount)})
                st.success(f"Added ₹{adhoc_amount:,.0f} in Month {adhoc_month}")
                st.rerun()

    st.divider()

    # --- RECURRING EXTRA PAYMENTS ---
    st.markdown("### 2. Recurring Extra Payments (Flexible)")
    col_r1, col_r2, col_r3, col_r4 = st.columns(4)
    with col_r1:
        freq = st.selectbox("Frequency", ["Every Month", "Every 3 Months", "Every 6 Months", "Every 12 Months"], key="freq")
    with col_r2:
        rec_amount = st.number_input("Extra Amount per instance (₹)", min_value=0, value=5000, step=1000, key="rec_amount")
    with col_r3:
        rec_start = st.number_input("Start from Month", min_value=1, max_value=tenure_months, value=6, step=1, key="rec_start")
    with col_r4:
        if st.button("➕ Add Recurring Extras", type="primary"):
            if rec_amount > 0:
                new_extras = generate_recurring_extras(freq, rec_amount, rec_start, tenure_months + 24)
                st.session_state.extras.extend(new_extras)
                st.success(f"Added {len(new_extras)} recurring extra payments of ₹{rec_amount:,.0f} ({freq})")
                st.rerun()

    st.divider()

    # Strategy choice
    st.markdown("### 3. Prepayment Strategy (for Normal Reducing Loans)")
    strategy = st.radio(
        "What should happen when you make extra payments?",
        options=[
            "Keep EMI same & reduce tenure (Recommended - Maximum interest saving)",
            "Keep original tenure & reduce future EMI amount"
        ],
        index=0,
        help="Option 1 saves the most interest. Option 2 keeps your monthly outflow same as original plan."
    )
    strategy_key = "reduce_tenure" if "reduce tenure" in strategy else "keep_tenure"

    if loan_type_key == "interest_only":
        st.caption("ℹ️ For Interest-Only loans, extra payments always reduce principal and future interest. No 'EMI' to reduce.")

    # Compute with extras button
    if st.button("🚀 Calculate Impact of All Extra Payments", type="primary", use_container_width=True):
        if not st.session_state.extras:
            st.warning("Please add at least one adhoc or recurring extra payment first.")
        else:
            # Generate schedule WITH extras
            with_extras_df, with_extras_summary = generate_schedule(
                principal=principal,
                annual_rate=annual_rate,
                tenure_months=tenure_months,
                loan_type=loan_type_key,
                monthly_emi=base_monthly,
                extras=st.session_state.extras,
                start_date=datetime.combine(start_date, datetime.min.time()),
                strategy=strategy_key
            )
            st.session_state.with_extras_schedule = with_extras_df
            st.session_state.with_extras_summary = with_extras_summary
            st.success("Impact calculated! See results below.")

    # Show comparison if available
    if not st.session_state.with_extras_schedule.empty:
        st.divider()
        st.subheader("📈 Impact Summary")

        s1 = st.session_state.original_summary
        s2 = st.session_state.with_extras_summary

        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.metric("Original Tenure", f"{s1['tenure_months']} months")
        with m2:
            st.metric("New Tenure (with extras)", f"{s2['actual_tenure_months']} months", 
                      delta=f"-{s2['months_saved']} months" if s2['months_saved'] > 0 else None)
        with m3:
            st.metric("Original Total Interest", format_inr(s1['total_interest_paid'], compact=True))
        with m4:
            st.metric("New Total Interest", format_inr(s2['total_interest_paid'], compact=True),
                      delta=f"-{format_inr(s2.get('interest_saved_vs_original', 0), compact=True)}" if s2.get('interest_saved_vs_original', 0) > 0 else None,
                      delta_color="inverse")

        st.caption(f"Strategy applied: **{s2.get('strategy_used', strategy_key)}**")

        # Comparison - Vertical layout (less horizontal stretch, inspired by emicalculator.net)
        st.subheader("Comparison: Original vs With Extra Payments")

        st.markdown("**Original Schedule (No Extras)**")
        display_orig = make_display_schedule(original_df.head(12))
        st.dataframe(display_orig, use_container_width=True, hide_index=True)
        if len(original_df) > 12:
            st.caption(f"... showing first 12 of {len(original_df)} months")

        st.markdown("**Updated Schedule After Extra Payments**")
        display_new = make_display_schedule(st.session_state.with_extras_schedule.head(12))
        st.dataframe(display_new, use_container_width=True, hide_index=True)
        if len(st.session_state.with_extras_schedule) > 12:
            st.caption(f"... showing first 12 of {len(st.session_state.with_extras_schedule)} months")

        # Full download for with-extras
        csv2 = io.StringIO()
        st.session_state.with_extras_schedule.to_csv(csv2, index=False)
        st.download_button(
            "⬇️ Download Schedule with Extra Payments (CSV)",
            data=csv2.getvalue(),
            file_name=f"schedule_with_extras_{loan_type_key}.csv",
            mime="text/csv"
        )

# ====================== TAB 3: REMAINING BALANCE ======================
with tab_remaining:
    st.subheader("Check Remaining Principal & Interest at Any Point")

    if not original_df.empty:
        max_m = int(original_df["Month"].max())
        after_month = st.slider("After which month do you want to check?", 1, max_m, min(12, max_m), step=1)

        remaining = get_remaining_balance(original_df, after_month)

        if "error" not in remaining:
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Outstanding Principal", format_inr(remaining['outstanding_principal'], compact=True))
            with c2:
                st.metric("Interest Paid Till Then", format_inr(remaining['cumulative_interest_paid'], compact=True))
            with c3:
                st.metric("Total Amount Paid Till Then", format_inr(remaining['total_paid_till_then'], compact=True))

            st.caption("Note: This is based on the **original schedule** (no extras). If you have active extra payments, the outstanding will be lower.")
        else:
            st.error(remaining["error"])
    else:
        st.info("Generate the original schedule first by adjusting inputs on the left.")

# ====================== FOOTER / INSTRUCTIONS ======================
st.divider()
st.markdown("""
**How to use this tool:**
1. Set your loan details on the left sidebar (switch between Normal and Interest-Only).
2. View the full repayment schedule in the first tab.
3. Add **Adhoc** (one-time) or **Recurring** extra payments in the second tab.
4. Click **"Calculate Impact of All Extra Payments"** to see how much interest & time you save.
5. Use the third tab to check remaining principal after any month.

**Tip for maximum savings:** Use the default strategy "Keep EMI same & reduce tenure".
""")

st.caption("Built for accurate what-if analysis on Normal EMI and Interest-Only (OD/Gold) loans • All calculations are simulated month-by-month")