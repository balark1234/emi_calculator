#!/usr/bin/env python3
"""
EMI Calculator - Full Version with Extra Payments + Start Date
"""

import pandas as pd
import numpy as np
from datetime import datetime
from dateutil.relativedelta import relativedelta
import io

try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def format_inr(amount: float, compact: bool = False) -> str:
    if amount is None:
        return "₹ 0.00"
    n = float(amount)
    sign = "₹ " if n >= 0 else "-₹ "
    n = abs(n)
    if compact:
        if n >= 10000000:
            return f"{sign}{n/10000000:.2f} Cr"
        elif n >= 100000:
            return f"{sign}{n/100000:.2f} Lakh"
        else:
            return f"{sign}{n:,.2f}"
    else:
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


def calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    if annual_rate <= 0:
        return round(principal / tenure_months, 2)
    monthly_rate = annual_rate / 12 / 100
    if monthly_rate == 0:
        return round(principal / tenure_months, 2)
    emi = principal * monthly_rate * (1 + monthly_rate) ** tenure_months / \
          ((1 + monthly_rate) ** tenure_months - 1)
    return round(emi, 2)


def generate_schedule(principal, annual_rate, tenure_months, loan_type="normal", 
                      monthly_emi=None, extras=None, start_date=None):
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

    # Create extra payment map
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

    for month_num in range(1, tenure_months + 200):
        if outstanding <= 0.01:
            break

        interest = outstanding * monthly_rate
        extra_this_month = extra_map.get(month_num, 0.0)

        if loan_type == "normal":
            payment = current_payment
            if outstanding + interest < payment + 1:
                payment = outstanding + interest
            interest_component = interest
            principal_component = min(payment - interest_component, outstanding)
        else:
            interest_component = interest
            principal_component = extra_this_month
            payment = interest_component + principal_component
            if month_num == tenure_months:
                bullet = max(0, outstanding - principal_component)
                principal_component += bullet
                payment = interest_component + principal_component

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

    df = pd.DataFrame(schedule)
    return df, {}


def make_display_schedule(df):
    if df.empty:
        return df
    display_df = df.copy()
    for col in ["Payment (₹)", "Interest (₹)", "Principal (₹)", "Extra (₹)", 
                "Outstanding Principal (₹)", "Cumulative Interest (₹)"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: format_inr(x))
    return display_df


def show_yearly_schedule_with_selection(schedule_df):
    if schedule_df.empty:
        return

    schedule_df = schedule_df.copy()
    schedule_df['Year'] = pd.to_datetime(schedule_df['Payment Date'], format='%d %b %Y').dt.year
    years = sorted(schedule_df['Year'].unique())

    st.markdown("**Repayment Schedule (Click any year to expand)**")

    for year in years:
        year_data = schedule_df[schedule_df['Year'] == year]
        total_payment = year_data['Payment (₹)'].sum()
        total_interest = year_data['Interest (₹)'].sum()
        ending_balance = year_data['Outstanding Principal (₹)'].iloc[-1]

        with st.expander(
            f"**Year {year}** — Payment: {format_inr(total_payment, compact=True)} | "
            f"Interest: {format_inr(total_interest, compact=True)} | "
            f"Ending Balance: {format_inr(ending_balance, compact=True)}"
        ):
            monthly_display = make_display_schedule(year_data.drop(columns=['Year']))
            st.dataframe(monthly_display, use_container_width=True, hide_index=True)


if STREAMLIT_AVAILABLE:
    st.set_page_config(page_title="EMI Calculator", layout="wide")
    st.title("💰 EMI Calculator")
    st.markdown("**Normal Reducing EMI** • **Interest-Only (OD/Gold)**")

    loan_type = st.radio("Loan Type", ["Normal Reducing EMI", "Interest-Only (OD/Gold)"], horizontal=True)
    loan_type_key = "normal" if "Normal" in loan_type else "interest_only"

    col1, col2, col3 = st.columns(3)
    with col1:
        principal = st.number_input("Principal Amount (₹)", 100000, 50000000, 2500000, 50000)
    with col2:
        annual_rate = st.number_input("Interest Rate (%)", 6.0, 18.0, 9.5, 0.1)
    with col3:
        tenure_months = st.number_input("Tenure (Months)", 12, 360, 240, 1)

    base_monthly = calculate_emi(principal, annual_rate, tenure_months) if loan_type_key == "normal" else round(principal * (annual_rate / 12 / 100), 2)

    st.metric("Monthly Payment", format_inr(base_monthly, compact=True))

    # ====================== EXTRA PAYMENTS ======================
    st.subheader("Extra Payments (Part Payments)")

    col_e1, col_e2 = st.columns(2)
    with col_e1:
        adhoc_amount = st.number_input("One-time Extra Payment (₹)", min_value=0, value=0, step=10000)
    with col_e2:
        rec_amount = st.number_input("Recurring Extra Payment (₹)", min_value=0, value=0, step=1000)
        freq = st.selectbox("Frequency", ["Every Month", "Every 3 Months", "Every 6 Months", "Every 12 Months"])

    # Build extras list
    extras_list = []
    if adhoc_amount > 0:
        extras_list.append({"month": 1, "amount": adhoc_amount})
    if rec_amount > 0:
        step_map = {"Every Month": 1, "Every 3 Months": 3, "Every 6 Months": 6, "Every 12 Months": 12}
        step = step_map.get(freq, 1)
        for m in range(1, tenure_months + 1, step):
            extras_list.append({"month": m, "amount": rec_amount})

    # Optional Start Date
    with st.expander("Advanced Options (Optional)"):
        start_date = st.date_input("Start Date", value=datetime.now().date())

    schedule_df, _ = generate_schedule(
        principal=principal,
        annual_rate=annual_rate,
        tenure_months=tenure_months,
        loan_type=loan_type_key,
        monthly_emi=base_monthly,
        extras=extras_list,
        start_date=datetime.combine(start_date, datetime.min.time())
    )

    st.subheader("Repayment Schedule")
    if not schedule_df.empty:
        show_yearly_schedule_with_selection(schedule_df)

        csv_buffer = io.StringIO()
        schedule_df.to_csv(csv_buffer, index=False)
        st.download_button("⬇️ Download Full Schedule (CSV)", csv_buffer.getvalue(), "schedule.csv", "text/csv")

        st.divider()

        # Chart
        st.subheader("Yearly Payment Breakdown & Outstanding Balance")
        if PLOTLY_AVAILABLE:
            tmp = schedule_df.copy()
            tmp['Year'] = pd.to_datetime(tmp['Payment Date'], format='%d %b %Y').dt.year
            yg = tmp.groupby('Year').agg({
                'Principal (₹)': 'sum',
                'Interest (₹)': 'sum',
                'Outstanding Principal (₹)': 'last'
            }).reset_index()
            yg.columns = ['Year', 'Principal', 'Interest', 'Balance']

            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Bar(x=yg['Year'], y=yg['Principal'], name='Principal', marker_color='#27ae60'), secondary_y=False)
            fig.add_trace(go.Bar(x=yg['Year'], y=yg['Interest'], name='Interest', marker_color='#e67e22'), secondary_y=False)
            fig.add_trace(go.Scatter(x=yg['Year'], y=yg['Balance'], name='Outstanding Balance', mode='lines+markers',
                                     line=dict(color='#8e44ad', width=3), marker=dict(size=7)), secondary_y=True)
            fig.update_layout(barmode='stack', height=480, title_text="Yearly Principal + Interest + Outstanding Balance")
            fig.update_layout(xaxis=dict(fixedrange=True), yaxis=dict(fixedrange=True), yaxis2=dict(fixedrange=True))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.caption("Green = Principal | Orange = Interest | Purple = Outstanding Balance")
        else:
            st.warning("Install plotly: pip install plotly")
    else:
        st.warning("Could not generate schedule")