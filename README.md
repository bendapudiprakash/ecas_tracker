# 📊 Indian eCAS Multi-PAN Family Portfolio & Transaction Analytics Engine

An automated, privacy-focused Python engine and 5-tab interactive HTML dashboard that processes **Indian NSDL & CDSL eCAS (Consolidated Account Statement) PDFs** across single or **multiple family mailboxes** to track multi-asset portfolio growth, calculate point-in-time **Window Range XIRR performance**, compute **Zerodha Console-style Unitized NAV curves**, and extract an audited **transaction log**.

---

## 🚀 Live Demo Sample Report Preview

Want to see what this engine produces without setting up real PDFs? You can view the sample report previews anytime:

- **🎨 Sample Dashboard Preview**: **[docs/sample_dashboard.html](docs/sample_dashboard.html)**
- **📜 Sample Transactions CSV**: **[docs/sample_transactions.csv](docs/sample_transactions.csv)**

---

## 🌟 Key Features

- **🔒 Privacy-First Local Processing**: Operates completely offline on your local machine using SQLite (`cas_tracker.db`). Environment credentials (`.env`) are loaded strictly at runtime.
- **👨‍👩‍👧‍👦 Multi-PAN & Family Portfolio Views**:
  - Automatically identifies statements belonging to different family members (PANs).
  - Provides a top **Family Member Switcher** in the UI to toggle between **Consolidated Family View (All PANs Combined)** and individual family member views.
- **📅 Point-in-Time Date Range Filter (`From Period` → `To Period`)**:
  - Select any historical starting and ending statement periods (e.g. `JAN 2022` to `DEC 2024`).
  - Instantly re-slices all charts, holdings tables, and KPI cards across the entire dashboard to evaluate performance over any custom timeframe.
- **⚡ Window-Specific Dynamic Range XIRR & Realized Gain Engine**:
  - Pre-computed Window Range XIRR matrix (`range_xirr_matrix`) computing exact money-weighted annualized returns for any selected date window.
  - Dynamically tracks **Starting Valuation ($V_{start}$)**, **Net Capital Injected / Withdrawn**, **Unrealized Market Gain**, and **Realized Gain / Loss** from closed redemptions.
- **📧 Multi-Mailbox Sync & Password Mapping (`python run.py --sync`)**:
  - Connects to multiple Gmail/IMAP mailboxes (e.g. self, spouse, parent), downloads new eCAS PDFs incrementally (`SINCE <date>`), and maps individual eCAS PDF passwords per mailbox.
- **📈 Zerodha Console Portfolio Performance Curve (Base 100)**:
  - Implements Zerodha's unitized NAV methodology isolating true organic market returns from cash deposits and withdrawals:
    $$\text{NAV}_t = \text{NAV}_{t-1} \times (1 + r_t)$$
- **📜 Strict Real Trade Transaction Extractor (`tracker_engine/output/transactions.csv`)**:
  - Filters out monthly snapshot holdings to extract strictly actual trade transactions (*SIPs, Purchases, Redemptions, Demat Stock Credits & Debits*).
- **🎨 5-Tab Modern Interactive Dashboard (`tracker_engine/output/dashboard.html`)**:
  1. **💵 Portfolio Value & Trajectory**: Summary cards (Valuation, Starting Base, Inflows/Withdrawals, Range XIRR, Unrealized Gain, Realized Gain), combined line chart, Category Doughnut, MoM Category Delta Table, and Holdings Search Filter.
  2. **⚡ Category XIRR Performance**: Category XIRR comparison bar charts, Capital Deployed vs Current Valuation, and XIRR table.
  3. **📈 Zerodha Console Performance Curve**: Unitized NAV curve (Base 100) vs Absolute Valuation.
  4. **📜 Full Transactions Log**: Paginated transaction log with live search, asset class filters, and CSV export.
  5. **🤖 AI Insights**: Executive portfolio diagnostics and structural recommendations.

---

## 📁 Project Architecture & Layout

```
cas_tracker/
├── run.py                      # Main CLI entrypoint
├── cas_passwords.json          # Encrypted PDF password mapping config
├── tracker_engine/             # Core Python backend engine
│   ├── input/                  # eCAS PDF statement store (gitignored)
│   ├── output/                 # Generated dashboard.html & Excel workbook (gitignored)
│   ├── cas_tracker.db          # Local SQLite cache database (gitignored)
│   └── src/                    # Backend analytics, parsers, finance, & reporting
│       ├── analytics/          # Growth tracker & NAV engines
│       ├── fetchers/           # Multi-mailbox IMAP fetcher
│       ├── parsers/            # NSDL/CDSL eCAS PDF extractor
│       ├── finance/            # Newton-Raphson XIRR & Cost Basis engines
│       ├── reporting/          # Interactive Chart.js HTML & Excel report generators
│       └── ai/                 # Gemini AI portfolio insights engine
├── android_app/                # Native Android Kotlin App (gitignored)
├── docs/                       # Synthetic sample report artifacts for GitHub preview
│   ├── sample_dashboard.html   # Standalone HTML sample report
│   └── sample_transactions.csv # Sample transaction audit trail
├── .env.example                # Environment configuration template
├── tracker_engine/requirements.txt # Project dependencies
├── .gitignore                  # Ignores input/, output/, android_app/, .env, cas_tracker.db
└── README.md                   # Project documentation
```

---

## 🚀 Quickstart Guide

### 1. Prerequisites & Installation

Clone the repository and set up a virtual environment:

```bash
git clone https://github.com/your-username/cas_tracker.git
cd cas_tracker

python3 -m venv .venv
source .venv/bin/activate
pip install -r tracker_engine/requirements.txt
```

### 2. Environment Configuration (`.env`)

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

#### Option A: Single Mailbox Setup
```env
GMAIL_USER=your_email@gmail.com
GMAIL_APP_PASSWORD=your_16_char_app_password
PDF_PASSWORD=YOUR_PAN_NUMBER
```

#### Option B: Multi-Mailbox & Family Portfolio Setup
```env
# Family Member 1 (Self)
MAILBOX_1_USER=user1@gmail.com
MAILBOX_1_APP_PASSWORD=app_pass_1
MAILBOX_1_PDF_PASSWORD=PAN1_PASSWORD

# Family Member 2 (Spouse / Parent)
MAILBOX_2_USER=user2@gmail.com
MAILBOX_2_APP_PASSWORD=app_pass_2
MAILBOX_2_PDF_PASSWORD=PAN2_PASSWORD
```

> ⚠️ **Note**: `.env` is ignored by Git and will never be committed to your repository.

---

## 💻 CLI Usage Commands

### Fast Local Execution (Default Mode)

Process existing PDFs in `tracker_engine/input/` and SQLite cache without network calls:

```bash
python run.py
```

### Incremental Multi-Mailbox Sync Mode (`--sync` / `-s`)

Fetch only new eCAS statements received across all configured mailboxes since the latest date in SQLite:

```bash
python run.py --sync
```

### Force Full Mailbox Re-Sync (`--force-all`)

Search entire mailbox history for all historic eCAS statements:

```bash
python run.py --force-all
```

---

## 📊 Dashboard & Output Artifacts

Running the pipeline automatically generates:
1. **[tracker_engine/output/dashboard.html](tracker_engine/output/dashboard.html)**: 5-tab interactive web dashboard with Multi-PAN Family View filtering.
2. **[tracker_engine/output/ecas_portfolio_tracker.xlsx](tracker_engine/output/ecas_portfolio_tracker.xlsx)**: Complete Excel & Google Sheets workbook.
3. **[tracker_engine/output/transactions.csv](tracker_engine/output/transactions.csv)**: Full audit log of all trade transactions.

---

## 🛡 Privacy & Security

- **No Third-Party APIs**: All PDF extraction and financial math are computed locally.
- **Masked Investor Profile**: Investor Name, PAN, and Sync Email are safely masked in the UI.
- **Git Safety**: `tracker_engine/input/`, `tracker_engine/output/`, `android_app/`, `.env`, and `cas_tracker.db` are strictly ignored by `.gitignore`.

---

## 📄 License

MIT License. Developed for automated eCAS portfolio tracking and analytics.
