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
    """
    if extras is None:
        extras = []
    if start_date is None:
        start_date = datetime.now().replace(day=1)

    monthly_rate = annual_rate / 12 / 100.0

    if monthly_emi is None:
        if loan_type == "normal":
            monthly_emi = calculate_emi(principal, annual_rate, tenure_months)
        else:
            monthly_emi = round(principal * monthly_rate, 2)

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

    max_months = tenure_months + 120
    actual_tenure = tenure_months

    for month_num in range(1, max_months + 1):
        if outstanding <= 0.01:
            actual_tenure = month_num - 1
            break

        interest = outstanding * monthly_rate
        extra_this_month = extra_map.get(month_num, 0.0)

        if loan_type == "normal":
            payment = current_payment
            if outstanding + interest < payment + 1:
                payment = outstanding + interest

            interest_component = interest
            principal_component = payment - interest_component

            if principal_component > outstanding:
                principal_component = outstanding
                payment = interest_component + principal_component

        else:
            interest_component = interest
            principal_component = extra_this_month
            payment = interest_component + principal_component

            is_final_month = (month_num == tenure_months)
            remaining_after_extra = outstanding - principal_component
            if is_final_month or remaining_after_extra <= 0.01:
                bullet = max(0, outstanding - principal_component)
                principal_component += bullet
                payment += bullet

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

    original_total_interest = 0.0
    if loan_type == "normal" and monthly_emi:
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


def show_yearly_schedule_with_expanders(schedule_df: pd.DataFrame):
    """Group schedule by year and show with expandable monthly details."""
    if schedule_df.empty:
        return

    schedule_df = schedule_df.copy()
    schedule_df['Year'] = pd.to_datetime(schedule_df['Payment Date']).dt.year

    years = schedule_df['Year'].unique()

    for year in years:
        year_data = schedule_df[schedule_df['Year'] == year]

        total_payment = year_data['Payment (₹)'].sum()
        total_interest = year_data['Interest (₹)'].sum()
        total_principal = year_data['Principal (₹)'].sum()
        ending_balance = year_data['Outstanding Principal (₹)'].iloc[-1]

        with st.expander(f"**Year {year}** | Payment: {format_inr(total_payment, compact=True)} | Interest: {format_inr(total_interest, compact=True)} | Ending Balance: {format_inr(ending_balance, compact=True)}"):
            monthly_display = make_display_schedule(year_data.drop(columns=['Year']))
            st.dataframe(monthly_display, use_container_width=True, hide_index=True)


# ====================== STREAMLIT UI ======================

if STREAMLIT_AVAILABLE:
    st.set_page_config(
        page_title="EMI Calculator - Normal & OD/Gold Loans",
        page_icon="💰",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stMetricValue"] { font-size: 28px !important; font-weight: 700 !important; color: #1a5f3c; }
    [data-testid="stMetric"] { background-color: #f8f9fa; border: 1px solid #e9ecef; border-radius: 10px; padding: 14px 18px; box-shadow: 0 2px 6px rgba(0,0,0,0.06); }
    .stDataFrame { font-size: 14px !important; border-radius: 8px; }
    label, .stNumberInput label { font-size: 15px !important; font-weight: 500 !important; }
    .main .block-container { max-width: 1100px !important; padding-top: 1rem; padding-left: 2rem; padding-right: 2rem; }
    h2, h3 { color: #1a5f3c; font-weight: 600; }
    </style>
    """, unsafe_allow_html=True)

st.title("💰 EMI Calculator")
st.markdown("**Normal Loans** (Principal + Interest)  •  **OD / Gold Loans** (Interest Only)")

# ====================== TOP INPUTS ======================
st.subheader("Loan Details")

loan_type = st.radio(
    "Loan Type",
    ["Normal Reducing EMI", "Interest-Only (OD/Gold)"],
    index=0,
    horizontal=True
)
loan_type_key = "normal" if "Normal" in loan_type else "interest_only"

st.markdown("---")

# Main inputs stacked vertically
principal = st.number_input(
    "Principal Amount (₹)", 
    min_value=10000, 
    max_value=100000000, 
    value=1000000, 
    step=10000, 
    format="%d"
)

annual_rate = st.number_input(
    "Interest Rate (%)", 
    min_value=1.0, 
    max_value=36.0, 
    value=10.5, 
    step=0.1
)

tenure_months = st.number_input(
    "Tenure (Months)", 
    min_value=3, 
    max_value=360, 
    value=60, 
    step=1
)

# Start Date moved to bottom as optional
with st.expander("Advanced Options (Optional)"):
    start_date = st.date_input(
        "Start Date (for schedule display)", 
        value=datetime.now().date(),
        help="This only affects the dates shown in the schedule. It does not impact calculations."
    )

st.divider()

# ====================== RESULTS ======================
if loan_type_key == "normal":
    base_monthly = calculate_emi(principal, annual_rate, tenure_months)
else:
    base_monthly = round(principal * (annual_rate / 12 / 100), 2)

total_original_interest = (base_monthly * tenure_months) - principal if loan_type_key == "normal" else (principal * (annual_rate / 12 / 100) * tenure_months)

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Monthly Payment", format_inr(base_monthly, compact=True))
with col2:
    st.metric("Total Interest", format_inr(total_original_interest, compact=True))
with col3:
    st.metric("Total Payable", format_inr(principal + total_original_interest, compact=True))

st.divider()

# ====================== EXTRA PAYMENTS (Reactive - No Add Button) ======================
st.subheader("Extra Payments (Type & See Changes Instantly)")

col_e1, col_e2 = st.columns(2)

with col_e1:
    st.markdown("**Adhoc Prepayment**")
    adhoc_amount = st.number_input("One-time Extra Amount (₹)", min_value=0, value=0, step=10000, help="Applied from next EMI")
with col_e2:
    st.markdown("**Recurring Extra**")
    rec_amount = st.number_input("Extra Amount per time (₹)", min_value=0, value=0, step=1000)
    freq = st.selectbox("Frequency", ["Every Month", "Every 3 Months", "Every 6 Months", "Every 12 Months"])

extras_list = []
if adhoc_amount > 0:
    extras_list.append({"month": 1, "amount": adhoc_amount})
if rec_amount > 0:
    step_map = {"Every Month": 1, "Every 3 Months": 3, "Every 6 Months": 6, "Every 12 Months": 12}
    step = step_map.get(freq, 1)
    for m in range(1, tenure_months + 1, step):
        extras_list.append({"month": m, "amount": rec_amount})

schedule_df, _ = generate_schedule(
    principal=principal,
    annual_rate=annual_rate,
    tenure_months=tenure_months,
    loan_type=loan_type_key,
    monthly_emi=base_monthly,
    extras=extras_list,
    start_date=datetime.combine(start_date, datetime.min.time())
)

st.divider()

# ====================== YEARLY SCHEDULE + OUTSTANDING BALANCE CHART ======================
st.subheader("Repayment Schedule (Click Year to Expand)")

if not schedule_df.empty:
    show_yearly_schedule_with_expanders(schedule_df)
    
    csv_buffer = io.StringIO()
    schedule_df.to_csv(csv_buffer, index=False)
    st.download_button("⬇️ Download Full Monthly Schedule (CSV)", csv_buffer.getvalue(), "full_schedule.csv", "text/csv")
    
    st.divider()
    
    st.subheader("Outstanding Loan Balance Over Years")
    
    schedule_df_temp = schedule_df.copy()
    schedule_df_temp['Year'] = pd.to_datetime(schedule_df_temp['Payment Date']).dt.year
    
    yearly_balance = schedule_df_temp.groupby('Year')['Outstanding Principal (₹)'].last().reset_index()
    yearly_balance.columns = ['Year', 'Outstanding Balance']
    yearly_balance = yearly_balance.set_index('Year')
    
    st.line_chart(yearly_balance, use_container_width=True)
    st.caption("This chart shows how your outstanding principal balance reduces every year.")
else:
    st.warning("Could not generate schedule. Please check your inputs.")