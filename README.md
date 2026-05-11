# 💰 Advanced EMI Calculator (Normal + OD/Gold Loans)

A powerful, interactive EMI calculator built with Streamlit that supports:

- **Normal Reducing Balance EMI Loans** (Principal + Interest)
- **Interest-Only Loans** (OD / Gold Loans) with bullet principal repayment
- **Adhoc one-time prepayments**
- **Recurring extra payments** (monthly, quarterly, half-yearly, yearly)
- Impact analysis: Interest saved + Tenure reduced
- Remaining principal checker at any month
- Full Indian number formatting (Lakhs & Crores)

## Features

- Two loan types in one app
- Interactive sliders and inputs
- Month-by-month repayment schedule
- What-if analysis with extra payments
- Clean vertical layout inspired by emicalculator.net
- Proper Indian numbering system (₹10.00 Lakh / ₹1.25 Cr)

## How to Run Locally

### 1. Clone the repository
```bash
git clone https://github.com/balark1234/emi_calculator.git
cd emi_calculator
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the app
```bash
streamlit run emi_calculator_app.py
```

The app will open automatically in your browser.

## Project Structure

```
emi-calculator/
├── emi_calculator_app.py    # Main Streamlit application
├── requirements.txt         # Python dependencies
└── README.md
```

## Updates

This repository is actively maintained. To get the latest version:

```bash
git pull
```

## Built With

- Python
- Streamlit
- Pandas

---

**Note**: This tool is for educational and personal financial planning purposes. Always consult your bank or financial advisor for official calculations.