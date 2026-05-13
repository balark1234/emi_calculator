#!/usr/bin/env python3
"""
EMI Calculator Web App - Streamlit (Corrected & Updated)
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

# Try to import Streamlit
try:
    import streamlit as st
    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False
    st = None

# ====================== PLOTLY IMPORT (FIXED) ======================
try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


# ====================== INDIAN NUMBER FORMATTING ======================

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


# ====================== CORE CALCULATION FUNCTIONS ======================

def calculate_emi(principal: float, annual_rate: float, tenure_months: int) -> float:
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
    if df.empty:
        return df
    display_df = df.copy()
    money_cols = ["Payment (₹)", "Interest (₹)", "Principal (₹)", "Extra (₹)", 
                  "Outstanding Principal (₹)", "Cumulative Interest (₹)"]
    for col in money_cols:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: format_inr(x, compact=False))
    return display_df


def show_yearly_schedule_with_selection(schedule_df: pd.DataFrame):
    if schedule_df.empty:
        return

    schedule_df = schedule_df.copy()
    schedule_df['Year'] = pd.to_datetime(schedule_df['Payment Date'], format='%d %b %Y').dt.year

    years = sorted(schedule_df['Year'].unique())

    yearly_summary = []
    for year in years:
        year_data = schedule_df[schedule_df['Year'] == year]
        yearly_summary.append({
            "Year": int(year),
            "Total Payment (₹)": year_data['Payment (₹)'].sum(),
            "Total Interest (₹)": year_data['Interest (₹)'].sum(),
            "Total Principal (₹)": year_data['Principal (₹)'].sum(),
            "Ending Outstanding (₹)": year_data['Outstanding Principal (₹)'].iloc[-1],
            "Months": len(year_data)
        })

    yearly_df = pd.DataFrame(yearly_summary)
    display_yearly = yearly_df.copy()
    for col in ["Total Payment (₹)", "Total Interest (₹)", "Total Principal (₹)", "Ending Outstanding (₹)"]:
        display_yearly[col] = display_yearly[col].apply(lambda x: format_inr(x, compact=True))

    st.markdown("**Yearly Repayment Summary** — Click any row to see monthly details")

    event = st.dataframe(
        display_yearly,
        use_container_width=True,
        hide_index=True,
        selection_mode="single-row",
        on_select="rerun",
        key="yearly_schedule_table"
    )

    selected_year = None
    if event.selection.rows:
        selected_idx = event.selection.rows[0]
        selected_year = int(yearly_df.iloc[selected_idx]["Year"])

    if selected_year is not None:
        st.divider()
        st.markdown(f"**Monthly Details for Year {selected_year}**")
        year_data = schedule_df[schedule_df['Year'] == selected_year]
        monthly_display = make_display_schedule(year_data.drop(columns=['Year']))
        st.dataframe(monthly_display, use_container_width=True, hide_index=True)
    else:
        st.caption("👆 Click any year row above to view its monthly breakdown")


# ====================== STREAMLIT UI ======================

if STREAMLIT_AVAILABLE:
    st.set_page_config(
        page_title="EMI Calculator - Normal & OD/Gold Loans",
        page_icon="💰",
        layout="wide"
    )

    st.title("💰 EMI Calculator")
    st.markdown("**Normal Reducing EMI** • **Interest-Only (OD/Gold)**")

    loan_type = st.radio(
        "Loan Type",
        ["Normal Reducing EMI", "Interest-Only (OD/Gold)"],
        index=0,
        horizontal=True
    )
    loan_type_key = "normal" if "Normal" in loan_type else "interest_only"

    st.subheader("Loan Details")

    col1, col2, col3 = st.columns(3)
    with col1:
        principal = st.number_input("Principal Amount (₹)", 100000, 50000000, 2500000, 50000)
    with col2:
        annual_rate = st.number_input("Interest Rate (%)", 6.0, 18.0, 9.5, 0.1)
    with col3:
        tenure_months = st.number_input("Tenure (Months)", 12, 360, 240, 1)

    base_monthly = calculate_emi(principal, annual_rate, tenure_months) if loan_type_key == "normal" else round(principal * (annual_rate / 12 / 100), 2)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Monthly Payment", format_inr(base_monthly, compact=True))
    with col2:
        total_int = (base_monthly * tenure_months) - principal if loan_type_key == "normal" else principal * (annual_rate / 12 / 100) * tenure_months
        st.metric("Total Interest", format_inr(total_int, compact=True))
    with col3:
        st.metric("Total Payable", format_inr(principal + total_int, compact=True))

    st.divider()

    extras_list = []

    schedule_df, _ = generate_schedule(
        principal=principal,
        annual_rate=annual_rate,
        tenure_months=tenure_months,
        loan_type=loan_type_key,
        monthly_emi=base_monthly,
        extras=extras_list
    )

    st.subheader("Repayment Schedule")

    if not schedule_df.empty:
        show_yearly_schedule_with_selection(schedule_df)

        csv_buffer = io.StringIO()
        schedule_df.to_csv(csv_buffer, index=False)
        st.download_button("⬇️ Download Full Monthly Schedule (CSV)", csv_buffer.getvalue(), "full_schedule.csv", "text/csv")

        st.divider()

        # ====================== OUTSTANDING BALANCE CHART ======================
        st.subheader("Yearly Payment Breakdown & Outstanding Balance")

        if PLOTLY_AVAILABLE:
            schedule_df_temp = schedule_df.copy()
            schedule_df_temp['Year'] = pd.to_datetime(schedule_df_temp['Payment Date'], format='%d %b %Y').dt.year

            yearly_data = schedule_df_temp.groupby('Year').agg({
                'Principal (₹)': 'sum',
                'Interest (₹)': 'sum',
                'Outstanding Principal (₹)': 'last'
            }).reset_index()
            yearly_data.columns = ['Year', 'Principal', 'Interest', 'Balance']

            fig = make_subplots(specs=[[{{"secondary_y": True}}]])

            fig.add_trace(
                go.Bar(x=yearly_data['Year'], y=yearly_data['Principal'], name='Principal', marker_color='#27ae60'),
                secondary_y=False
            )
            fig.add_trace(
                go.Bar(x=yearly_data['Year'], y=yearly_data['Interest'], name='Interest', marker_color='#e67e22'),
                secondary_y=False
            )
            fig.add_trace(
                go.Scatter(
                    x=yearly_data['Year'],
                    y=yearly_data['Balance'],
                    name='Outstanding Balance',
                    mode='lines+markers',
                    line=dict(color='#8e44ad', width=3),
                    marker=dict(size=7)
                ),
                secondary_y=True
            )

            fig.update_layout(
                barmode='stack',
                height=480,
                title_text="Yearly Principal + Interest (Stacked) + Outstanding Balance",
                hovermode="x unified"
            )
            fig.update_layout(
                xaxis=dict(fixedrange=True),
                yaxis=dict(fixedrange=True),
                yaxis2=dict(fixedrange=True)
            )

            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            st.caption("Green = Principal | Orange = Interest | Purple Line = Outstanding Balance at year end")
        else:
            st.warning("Plotly not installed. Install it with: pip install plotly")
            st.line_chart(schedule_df.set_index('Year')['Outstanding Principal (₹)'] if 'Year' in schedule_df.columns else pd.DataFrame())
    else:
        st.warning("Could not generate schedule. Please check your inputs.")