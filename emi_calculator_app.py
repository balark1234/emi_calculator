#!/usr/bin/env python3
"""
EMI Calculator - Final Clean Version
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

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False


def format_inr(amount, compact=False):
    if amount is None:
        return "₹ 0"
    n = float(amount)
    sign = "₹ " if n >= 0 else "-₹ "
    n = abs(n)
    if compact:
        if n >= 10000000: return f"{sign}{n/10000000:.2f} Cr"
        if n >= 100000: return f"{sign}{n/100000:.2f} Lakh"
        return f"{sign}{n:,.0f}"
    s = f"{n:,.2f}"
    int_part, dec = s.split('.')
    int_part = int_part.replace(',', '')
    if len(int_part) > 3:
        result = int_part[-3:]
        int_part = int_part[:-3]
        while int_part:
            result = int_part[-2:] + ',' + result
            int_part = int_part[:-2]
        int_part = result
    return f"{sign}{int_part}.{dec}"


def calculate_emi(principal, rate, tenure):
    if rate <= 0:
        return round(principal / tenure, 2)
    mr = rate / 12 / 100
    return round(principal * mr * (1 + mr)**tenure / ((1 + mr)**tenure - 1), 2)


def generate_schedule(principal, rate, tenure, loan_type="normal", emi=None, extras=None):
    if extras is None: extras = []
    start = datetime.now().replace(day=1)
    mr = rate / 12 / 100
    if emi is None:
        emi = calculate_emi(principal, rate, tenure) if loan_type == "normal" else round(principal * mr, 2)

    extra_map = {e.get("month", 0): e.get("amount", 0) for e in extras}
    rows = []
    bal = float(principal)

    for m in range(1, tenure + 200):
        if bal < 1: break
        interest = bal * mr
        extra = extra_map.get(m, 0)

        if loan_type == "normal":
            pay = emi
            if bal + interest < pay: pay = bal + interest
            prin = min(pay - interest, bal)
        else:
            pay = interest + extra
            prin = extra
            if m == tenure:
                prin += max(0, bal - prin)
                pay = interest + prin

        bal = max(0, bal - prin)
        d = start + relativedelta(months=m-1)
        rows.append({
            "Month": m,
            "Payment Date": d.strftime("%d %b %Y"),
            "Payment (₹)": round(pay, 2),
            "Interest (₹)": round(interest, 2),
            "Principal (₹)": round(prin, 2),
            "Extra (₹)": round(extra, 2),
            "Outstanding Principal (₹)": round(bal, 2)
        })
    return pd.DataFrame(rows), {}


def make_display(df):
    if df.empty: return df
    d = df.copy()
    for c in ["Payment (₹)", "Interest (₹)", "Principal (₹)", "Extra (₹)", "Outstanding Principal (₹)"]:
        if c in d.columns:
            d[c] = d[c].apply(lambda x: format_inr(x))
    return d


def show_yearly_schedule_with_selection(schedule_df):
    if schedule_df.empty: return

    df = schedule_df.copy()
    df['Year'] = pd.to_datetime(df['Payment Date'], format='%d %b %Y').dt.year
    years = sorted(df['Year'].unique())

    summary = []
    for y in years:
        yd = df[df['Year'] == y]
        summary.append({
            "Year": int(y),
            "Total Payment (₹)": yd['Payment (₹)'].sum(),
            "Total Interest (₹)": yd['Interest (₹)'].sum(),
            "Total Principal (₹)": yd['Principal (₹)'].sum(),
            "Ending Outstanding (₹)": yd['Outstanding Principal (₹)'].iloc[-1],
            "Months": len(yd)
        })

    ydf = pd.DataFrame(summary)
    disp = ydf.copy()
    for c in ["Total Payment (₹)", "Total Interest (₹)", "Total Principal (₹)", "Ending Outstanding (₹)"]:
        disp[c] = disp[c].apply(lambda x: format_inr(x, compact=True))

    st.markdown("**Yearly Summary** — Click any row to see monthly details")

    event = st.dataframe(
        disp, use_container_width=True, hide_index=True,
        selection_mode="single-row", on_select="rerun", key="yearly_table"
    )

    selected_year = None
    if event.selection.rows:
        selected_year = int(ydf.iloc[event.selection.rows[0]]["Year"])

    if selected_year is not None:
        st.divider()
        st.markdown(f"**Monthly Details for Year {selected_year}**")
        yd = df[df['Year'] == selected_year]
        st.dataframe(make_display(yd.drop(columns=['Year'])), use_container_width=True, hide_index=True)
    else:
        st.caption("Click any year row above")


if STREAMLIT_AVAILABLE:
    st.set_page_config(page_title="EMI Calculator", layout="wide")
    st.title("💰 EMI Calculator")

    loan_type = st.radio("Loan Type", ["Normal Reducing EMI", "Interest Only (OD/Gold)"], horizontal=True)
    ltype = "normal" if "Normal" in loan_type else "interest_only"

    c1, c2, c3 = st.columns(3)
    with c1: principal = st.number_input("Principal Amount (₹)", 100000, 50000000, 2500000, 50000)
    with c2: rate = st.number_input("Interest Rate (%)", 6.0, 18.0, 9.5, 0.1)
    with c3: tenure = st.number_input("Tenure (Months)", 12, 360, 240, 1)

    emi = calculate_emi(principal, rate, tenure) if ltype == "normal" else round(principal * (rate/12/100), 2)
    st.metric("Monthly Payment", format_inr(emi, compact=True))

    sched, _ = generate_schedule(principal, rate, tenure, ltype, emi, [])

    st.subheader("Repayment Schedule")
    if not sched.empty:
        show_yearly_schedule_with_selection(sched)

        csv = io.StringIO()
        sched.to_csv(csv, index=False)
        st.download_button("⬇️ Download Full Schedule (CSV)", csv.getvalue(), "schedule.csv", "text/csv")

        st.divider()
        st.subheader("Yearly Payment Breakdown & Outstanding Balance")

        if PLOTLY_AVAILABLE:
            tmp = sched.copy()
            tmp['Year'] = pd.to_datetime(tmp['Payment Date'], format='%d %b %Y').dt.year
            yg = tmp.groupby('Year').agg({'Principal (₹)':'sum', 'Interest (₹)':'sum', 'Outstanding Principal (₹)':'last'}).reset_index()
            yg.columns = ['Year','Principal','Interest','Balance']

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
            st.warning("Please install plotly: pip install plotly")
    else:
        st.warning("Could not generate schedule")
