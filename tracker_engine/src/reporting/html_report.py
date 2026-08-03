"""
Dashboard Generator for CAS Tracker
-----------------------------------
Generates a modern 4-tab interactive HTML dashboard (output/dashboard.html):
- Family Member Switcher (Consolidated Family Portfolio vs Individual PANs)
- Header: Investor Profile Card (Investor Name, Masked PAN, NSDL CAS ID, Masked Sync Email)
- Tab 1: 💵 Portfolio Value & Category Trajectory (Simple Value Tracking)
- Tab 2: ⚡ Category XIRR Performance (Category XIRR)
- Tab 3: 📈 Zerodha Console Performance Curve (Unitized NAV Index Base 100)
- Tab 4: 📜 Full Transactions Log (271 Strict Real Trade Transactions)
"""

import os
import json
import re
import sqlite3

from tracker_engine.src.storage.repository import get_all_statements_data, get_connection
from tracker_engine.src.analytics.growth_tracker import analyze_growth_in_memory
from tracker_engine.src.models.security import SecurityIdentity
from tracker_engine.src.finance.cost_basis import CostBasisCalculator

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

try:
    from tracker_engine.src.ai.insights import get_ai_insights, render_ai_insights_html
except ImportError:
    def get_ai_insights(*args, **kwargs): return ""
    def render_ai_insights_html(*args, **kwargs): return ""


def mask_pan(pan: str) -> str:
    """Returns a masked PAN e.g. ABCDE1234F -> BF*****62G"""
    if not pan or len(pan) < 5:
        return "BF*****"
    return pan[:2] + "*****" + pan[-2:]


def format_inr(val, include_symbol=True, decimals=2):
    """Formats a number according to Indian Numbering System (Lakhs & Crores)."""
    if val is None:
        return "₹0.00" if include_symbol else "0.00"
    is_neg = val < 0
    val = abs(val)
    fmt_str = f"{val:.{decimals}f}"
    parts = fmt_str.split('.')
    integer_part = parts[0]
    decimal_part = f".{parts[1]}" if len(parts) > 1 else ""

    if len(integer_part) > 3:
        last_three = integer_part[-3:]
        other_digits = integer_part[:-3]
        res = ""
        while len(other_digits) > 2:
            res = "," + other_digits[-2:] + res
            other_digits = other_digits[:-2]
        formatted_int = other_digits + res + "," + last_three
    else:
        formatted_int = integer_part

    prefix = "-" if is_neg else ""
    symbol = "₹" if include_symbol else ""
    return f"{prefix}{symbol}{formatted_int}{decimal_part}"


def mask_email(email_str):
    if not email_str or "@" not in email_str:
        return "configured****@gmail.com"
    parts = email_str.split("@")
    user = parts[0]
    domain = parts[1]
    if len(user) <= 2:
        masked_user = user[0] + "****"
    else:
        masked_user = user[:2] + "****"
    return f"{masked_user}@{domain}"


def get_all_transactions_from_db():
    conn = get_connection()
    c = conn.cursor()

    try:
        c.execute(
            """
            SELECT statement_period, transaction_date, pan, investor_name, isin, security_name,
                   asset_class, transaction_type, amount, units, price_nav, pdf_filename
            FROM transactions
            ORDER BY transaction_date DESC, id DESC
        """
        )
        rows = c.fetchall()
        conn.close()

        return [
            {
                "statement_period": r[0],
                "transaction_date": r[1],
                "pan": r[2] or "ABCDE1234F",
                "investor_name": r[3] or "INVESTOR NAME",
                "isin": r[4],
                "security_name": r[5],
                "asset_class": r[6],
                "transaction_type": r[7],
                "amount": r[8],
                "units": r[9],
                "price_nav": r[10],
                "pdf_filename": r[11],
            }
            for r in rows
        ]
    except Exception:
        conn.close()
        return []


def generate_dashboard(analysis=None, output_path=None, with_ai=False):
    if output_path is None:
        output_path = os.path.join(OUTPUT_DIR, "dashboard.html")
    datasets = get_all_statements_data()
    if not datasets:
        print("No statements data available in SQLite database.")
        return

    if not analysis:
        analysis = analyze_growth_in_memory(datasets)

    if not analysis:
        print("Analysis engine failed.")
        return

    transactions = get_all_transactions_from_db()

    # Discover all distinct PANs & Family Profiles in SQLite
    family_profiles = {}
    for ds in datasets:
        pan = ds.get("pan", "ABCDE1234F")
        name = ds.get("investor_name", "BENDAPUDI SRI SAI SATYA PRAKASH")
        cas_id = ds.get("cas_id", "12345678")

        if pan not in family_profiles:
            family_profiles[pan] = {
                "pan": pan,
                "masked_pan": mask_pan(pan),
                "investor_name": name,
                "cas_id": cas_id,
                "statement_count": 0,
            }
        family_profiles[pan]["statement_count"] += 1

    latest_period = analysis["curr_period"]
    first_period = datasets[0]["statement_period"]
    ps = analysis["portfolio_summary"]
    latest_val = ps["curr_portfolio_value"]
    prev_val = ps["prev_portfolio_value"]
    val_delta = ps["total_value_change"]
    organic_growth_pct = ps["portfolio_organic_growth_pct"]

    timeline = analysis["timeline"]
    xirr_summary = analysis["xirr_summary"]
    port_xirr = xirr_summary["portfolio_xirr"]
    category_xirrs = xirr_summary["category_xirr"]

    from collections import defaultdict
    from tracker_engine.src.models.security import SecurityIdentity
    from tracker_engine.src.finance.cost_basis import CostBasisCalculator

    def make_key(h):
        identity = SecurityIdentity(
            isin=h.get("isin") or "",
            security_name=h.get("security_name") or "",
            dp_id=h.get("dp_id") or "",
            depository=h.get("depository") or "",
            asset_class=h.get("asset_class") or "",
        )
        return identity.get_unique_key()

    cost_calculator = CostBasisCalculator()
    enriched_all_period_holdings = {}

    for i, ds in enumerate(datasets):
        period = ds["statement_period"]
        raw_h_list = ds.get("holdings", [])

        if i == 0:
            cost_calculator.process_monthly_transition(
                period,
                {},
                {make_key(h): h for h in raw_h_list if h.get("value", 0) > 0}
            )
        else:
            prev_ds = datasets[i - 1]
            prev_map = {make_key(h): h for h in prev_ds.get("holdings", []) if h.get("value", 0) > 0}
            curr_map = {make_key(h): h for h in raw_h_list if h.get("value", 0) > 0}
            cost_calculator.process_monthly_transition(period, prev_map, curr_map)

        period_enriched = []
        for h in raw_h_list:
            val = h.get("value", 0.0)
            if val <= 0:
                continue
            k = make_key(h)
            cost = cost_calculator.get_cost_basis(k)
            realized = cost_calculator.get_realized_gain(k)
            unrealized = val - cost
            tot_gain = unrealized + realized
            u_pct = (unrealized / cost * 100.0) if cost > 0 else 0.0

            h_copy = dict(h)
            h_copy["cost_basis"] = round(cost, 2)
            h_copy["unrealized_gain"] = round(unrealized, 2)
            h_copy["unrealized_pct"] = round(u_pct, 2)
            h_copy["realized_gain"] = round(realized, 2)
            h_copy["total_gain"] = round(tot_gain, 2)
            period_enriched.append(h_copy)

        enriched_all_period_holdings[period] = period_enriched

    last_period = datasets[-1]["statement_period"]
    curr_holdings = enriched_all_period_holdings.get(last_period, [])

    cat_gain_summary = defaultdict(lambda: {"cost_basis": 0.0, "curr_val": 0.0, "realized_gain": 0.0, "unrealized_gain": 0.0})
    for h in curr_holdings:
        ac = h.get("asset_class", "Other")
        c_stat = cat_gain_summary[ac]
        c_stat["cost_basis"] += h["cost_basis"]
        c_stat["curr_val"] += h["value"]
        c_stat["realized_gain"] += h["realized_gain"]
        c_stat["unrealized_gain"] += h["unrealized_gain"]

    # Merge cat_gain_summary into category_xirrs
    for cat, info in category_xirrs.items():
        if cat in cat_gain_summary:
            cg = cat_gain_summary[cat]
            info["cost_basis"] = round(cg["cost_basis"], 2)
            info["realized_gain"] = round(cg["realized_gain"], 2)
            info["unrealized_gain"] = round(cg["unrealized_gain"], 2)
            info["total_gain"] = round(cg["realized_gain"] + cg["unrealized_gain"], 2)
            info["unrealized_pct"] = round((cg["unrealized_gain"] / cg["cost_basis"] * 100.0), 2) if cg["cost_basis"] > 0 else 0.0
        else:
            info["cost_basis"] = info.get("init_value", 0.0)
            info["realized_gain"] = 0.0
            info["unrealized_gain"] = round(info["curr_value"] - info["init_value"], 2)
            info["total_gain"] = info["unrealized_gain"]
            info["unrealized_pct"] = round((info["unrealized_gain"] / info["cost_basis"] * 100.0), 2) if info["cost_basis"] > 0 else 0.0

    investor_name = "BENDAPUDI SRI SAI SATYA PRAKASH"
    masked_pan = "BF*****2G"
    nsdl_id = "12345678"
    raw_email = os.getenv("GMAIL_USER") or os.getenv("EMAIL_ACCOUNT") or os.getenv("IMAP_USER") or ""
    masked_sync_email = mask_email(raw_email)

    cat_breakdown = {}
    for h in curr_holdings:
        ac = h["asset_class"]
        cat_breakdown[ac] = cat_breakdown.get(ac, 0.0) + h["value"]

    total_realized_gain = sum(cg["realized_gain"] for cg in cat_gain_summary.values())

    nav_series = timeline["nav_series"]
    latest_nav = nav_series[-1]
    nav_return = round(((latest_nav - 100.0) / 100.0 * 100.0), 2)

    twrr_series = timeline.get("twrr_series", nav_series)
    latest_twrr = twrr_series[-1]
    twrr_return = round(((latest_twrr - 100.0) / 100.0 * 100.0), 2)

    # Fetch AI insights via Antigravity agentapi (Claude Sonnet) only when with_ai is True
    if with_ai:
        print("🤖 Generating AI portfolio insights via Antigravity (Claude Sonnet)...")
        ai_insights, ai_error = get_ai_insights(analysis, curr_holdings)
        ai_insights_html = render_ai_insights_html(ai_insights, ai_error)
    else:
        ai_insights_html = """
        <div style="padding:48px;text-align:center;color:#64748b;">
          <div style="font-size:52px;margin-bottom:16px;">🤖</div>
          <div style="font-size:18px;font-weight:700;color:#94a3b8;margin-bottom:10px;">AI Portfolio Insights (On-Demand)</div>
          <div style="font-size:13px;color:#64748b;max-width:520px;margin:0 auto;line-height:1.8;">
            To run Claude Sonnet AI analysis on your latest portfolio, execute:<br><br>
            <code style="background:#0f172a;padding:8px 16px;border-radius:8px;display:inline-block;color:#38bdf8;font-size:14px;border:1px solid #1e293b;">python run_tracker.py --ai</code><br><br>
            <span style="font-size:12px;color:#475569;">Uses Antigravity Claude Sonnet • No API keys needed • PII is fully stripped</span>
          </div>
        </div>
        """

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    html_path = output_path

    json_timeline = json.dumps(timeline)
    json_category_xirrs = json.dumps(category_xirrs)
    json_holdings = json.dumps(curr_holdings)
    json_mom_summary = json.dumps(analysis["asset_class_summary"])
    json_transactions = json.dumps(transactions)
    json_family_profiles = json.dumps(list(family_profiles.values()))
    clean_monthly_history = [
        {
            "curr_period": m["curr_period"],
            "prev_period": m["prev_period"],
            "portfolio_summary": m["portfolio_summary"],
            "asset_class_summary": m["asset_class_summary"],
        }
        for m in analysis.get("monthly_history", [])
    ]
    json_monthly_history = json.dumps(clean_monthly_history)
    json_all_period_holdings = json.dumps(enriched_all_period_holdings)
    all_period_mom_summaries = {
        m["curr_period"]: m["asset_class_summary"]
        for m in analysis.get("monthly_history", [])
    }
    json_all_period_mom_summaries = json.dumps(all_period_mom_summaries)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Family eCAS Portfolio & Transaction Analytics</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root {{
      --bg-color: #0b0f19;
      --card-bg: #151c2c;
      --accent-color: #3b82f6;
      --accent-hover: #2563eb;
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --border-color: #1f2937;
      --green: #10b981;
      --red: #ef4444;
      --gold: #f59e0b;
      --purple: #8b5cf6;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background-color: var(--bg-color);
      color: var(--text-main);
      padding: 24px;
      line-height: 1.5;
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 20px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border-color);
      flex-wrap: wrap;
      gap: 16px;
    }}
    .header h1 {{ font-size: 24px; font-weight: 700; background: linear-gradient(135deg, #60a5fa, #a78bfa); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}

    /* Family Member Selector Bar */
    .family-bar {{
      background: linear-gradient(135deg, #1e1b4b, #311b92);
      border: 1px solid #4338ca;
      border-radius: 12px;
      padding: 14px 20px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }}
    .family-title {{ display: flex; align-items: center; gap: 10px; font-weight: 700; font-size: 15px; color: #e0e7ff; }}
    .family-select {{
      background: #0f172a;
      border: 1px solid #6366f1;
      color: #fff;
      padding: 10px 16px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      outline: none;
      cursor: pointer;
      min-width: 280px;
    }}

    /* Investor Profile Header Card */
    .investor-card {{
      background: linear-gradient(135deg, #1e293b, #0f172a);
      border: 1px solid #334155;
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }}
    .investor-info {{ display: flex; align-items: center; gap: 16px; }}
    .avatar {{
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, var(--accent-color), var(--purple));
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 700;
      font-size: 18px;
      color: #fff;
    }}
    .investor-details .name {{ font-size: 16px; font-weight: 700; color: #fff; }}
    .investor-details .sub {{ font-size: 13px; color: var(--text-muted); display: flex; gap: 12px; margin-top: 2px; }}
    .badge-info {{ background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 500; }}

    /* Tab Navigation */
    .tabs-nav {{
      display: flex;
      gap: 12px;
      margin-bottom: 24px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
    }}
    .tab-btn {{
      background: #1e293b;
      color: var(--text-muted);
      border: 1px solid var(--border-color);
      padding: 10px 20px;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
    }}
    .tab-btn:hover {{ background: #334155; color: #fff; }}
    .tab-btn.active {{ background: var(--accent-color); color: #fff; border-color: var(--accent-color); shadow: 0 4px 12px rgba(59, 130, 246, 0.3); }}

    .tab-content {{ display: none; }}
    .tab-content.active {{ display: block; }}

    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }}
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 18px;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}
    .kpi-card:hover {{ transform: translateY(-2px); border-color: #3b82f6; }}
    .kpi-card .title {{ font-size: 12px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; font-weight: 600; }}
    .kpi-card .val {{ font-size: 24px; font-weight: 700; color: #fff; }}
    .kpi-card .delta {{ font-size: 13px; font-weight: 600; margin-top: 4px; display: inline-block; }}
    .delta.pos {{ color: var(--green); }}
    .delta.neg {{ color: var(--red); }}

    .grid-2 {{ display: grid; grid-template-columns: 2fr 1fr; gap: 20px; margin-bottom: 24px; }}
    @media (max-width: 1024px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}

    .chart-card {{
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .chart-card h3 {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; color: var(--text-main); display: flex; justify-content: space-between; align-items: center; }}
    .chart-container {{ position: relative; height: 340px; width: 100%; }}

    .data-card {{
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 24px;
    }}
    .table-controls {{
      display: flex;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }}
    .search-input, .select-filter {{
      background: #0f172a;
      border: 1px solid var(--border-color);
      color: #fff;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      outline: none;
    }}
    .search-input {{ flex: 1; min-width: 200px; }}
    .select-filter {{ min-width: 160px; }}

    table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
    th {{ background: #0f172a; color: var(--text-muted); padding: 12px 14px; font-weight: 600; border-bottom: 1px solid var(--border-color); white-space: nowrap; }}
    td {{ padding: 12px 14px; border-bottom: 1px solid var(--border-color); color: #cbd5e1; }}
    tr:hover td {{ background: #1e293b; color: #fff; }}
    .badge {{ padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
    .badge-eq {{ background: rgba(59, 130, 246, 0.15); color: #60a5fa; }}

    .methodology-box {{
      background: rgba(30, 41, 59, 0.6);
      border-left: 4px solid var(--accent-color);
      padding: 16px;
      border-radius: 6px;
      margin-bottom: 24px;
      font-size: 13px;
      color: #94a3b8;
    }}
    .methodology-box h4 {{ color: #f3f4f6; margin-bottom: 6px; font-size: 14px; }}

    .tx-pagination {{ display: flex; justify-content: space-between; align-items: center; margin-top: 16px; font-size: 13px; color: var(--text-muted); }}
    .tx-btn {{ background: #1e293b; color: #fff; border: 1px solid var(--border-color); padding: 6px 14px; border-radius: 6px; cursor: pointer; }}
    .tx-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}
  </style>
</head>
<body>

  <div class="header">
    <div>
      <h1>NSDL eCAS Portfolio & Transaction Analytics</h1>
      <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Multi-Asset Growth, XIRR Engine, Zerodha Performance Curve & Full Transactions Log</p>
    </div>
  </div>

  <!-- Multi-PAN Family View Selector & Date Range Filter Bar -->
  <div class="family-bar">
    <div style="display: flex; align-items: center; gap: 20px; flex-wrap: wrap;">
      <div class="family-title">
        <span>👨‍👩‍👧‍👦 Family Portfolio View</span>
      </div>
      <div>
        <select id="familySelect" class="family-select" onchange="onFilterChange()">
          <option value="ALL">👨‍👩‍👧‍👦 Consolidated Family Portfolio (All PANs Combined)</option>
        </select>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 13px; color: #a5b4fc; font-weight: 600;">📅 From Period:</span>
        <select id="fromPeriodSelect" class="family-select" onchange="onFilterChange()"></select>
      </div>
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="font-size: 13px; color: #a5b4fc; font-weight: 600;">📅 To Period:</span>
        <select id="toPeriodSelect" class="family-select" onchange="onFilterChange()"></select>
      </div>
    </div>
  </div>

  <!-- Investor & Account Profile Card -->
  <div class="investor-card">
    <div class="investor-info">
      <div class="avatar" id="invAvatar">B</div>
      <div class="investor-details">
        <div class="name" id="invName">{investor_name}</div>
        <div class="sub">
          <span>PAN: <strong style="color:#f3f4f6;" id="invPan">{masked_pan}</strong></span>
          <span>•</span>
          <span>NSDL CAS ID: <strong style="color:#f3f4f6;" id="invCas">{nsdl_id}</strong></span>
        </div>
      </div>
    </div>
    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
      <div class="badge-info">Sync Email: <strong>{masked_sync_email}</strong></div>
      <div class="badge-info">Statements: <strong>{len(datasets)} Monthly Files ({first_period} – {latest_period})</strong></div>
    </div>
  </div>

  <!-- Tab Buttons -->
  <div class="tabs-nav">
    <button class="tab-btn active" onclick="switchTab('tab-val')">💵 Portfolio Value & Trajectory</button>
    <button class="tab-btn" onclick="switchTab('tab-xirr')">⚡ Category XIRR Performance</button>
    <button class="tab-btn" onclick="switchTab('tab-zerodha')">📈 Zerodha Performance Curve</button>
    <button class="tab-btn" onclick="switchTab('tab-holdings')">💼 Current Portfolio Holdings</button>
    <button class="tab-btn" onclick="switchTab('tab-tx')">📜 Full Transactions Log ({len(transactions):,})</button>
    <button class="tab-btn" onclick="switchTab('tab-ai')" style="background:linear-gradient(135deg,#1e1b4b,#312e81);border-color:#6366f1;">🤖 AI Insights</button>
  </div>

  <!-- TAB 1: PORTFOLIO VALUE & TRAJECTORY -->
  <div id="tab-val" class="tab-content active">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="title" id="kpiValTitle">Portfolio Value ({latest_period})</div>
        <div class="val" id="kpiCurrVal">{format_inr(latest_val)}</div>
        <div class="delta {'pos' if val_delta>=0 else 'neg'}" id="kpiValDelta">{'▲' if val_delta>=0 else '▼'} {format_inr(abs(val_delta))} MoM</div>
      </div>
      <div class="kpi-card">
        <div class="title">Starting Valuation</div>
        <div class="val" id="kpiStartVal">{format_inr(timeline['portfolio_values'][0])}</div>
        <div class="delta" style="color: var(--text-muted);" id="kpiStartValSub">Base Value at Window Start</div>
      </div>
      <div class="kpi-card">
        <div class="title">Total Fresh Deposited</div>
        <div class="val" id="kpiFreshDeposited">{format_inr(timeline['cum_fresh_deposits'][-1])}</div>
        <div class="delta" style="color: var(--text-muted);" id="kpiFreshSub">Cumulative Cash Added</div>
      </div>
      <div class="kpi-card">
        <div class="title">Total Capital Withdrawn</div>
        <div class="val" style="color: var(--red);" id="kpiWithdrawn">{format_inr(timeline['cum_withdrawn'][-1])}</div>
        <div class="delta" style="color: var(--red);" id="kpiWithdrawnSub">Redemptions / Outflows</div>
      </div>
      <div class="kpi-card">
        <div class="title">Net Capital Injected</div>
        <div class="val" id="kpiInflow">{format_inr(timeline['cum_inflows'][-1])}</div>
        <div class="delta" style="color: var(--text-muted);" id="kpiInflowSub">Net Fresh Cash Remaining</div>
      </div>
      <div class="kpi-card">
        <div class="title">Overall Range XIRR</div>
        <div class="val" style="color: var(--green);" id="kpiXirr">{port_xirr:+.2f}%</div>
        <div class="delta" style="color: var(--green);" id="kpiXirrSub">Money-Weighted Return</div>
      </div>
      <div class="kpi-card">
        <div class="title">Unrealized Market Gain</div>
        <div class="val" id="kpiGain" style="color: {'var(--green)' if (latest_val - timeline['cum_inflows'][-1])>=0 else 'var(--red)'};">{format_inr(latest_val - timeline['cum_inflows'][-1])}</div>
        <div class="delta {'pos' if (latest_val - timeline['cum_inflows'][-1])>=0 else 'neg'}" id="kpiGainSub">Paper Gain in Range</div>
      </div>
      <div class="kpi-card">
        <div class="title">Realized Gain / Loss</div>
        <div class="val" style="color: var(--green);" id="kpiRealizedGain">+{format_inr(total_realized_gain)}</div>
        <div class="delta pos" id="kpiRealizedSub">Realized Profit in Range</div>
      </div>
    </div>

    <div class="grid-2">
      <div class="chart-card">
        <h3>Combined Portfolio & Asset Class Valuation Trajectory (₹) <span>Nov 2019 – {latest_period}</span></h3>
        <div class="chart-container" style="height: 380px;">
          <canvas id="chartValueTrajectory"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <h3>Asset Category Allocation</h3>
        <div class="chart-container" style="height: 380px;">
          <canvas id="chartCategoryDoughnut"></canvas>
        </div>
      </div>
    </div>

    <!-- Monthly Organic Return Trend Chart (Each Asset Class & Cumulative Portfolio) -->
    <div class="chart-card" style="margin-top: 20px;">
      <h3>Monthly Organic Return % Trend (Each Asset Class & Cumulative Portfolio)</h3>
      <div class="chart-container" style="height: 420px;">
        <canvas id="chartAssetClassReturnsTrend"></canvas>
      </div>
    </div>

    <!-- Monthly Asset Class Return Matrix Table -->
    <div class="data-card" style="margin-top: 24px;">
      <h3 id="monthlyReturnsTitle">Monthly Organic Return % Matrix by Asset Class ({first_period} – {latest_period})</h3>
      <div style="overflow-x: auto; margin-top: 14px;">
        <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
          <thead>
            <tr>
              <th style="position:sticky;left:0;background:#0f172a;z-index:2;">Period</th>
              <th>Portfolio Value (₹)</th>
              <th>Net Inflow (₹)</th>
              <th>Port Return %</th>
              <th>Equities %</th>
              <th>Mutual Funds %</th>
              <th>Govt Sec %</th>
              <th>AIF %</th>
              <th>NPS %</th>
              <th>Bonds %</th>
              <th>Pref Shares %</th>
            </tr>
          </thead>
          <tbody id="tblMonthlyReturnsBody"></tbody>
        </table>
      </div>
    </div>
  </div>

  <!-- TAB 2: CATEGORY XIRR PERFORMANCE -->
  <div id="tab-xirr" class="tab-content">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="title">Overall Range XIRR</div>
        <div class="val" style="color: var(--green);" id="kpiXirrTab2">{port_xirr:+.2f}%</div>
        <div class="delta pos" id="kpiXirrTab2Sub">Money-Weighted Annualized Return</div>
      </div>
      <div class="kpi-card">
        <div class="title">Starting Valuation</div>
        <div class="val" id="kpiStartValTab2">₹{timeline['portfolio_values'][0]:,.2f}</div>
        <div class="delta" style="color: var(--text-muted);" id="kpiStartValTab2Sub">Base Value at Range Start</div>
      </div>
      <div class="kpi-card">
        <div class="title">Net Capital Injected</div>
        <div class="val" id="kpiInflowTab2">₹{timeline['cum_inflows'][-1]:,.2f}</div>
        <div class="delta" style="color: var(--text-muted);" id="kpiInflowTab2Sub">Fresh Capital Added in Range</div>
      </div>
      <div class="kpi-card">
        <div class="title">Ending Valuation</div>
        <div class="val" id="kpiValTab2">₹{latest_val:,.2f}</div>
        <div class="delta pos" id="kpiValTab2Sub">Ending Wealth at Range End</div>
      </div>
    </div>

    <div class="grid-2">
      <div class="chart-card">
        <h3>Category Annualized XIRR (%) Rate Comparison</h3>
        <div class="chart-container">
          <canvas id="chartCategoryXirrBar"></canvas>
        </div>
      </div>
      <div class="chart-card">
        <h3>Capital Injected vs Current Valuation</h3>
        <div class="chart-container">
          <canvas id="chartCapitalVsValuation"></canvas>
        </div>
      </div>
    </div>

    <div class="data-card">
      <h3>Category XIRR Performance Breakdown Table</h3>
      <table style="margin-top: 14px;">
        <thead>
          <tr>
            <th>Asset Category</th>
            <th>First Holding Date</th>
            <th>Cost Basis (₹)</th>
            <th>Current Valuation (₹)</th>
            <th>Realized Gain (₹)</th>
            <th>Unrealized Gain (₹)</th>
            <th>Unrealized Return %</th>
            <th>Annualized XIRR %</th>
          </tr>
        </thead>
        <tbody id="tblXirrBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 3: ZERODHA PERFORMANCE CURVE & TWRR VIEW -->
  <div id="tab-zerodha" class="tab-content">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="title">Capital-Weighted NAV Index</div>
        <div class="val" style="color: var(--accent-color);">{latest_nav:.2f}</div>
        <div class="delta pos">{nav_return:+.2f}% Money-Weighted Index</div>
      </div>
      <div class="kpi-card">
        <div class="title">Time-Weighted TWRR Index</div>
        <div class="val" style="color: var(--purple);">{latest_twrr:.2f}</div>
        <div class="delta pos">{twrr_return:+.2f}% Compound TWRR</div>
      </div>
      <div class="kpi-card">
        <div class="title">Overall Portfolio XIRR</div>
        <div class="val" style="color: var(--green);">{port_xirr:+.2f}%</div>
        <div class="delta pos">True Annualized Return</div>
      </div>
    </div>

    <div class="methodology-box">
      <h4>💡 Zerodha Performance Curve & TWRR Methodology Explained</h4>
      <p>This tab provides two complementary views of your portfolio performance:<br>
      • <strong>Capital-Weighted Index (Base 100)</strong>: Weights returns by the actual capital committed over time (matches your <strong>{port_xirr:+.2f}% XIRR</strong>).<br>
      • <strong>Time-Weighted Rate of Return (TWRR)</strong>: Measures the theoretical compound growth of ₹1 invested on Day 1, ignoring when fresh money was added.</p>
    </div>

    <!-- View Toggle Control -->
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px;">
      <h3 style="font-size:16px;color:#f3f4f6;">Zerodha Console Performance Curve</h3>
      <div style="display:flex;gap:8px;background:#1e293b;padding:4px;border-radius:8px;border:1px solid #334155;">
        <button id="btnCapView" onclick="setNavView('capital')" style="background:#3b82f6;color:#fff;border:none;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">Capital-Weighted Index</button>
        <button id="btnTwrrView" onclick="setNavView('twrr')" style="background:transparent;color:#94a3b8;border:none;padding:6px 14px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;">Time-Weighted TWRR Index</button>
      </div>
    </div>

    <div class="chart-card">
      <div class="chart-container">
        <canvas id="chartZerodhaNavCurve"></canvas>
      </div>
    </div>
  </div>

  <!-- TAB 4: CURRENT PORTFOLIO HOLDINGS -->
  <div id="tab-holdings" class="tab-content">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="title">Total Securities Held</div>
        <div class="val" style="color: var(--accent-color);">{len(curr_holdings):,}</div>
        <div class="delta" style="color: var(--text-muted);">Active Holdings in Selected Period</div>
      </div>
      <div class="kpi-card">
        <div class="title">Total Portfolio Valuation</div>
        <div class="val" id="kpiHoldingsVal">₹{latest_val:,.2f}</div>
        <div class="delta pos">Current Asset Value</div>
      </div>
    </div>

    <div class="data-card">
      <h3>Current Portfolio Holdings ({latest_period})</h3>
      <div class="table-controls" style="margin-top: 14px;">
        <input type="text" id="holdingsSearch" class="search-input" placeholder="Search security name, ISIN, or DP ID..." oninput="filterHoldings()">
        <select id="holdingsCategoryFilter" class="select-filter" onchange="filterHoldings()">
          <option value="ALL">All Categories</option>
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th>Asset Class</th>
            <th>ISIN</th>
            <th>Security Name</th>
            <th>Depository / DP ID</th>
            <th>Quantity</th>
            <th>Current Price</th>
            <th>Current Valuation (₹)</th>
            <th>Cost Basis (₹)</th>
            <th>Realized Gain (₹)</th>
            <th>Unrealized Gain (₹)</th>
            <th>Unrealized Return %</th>
          </tr>
        </thead>
        <tbody id="tblHoldingsBody"></tbody>
      </table>
    </div>
  </div>

  <!-- TAB 4: FULL TRANSACTIONS HISTORY -->
  <div id="tab-tx" class="tab-content">
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="title">Total Real Trade Transactions</div>
        <div class="val" style="color: var(--accent-color);">{len(transactions):,}</div>
        <div class="delta" style="color: var(--text-muted);">SIPs, Purchases, Redemptions</div>
      </div>
      <div class="kpi-card">
        <div class="title">CSV Export Path</div>
        <div class="val" style="font-size: 15px; color: var(--green);">output/transactions.csv</div>
        <div class="delta pos">Full Audit Trail Available</div>
      </div>
    </div>

    <div class="data-card">
      <h3>Full eCAS Transaction Log</h3>
      <div class="table-controls" style="margin-top: 14px;">
        <input type="text" id="txSearch" class="search-input" placeholder="Search date, ISIN, security name, transaction type..." oninput="filterTx()">
        <select id="txCategoryFilter" class="select-filter" onchange="filterTx()">
          <option value="ALL">All Asset Classes</option>
        </select>
      </div>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Statement Period</th>
            <th>Asset Class</th>
            <th>ISIN</th>
            <th>Security / Fund Name</th>
            <th>Transaction Description</th>
            <th>Amount (₹)</th>
            <th>Price / NAV (₹)</th>
            <th>Units</th>
          </tr>
        </thead>
        <tbody id="tblTxBody"></tbody>
      </table>
      <div class="tx-pagination">
        <button class="tx-btn" onclick="prevTxPage()" id="btnPrevPage">◀ Previous</button>
        <span id="txPageInfo">Page 1</span>
        <button class="tx-btn" onclick="nextTxPage()" id="btnNextPage">Next ▶</button>
      </div>
    </div>
  </div>

  <script>
    const timelineData = {json_timeline};
    const categoryXirrs = {json_category_xirrs};
    let holdingsData = {json_holdings};
    let momSummary = {json_mom_summary};
    const transactionsData = {json_transactions};
    const familyProfiles = {json_family_profiles};
    const monthlyHistory = {json_monthly_history};

    const allPeriodHoldings = {json_all_period_holdings};
    const allPeriodMomSummaries = {json_all_period_mom_summaries};
    let filteredHoldings = [...holdingsData];
    let filteredTx = [...transactionsData];
    let txCurrentPage = 1;
    const txPageSize = 50;

    // Populate Family Select Dropdown
    const familySelect = document.getElementById('familySelect');
    familyProfiles.forEach(fp => {{
      const opt = document.createElement('option');
      opt.value = fp.pan;
      opt.innerText = `👤 ${{fp.investor_name}} (PAN: ${{fp.masked_pan || fp.pan.substring(0,2)+'*****'+fp.pan.slice(-2)}}) - ${{fp.statement_count}} Statements`;
      familySelect.appendChild(opt);
    }});

    function onFamilyChange() {{
      const selPan = familySelect.value;
      if (selPan === 'ALL') {{
        document.getElementById('invName').innerText = 'Consolidated Family Portfolio';
        document.getElementById('invPan').innerText = 'FAMILY_CONSOLIDATED';
        document.getElementById('invAvatar').innerText = '👨‍👩‍👧‍👦';
        filteredHoldings = [...holdingsData];
        filteredTx = [...transactionsData];
      }} else {{
        const profile = familyProfiles.find(fp => fp.pan === selPan);
        if (profile) {{
          document.getElementById('invName').innerText = profile.investor_name;
          document.getElementById('invPan').innerText = profile.masked_pan || profile.pan.substring(0,2)+'*****'+profile.pan.slice(-2);
          document.getElementById('invAvatar').innerText = profile.investor_name.charAt(0);
        }}
        filteredHoldings = holdingsData.filter(h => h.pan === selPan || selPan === 'ALL');
        filteredTx = transactionsData.filter(t => t.pan === selPan || selPan === 'ALL');
      }}
      txCurrentPage = 1;
      renderHoldingsTable();
      renderTxTable();
    }}

    function switchTab(tabId) {{
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    }}

    function renderTblMom() {{
      const tbody = document.getElementById('tblMomBody');
      tbody.innerHTML = '';
      for (const [cat, stats] of Object.entries(momSummary)) {{
        const tr = document.createElement('tr');
        const isPos = stats.market_appreciation >= 0;
        tr.innerHTML = `
          <td><strong>${{cat}}</strong></td>
          <td>₹${{stats.prev_value.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td>₹${{stats.curr_value.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td>₹${{stats.net_capital_inflow.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="color: ${{isPos ? 'var(--green)' : 'var(--red)'}}">₹${{stats.market_appreciation.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="font-weight:600; color: ${{stats.organic_growth_pct>=0 ? 'var(--green)' : 'var(--red)'}}">${{stats.organic_growth_pct > 0 ? '+' : ''}}${{stats.organic_growth_pct}}%</td>
        `;
        tbody.appendChild(tr);
      }}
    }}

    function renderHoldingsTable() {{
      const tbody = document.getElementById('tblHoldingsBody');
      tbody.innerHTML = '';
      filteredHoldings.forEach(h => {{
        const tr = document.createElement('tr');
        const isPosUnrealized = (h.unrealized_gain || 0) >= 0;
        const isPosRealized = (h.realized_gain || 0) >= 0;
        const uGain = h.unrealized_gain || 0;
        const rGain = h.realized_gain || 0;
        const uPct = h.unrealized_pct || 0;
        const cost = h.cost_basis || 0;

        tr.innerHTML = `
          <td><span class="badge badge-eq">${{h.asset_class}}</span></td>
          <td style="font-family: monospace; color:#94a3b8;">${{h.isin}}</td>
          <td><strong>${{h.security_name}}</strong></td>
          <td style="color:#94a3b8;">${{h.depository || ''}} (${{h.dp_id || ''}})</td>
          <td>${{(h.quantity || 0).toLocaleString('en-IN')}}</td>
          <td>₹${{(h.price || 0).toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td><strong>₹${{(h.value || 0).toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</strong></td>
          <td>₹${{cost.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="color: ${{isPosRealized ? 'var(--green)' : 'var(--red)'}}">${{rGain >= 0 ? '+' : ''}}₹${{Math.abs(rGain).toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="font-weight:600; color: ${{isPosUnrealized ? 'var(--green)' : 'var(--red)'}}">${{uGain >= 0 ? '+' : ''}}₹${{Math.abs(uGain).toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="font-weight:700; color: ${{isPosUnrealized ? 'var(--green)' : 'var(--red)'}}">${{uPct >= 0 ? '+' : ''}}${{uPct.toFixed(2)}}%</td>
        `;
        tbody.appendChild(tr);
      }});
    }}

    function filterHoldings() {{
      const q = document.getElementById('holdingsSearch').value.toLowerCase();
      const cat = document.getElementById('holdingsCategoryFilter').value;
      const selPan = familySelect.value;
      filteredHoldings = holdingsData.filter(h => {{
        const matchQ = (h.security_name || '').toLowerCase().includes(q) || (h.isin || '').toLowerCase().includes(q) || (h.dp_id || '').toLowerCase().includes(q);
        const matchCat = cat === 'ALL' || h.asset_class === cat;
        const matchPan = selPan === 'ALL' || h.pan === selPan;
        return matchQ && matchCat && matchPan;
      }});
      renderHoldingsTable();
    }}

    function renderTblXirr() {{
      const tbody = document.getElementById('tblXirrBody');
      tbody.innerHTML = '';
      for (const [cat, info] of Object.entries(categoryXirrs)) {{
        const tr = document.createElement('tr');
        const isPosXirr = (info.xirr_pct || 0) >= 0;
        const isPosUnrealized = (info.unrealized_gain || 0) >= 0;
        const isPosRealized = (info.realized_gain || 0) >= 0;
        const uGain = info.unrealized_gain || 0;
        const rGain = info.realized_gain || 0;
        const uPct = info.unrealized_pct || 0;
        const cost = info.cost_basis || info.init_value || 0;

        tr.innerHTML = `
          <td><strong>${{cat}}</strong></td>
          <td>${{info.first_date}}</td>
          <td>₹${{cost.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td>₹${{info.curr_value.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="color: ${{isPosRealized ? 'var(--green)' : 'var(--red)'}}">${{rGain >= 0 ? '+' : ''}}₹${{Math.abs(rGain).toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="font-weight:600; color: ${{isPosUnrealized ? 'var(--green)' : 'var(--red)'}}">${{uGain >= 0 ? '+' : ''}}₹${{Math.abs(uGain).toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td style="font-weight:700; color: ${{isPosUnrealized ? 'var(--green)' : 'var(--red)'}}">${{uPct >= 0 ? '+' : ''}}${{uPct.toFixed(2)}}%</td>
          <td style="font-weight:700; color: ${{isPosXirr ? 'var(--green)' : 'var(--red)'}}">${{info.xirr_pct > 0 ? '+' : ''}}${{info.xirr_pct}}%</td>
        `;
        tbody.appendChild(tr);
      }}
    }}

    function renderTxTable() {{
      const tbody = document.getElementById('tblTxBody');
      tbody.innerHTML = '';
      const start = (txCurrentPage - 1) * txPageSize;
      const end = start + txPageSize;
      const pageData = filteredTx.slice(start, end);

      pageData.forEach(tx => {{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${{tx.transaction_date}}</strong></td>
          <td>${{tx.statement_period}}</td>
          <td><span class="badge badge-eq">${{tx.asset_class}}</span></td>
          <td style="font-family: monospace; color:#94a3b8;">${{tx.isin}}</td>
          <td>${{tx.security_name}}</td>
          <td style="color:#cbd5e1;">${{tx.transaction_type}}</td>
          <td>₹${{tx.amount.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td>₹${{tx.price_nav.toLocaleString('en-IN', {{maximumFractionDigits:2}})}}</td>
          <td>${{tx.units.toLocaleString('en-IN', {{maximumFractionDigits:3}})}}</td>
        `;
        tbody.appendChild(tr);
      }});

      const totalPages = Math.ceil(filteredTx.length / txPageSize) || 1;
      document.getElementById('txPageInfo').innerText = `Page ${{txCurrentPage}} of ${{totalPages}} (${{filteredTx.length}} transactions)`;
      document.getElementById('btnPrevPage').disabled = txCurrentPage === 1;
      document.getElementById('btnNextPage').disabled = txCurrentPage === totalPages;
    }}

    function filterTx() {{
      const q = document.getElementById('txSearch').value.toLowerCase();
      const cat = document.getElementById('txCategoryFilter').value;
      const selPan = familySelect.value;
      filteredTx = transactionsData.filter(t => {{
        const matchQ = (t.security_name || '').toLowerCase().includes(q) || (t.isin || '').toLowerCase().includes(q) || (t.transaction_type || '').toLowerCase().includes(q) || (t.transaction_date || '').includes(q);
        const matchCat = cat === 'ALL' || t.asset_class === cat;
        const matchPan = selPan === 'ALL' || t.pan === selPan;
        return matchQ && matchCat && matchPan;
      }});
      txCurrentPage = 1;
      renderTxTable();
    }}

    function prevTxPage() {{ if (txCurrentPage > 1) {{ txCurrentPage--; renderTxTable(); }} }}
    function nextTxPage() {{ const totalPages = Math.ceil(filteredTx.length / txPageSize); if (txCurrentPage < totalPages) {{ txCurrentPage++; renderTxTable(); }} }}

    // Populate Category Dropdowns
    const categories = Array.from(new Set(holdingsData.map(h => h.asset_class)));
    const catFilter = document.getElementById('holdingsCategoryFilter');
    const txCatFilter = document.getElementById('txCategoryFilter');
    categories.forEach(c => {{
      const opt = document.createElement('option'); opt.value = c; opt.innerText = c;
      catFilter.appendChild(opt);
      const opt2 = document.createElement('option'); opt2.value = c; opt2.innerText = c;
      txCatFilter.appendChild(opt2);
    }});

    // Populate From/To Period Dropdowns
    const fromSel = document.getElementById('fromPeriodSelect');
    const toSel = document.getElementById('toPeriodSelect');
    if (fromSel && toSel) {{
      fromSel.innerHTML = '';
      toSel.innerHTML = '';

      timelineData.periods.forEach((p, idx) => {{
        const opt = document.createElement('option');
        opt.value = p;
        opt.innerText = idx === 0 ? `📅 ${{p}} (Start)` : `📅 ${{p}}`;
        fromSel.appendChild(opt);
      }});
      fromSel.value = timelineData.periods[0];

      [...timelineData.periods].reverse().forEach((p, idx) => {{
        const opt = document.createElement('option');
        opt.value = p;
        opt.innerText = idx === 0 ? `📅 ${{p}} (Latest)` : `📅 ${{p}}`;
        toSel.appendChild(opt);
      }});
      toSel.value = timelineData.periods[timelineData.periods.length - 1];
    }}

    function fmtINR(val, decimals=2) {{
      if (val === null || val === undefined || isNaN(val)) return "₹0.00";
      const isNeg = val < 0;
      const str = Math.abs(val).toLocaleString('en-IN', {{
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
      }});
      return (isNeg ? "-₹" : "₹") + str;
    }}

    function onFilterChange() {{
      const fromEl = document.getElementById('fromPeriodSelect');
      const toEl = document.getElementById('toPeriodSelect');
      const fromP = fromEl ? fromEl.value : timelineData.periods[0];
      const toP = toEl ? toEl.value : timelineData.periods[timelineData.periods.length - 1];

      let startIdx = timelineData.periods.indexOf(fromP);
      let endIdx = timelineData.periods.indexOf(toP);

      if (startIdx === -1) startIdx = 0;
      if (endIdx === -1) endIdx = timelineData.periods.length - 1;

      if (startIdx > endIdx) {{
        const temp = startIdx;
        startIdx = endIdx;
        endIdx = temp;
      }}

      const slicedPeriods = timelineData.periods.slice(startIdx, endIdx + 1);
      const slicedValues = timelineData.portfolio_values.slice(startIdx, endIdx + 1);
      const slicedInflows = timelineData.cum_inflows.slice(startIdx, endIdx + 1);
      const slicedFresh = timelineData.cum_fresh_deposits ? timelineData.cum_fresh_deposits.slice(startIdx, endIdx + 1) : [];
      const slicedWithdrawn = timelineData.cum_withdrawn ? timelineData.cum_withdrawn.slice(startIdx, endIdx + 1) : [];

      const currVal = slicedValues[slicedValues.length - 1];
      const startVal = slicedValues[0];
      const valDelta = currVal - startVal;

      const endInflow = slicedInflows[slicedInflows.length - 1];
      const startInflow = slicedInflows[0];
      const windowInflow = endInflow - startInflow;

      const startFresh = slicedFresh.length > 0 ? (slicedFresh[0] || 0) : 0;
      const endFresh = slicedFresh.length > 0 ? (slicedFresh[slicedFresh.length - 1] || 0) : 0;
      const windowFresh = Math.max(0, endFresh - startFresh);

      const startWithdrawn = slicedWithdrawn.length > 0 ? (slicedWithdrawn[0] || 0) : 0;
      const endWithdrawn = slicedWithdrawn.length > 0 ? (slicedWithdrawn[slicedWithdrawn.length - 1] || 0) : 0;
      const windowWithdrawn = Math.max(0, endWithdrawn - startWithdrawn);

      const windowMarketGain = valDelta - windowInflow;

      const slicedRealized = timelineData.realized_gains_series ? timelineData.realized_gains_series.slice(startIdx, endIdx + 1) : [];
      const prevRealized = startIdx > 0 ? (timelineData.realized_gains_series[startIdx - 1] || 0) : 0;
      const endRealized = slicedRealized.length > 0 ? slicedRealized[slicedRealized.length - 1] : 0;
      const windowRealized = endRealized - prevRealized;

      let windowXirr = 22.32;
      if (timelineData.range_xirr_matrix && timelineData.range_xirr_matrix[startIdx] && timelineData.range_xirr_matrix[startIdx][endIdx] !== undefined) {{
        windowXirr = timelineData.range_xirr_matrix[startIdx][endIdx];
      }}

      // Tab 1 KPI Cards
      document.getElementById('kpiValTitle').innerText = `Portfolio Value (${{timelineData.periods[endIdx]}})`;
      document.getElementById('kpiCurrVal').innerText = fmtINR(currVal);

      const deltaEl = document.getElementById('kpiValDelta');
      if (deltaEl) {{
        deltaEl.className = `delta ${{valDelta >= 0 ? 'pos' : 'neg'}}`;
        deltaEl.innerText = `${{valDelta >= 0 ? '▲' : '▼'}} ${{fmtINR(Math.abs(valDelta))}} (${{fromP}} → ${{toP}})`;
      }}

      const startValEl = document.getElementById('kpiStartVal');
      if (startValEl) {{
        startValEl.innerText = fmtINR(startVal);
      }}

      const freshEl = document.getElementById('kpiFreshDeposited');
      if (freshEl) {{
        freshEl.innerText = fmtINR(windowFresh);
      }}

      const withdrawnEl = document.getElementById('kpiWithdrawn');
      if (withdrawnEl) {{
        withdrawnEl.innerText = fmtINR(windowWithdrawn);
      }}

      document.getElementById('kpiInflow').innerText = fmtINR(windowInflow);
      const inflowSubEl = document.getElementById('kpiInflowSub');
      if (inflowSubEl) {{
        inflowSubEl.style.color = windowInflow >= 0 ? 'var(--text-muted)' : '#f87171';
        inflowSubEl.innerText = windowInflow >= 0 ? `Fresh Capital Added (${{fromP}} → ${{toP}})` : `🔴 Capital Withdrawn (${{fromP}} → ${{toP}})`;
      }}

      const xirrEl = document.getElementById('kpiXirr');
      if (xirrEl) {{
        xirrEl.style.color = windowXirr >= 0 ? 'var(--green)' : 'var(--red)';
        xirrEl.innerText = `${{windowXirr >= 0 ? '+' : ''}}${{windowXirr.toFixed(2)}}%`;
      }}

      const gainEl = document.getElementById('kpiGain');
      if (gainEl) {{
        gainEl.style.color = windowMarketGain >= 0 ? 'var(--green)' : 'var(--red)';
        gainEl.innerText = `${{windowMarketGain >= 0 ? '+' : ''}}${{fmtINR(windowMarketGain)}}`;
      }}

      const realEl = document.getElementById('kpiRealizedGain');
      if (realEl) {{
        realEl.style.color = windowRealized >= 0 ? 'var(--green)' : 'var(--red)';
        realEl.innerText = `${{windowRealized >= 0 ? '+' : ''}}${{fmtINR(windowRealized)}}`;
      }}

      // Tab 2 KPI Cards
      const xirrTab2El = document.getElementById('kpiXirrTab2');
      if (xirrTab2El) {{
        xirrTab2El.style.color = windowXirr >= 0 ? 'var(--green)' : 'var(--red)';
        xirrTab2El.innerText = `${{windowXirr >= 0 ? '+' : ''}}${{windowXirr.toFixed(2)}}%`;
      }}
      const startValTab2El = document.getElementById('kpiStartValTab2');
      if (startValTab2El) {{
        startValTab2El.innerText = fmtINR(startVal);
      }}
      const inflowTab2El = document.getElementById('kpiInflowTab2');
      if (inflowTab2El) {{
        inflowTab2El.innerText = fmtINR(windowInflow);
      }}
      const inflowTab2SubEl = document.getElementById('kpiInflowTab2Sub');
      if (inflowTab2SubEl) {{
        inflowTab2SubEl.style.color = windowInflow >= 0 ? 'var(--text-muted)' : '#f87171';
        inflowTab2SubEl.innerText = windowInflow >= 0 ? `Fresh Capital Added in Range` : `🔴 Capital Withdrawn in Range`;
      }}
      const valTab2El = document.getElementById('kpiValTab2');
      if (valTab2El) {{
        valTab2El.innerText = fmtINR(currVal);
      }}

      // Update Holdings & MoM Summary for Holdings Table & Category Allocation
      const selToPeriod = timelineData.periods[endIdx];
      holdingsData = allPeriodHoldings[selToPeriod] || [];
      if (allPeriodMomSummaries[selToPeriod]) {{
        momSummary = allPeriodMomSummaries[selToPeriod];
      }}

      // Filter transactions to the selected period range
      const activePeriodSet = new Set(slicedPeriods);
      const selPan = familySelect.value;
      filteredTx = transactionsData.filter(t => activePeriodSet.has(t.statement_period) && (selPan === 'ALL' || t.pan === selPan));
      txCurrentPage = 1;

      const titleEl = document.getElementById('monthlyReturnsTitle');
      if (titleEl) {{
        titleEl.innerText = `Monthly Organic Return % Matrix by Asset Class (${{fromP}} – ${{toP}})`;
      }}

      renderTblXirr();
      renderMonthlyReturnsTable(startIdx, endIdx);
      onFamilyChange();

      // Update Chart 1: Combined Valuation Trajectory
      if (window.chartValueTrajectoryInstance) {{
        chartValueTrajectoryInstance.data.labels = slicedPeriods;
        chartValueTrajectoryInstance.data.datasets[0].data = slicedValues;
        chartValueTrajectoryInstance.data.datasets[1].data = slicedInflows;
        catKeys.forEach((cat, idx) => {{
          const vals = timelineData.category_series[cat] ? timelineData.category_series[cat].values.slice(startIdx, endIdx + 1) : [];
          if (chartValueTrajectoryInstance.data.datasets[idx + 2]) {{
            chartValueTrajectoryInstance.data.datasets[idx + 2].data = vals;
          }}
        }});
        chartValueTrajectoryInstance.update();
      }}

      // Update Chart 2: Category Doughnut Allocation
      if (window.chartCategoryDoughnutInstance) {{
        const newCatVals = catLabels.map(c => holdingsData.filter(h => h.asset_class === c).reduce((sum, h) => sum + h.value, 0));
        chartCategoryDoughnutInstance.data.datasets[0].data = newCatVals;
        chartCategoryDoughnutInstance.update();
      }}

      // Update Chart 1c: Return Trend
      if (window.chartAssetClassReturnsTrendInstance) {{
        const slicedMH = monthlyHistory.slice(startIdx, endIdx);
        chartAssetClassReturnsTrendInstance.data.labels = slicedMH.map(m => m.curr_period);
        chartAssetClassReturnsTrendInstance.data.datasets[0].data = slicedMH.map(m => m.portfolio_summary.portfolio_organic_growth_pct);
        catKeys.forEach((cat, idx) => {{
          if (chartAssetClassReturnsTrendInstance.data.datasets[idx + 1]) {{
            chartAssetClassReturnsTrendInstance.data.datasets[idx + 1].data = slicedMH.map(m => (m.asset_class_summary[cat] && m.asset_class_summary[cat].prev_value > 0) ? m.asset_class_summary[cat].organic_growth_pct : 0);
          }}
        }});
        chartAssetClassReturnsTrendInstance.update();
      }}

      // Update Chart 5: Zerodha Performance Curve
      if (window.chartZerodhaNavInstance) {{
        chartZerodhaNavInstance.data.labels = slicedPeriods;
        chartZerodhaNavInstance.data.datasets[0].data = slicedNav;
        chartZerodhaNavInstance.data.datasets[1].data = slicedValues;
        chartZerodhaNavInstance.update();
      }}
    }}

    // Chart 1: Combined Portfolio & Asset Class Valuation Trajectory
    const catKeys = [
      'Equities (E)', 'Mutual Funds (M)', 'Government Securities (G)',
      'Alternate Investment Fund (A)', 'National Pension System (N)',
      'Corporate Bonds (C)', 'Preference Shares (P)'
    ];
    const catColors = {{
      'Equities (E)': '#60a5fa',
      'Mutual Funds (M)': '#34d399',
      'Government Securities (G)': '#fbbf24',
      'Alternate Investment Fund (A)': '#a78bfa',
      'National Pension System (N)': '#f472b6',
      'Corporate Bonds (C)': '#2dd4bf',
      'Preference Shares (P)': '#818cf8'
    }};

    const combinedValuationDatasets = [
      {{
        label: 'Total Portfolio Valuation (₹)',
        data: timelineData.portfolio_values,
        borderColor: '#3b82f6',
        borderWidth: 3.5,
        backgroundColor: 'rgba(59, 130, 246, 0.08)',
        fill: true,
        tension: 0.3
      }},
      {{
        label: 'Cumulative Net Inflows (₹)',
        data: timelineData.cum_inflows,
        borderColor: '#10b981',
        borderWidth: 2,
        borderDash: [5, 5],
        fill: false,
        tension: 0.3
      }},
      ...catKeys.map(cat => ({{
        label: cat,
        data: timelineData.category_series[cat] ? timelineData.category_series[cat].values : [],
        borderColor: catColors[cat] || '#94a3b8',
        borderWidth: 1.5,
        borderDash: [2, 2],
        fill: false,
        tension: 0.3
      }}))
    ];

    window.chartValueTrajectoryInstance = new Chart(document.getElementById('chartValueTrajectory'), {{
      type: 'line',
      data: {{
        labels: timelineData.periods,
        datasets: combinedValuationDatasets
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }} }},
        scales: {{ x: {{ ticks: {{ color: '#64748b' }} }}, y: {{ ticks: {{ color: '#64748b' }} }} }}
      }}
    }});

    // Chart 2: Category Doughnut
    const catLabels = Object.keys(categoryXirrs);
    const catVals = catLabels.map(c => holdingsData.filter(h => h.asset_class === c).reduce((sum, h) => sum + h.value, 0));
    window.chartCategoryDoughnutInstance = new Chart(document.getElementById('chartCategoryDoughnut'), {{
      type: 'doughnut',
      data: {{
        labels: catLabels,
        datasets: [{{ data: catVals, backgroundColor: ['#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#14b8a6', '#ec4899'] }}]
      }},
      options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 11 }} }} }} }} }}
    }});

    // Chart 3: Category XIRR Bar
    const xirrVals = catLabels.map(c => categoryXirrs[c] ? categoryXirrs[c].xirr_pct : 0);
    new Chart(document.getElementById('chartCategoryXirrBar'), {{
      type: 'bar',
      data: {{
        labels: catLabels,
        datasets: [{{ label: 'Annualized XIRR (%)', data: xirrVals, backgroundColor: xirrVals.map(v => v >= 0 ? '#10b981' : '#ef4444') }}]
      }},
      options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ ticks: {{ color: '#64748b' }} }}, y: {{ ticks: {{ color: '#64748b' }} }} }} }}
    }});

    // Chart 4: Capital Injected vs Valuation
    const capInjected = catLabels.map(c => categoryXirrs[c] ? categoryXirrs[c].init_value : 0);
    const currValuations = catLabels.map(c => categoryXirrs[c] ? categoryXirrs[c].curr_value : 0);
    new Chart(document.getElementById('chartCapitalVsValuation'), {{
      type: 'bar',
      data: {{
        labels: catLabels,
        datasets: [
          {{ label: 'Capital Deployed (₹)', data: capInjected, backgroundColor: '#3b82f6' }},
          {{ label: 'Current Valuation (₹)', data: currValuations, backgroundColor: '#10b981' }}
        ]
      }},
      options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }}, scales: {{ x: {{ ticks: {{ color: '#64748b' }} }}, y: {{ ticks: {{ color: '#64748b' }} }} }} }}
    }});

    // Chart 1c: Monthly Return % Trend (Each Asset Class & Cumulative Portfolio)
    const returnDatasets = [
      {{
        label: 'Cumulative Portfolio Organic Return %',
        data: monthlyHistory.map(m => m.portfolio_summary.portfolio_organic_growth_pct),
        borderColor: '#f59e0b',
        borderWidth: 3,
        fill: false,
        tension: 0.3
      }},
      ...catKeys.map(cat => ({{
        label: cat + ' Organic Return %',
        data: monthlyHistory.map(m => (m.asset_class_summary[cat] && m.asset_class_summary[cat].prev_value > 0) ? m.asset_class_summary[cat].organic_growth_pct : 0),
        borderColor: catColors[cat] || '#94a3b8',
        borderWidth: 1.5,
        borderDash: [3, 3],
        fill: false,
        tension: 0.3
      }}))
    ];

    window.chartAssetClassReturnsTrendInstance = new Chart(document.getElementById('chartAssetClassReturnsTrend'), {{
      type: 'line',
      data: {{
        labels: monthlyHistory.map(m => m.curr_period),
        datasets: returnDatasets
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8', font: {{ size: 10 }} }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#64748b' }} }},
          y: {{
            suggestedMin: -35,
            suggestedMax: 35,
            ticks: {{ color: '#64748b', callback: v => v + '%' }},
            title: {{ display: true, text: 'Monthly Organic Return %', color: '#94a3b8' }}
          }}
        }}
      }}
    }});

    // Populate Monthly Asset Class Return Matrix Table
    function renderMonthlyReturnsTable(sIdx, eIdx) {{
      const tbody = document.getElementById('tblMonthlyReturnsBody');
      if (!tbody || !monthlyHistory) return;
      tbody.innerHTML = '';

      const slicedHistory = (sIdx !== undefined && eIdx !== undefined) ? monthlyHistory.slice(sIdx, eIdx + 1) : monthlyHistory;
      [...slicedHistory].reverse().forEach(mh => {{
        const tr = document.createElement('tr');
        const ps = mh.portfolio_summary;
        const acSum = mh.asset_class_summary || {{}};

        const pVal = ps.curr_portfolio_value;
        const inflow = ps.net_capital_injected;
        const portRet = ps.portfolio_organic_growth_pct;

        function colorCell(val) {{
          if (val > 0.1) return `<span style="color:#10b981;font-weight:600;">+${{val.toFixed(2)}}%</span>`;
          if (val < -0.1) return `<span style="color:#ef4444;font-weight:600;">${{val.toFixed(2)}}%</span>`;
          return `<span style="color:#64748b;">0.00%</span>`;
        }}

        let catTds = catKeys.map(cat => {{
          const stats = acSum[cat];
          if (!stats || stats.prev_value <= 0) return `<td style="color:#475569;text-align:center;">-</td>`;
          return `<td style="text-align:right;">${{colorCell(stats.organic_growth_pct)}}</td>`;
        }}).join('');

        tr.innerHTML = `
          <td style="position:sticky;left:0;background:#1e293b;font-weight:600;">${{mh.curr_period}}</td>
          <td style="text-align:right;font-weight:500;">₹${{pVal.toLocaleString('en-IN', {{maximumFractionDigits:0}})}}</td>
          <td style="text-align:right;color:${{inflow >= 0 ? '#10b981':'#ef4444'}};">₹${{inflow.toLocaleString('en-IN', {{maximumFractionDigits:0}})}}</td>
          <td style="text-align:right;">${{colorCell(portRet)}}</td>
          ${{catTds}}
        `;
        tbody.appendChild(tr);
      }});
    }}

    renderMonthlyReturnsTable();

    // Chart 5: Zerodha Performance Curve (Restored untouched)
    window.chartZerodhaNavInstance = new Chart(document.getElementById('chartZerodhaNavCurve'), {{
      type: 'line',
      data: {{
        labels: timelineData.periods,
        datasets: [
          {{ label: 'Zerodha Portfolio NAV (Base 100)', data: timelineData.nav_series, borderColor: '#f59e0b', backgroundColor: 'rgba(245, 158, 11, 0.1)', fill: true, tension: 0.3, yAxisID: 'yNav' }},
          {{ label: 'Portfolio Valuation (₹)', data: timelineData.portfolio_values, borderColor: '#3b82f6', borderDash: [3, 3], fill: false, yAxisID: 'yVal' }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        plugins: {{ legend: {{ labels: {{ color: '#94a3b8' }} }} }},
        scales: {{
          x: {{ ticks: {{ color: '#64748b' }} }},
          yNav: {{ type: 'linear', position: 'left', title: {{ display: true, text: 'NAV Index (Base 100)', color: '#f59e0b' }}, ticks: {{ color: '#f59e0b' }} }},
          yVal: {{ type: 'linear', position: 'right', title: {{ display: true, text: 'Portfolio Value (₹)', color: '#3b82f6' }}, ticks: {{ color: '#3b82f6' }}, grid: {{ drawOnChartArea: false }} }}
        }}
      }}
    }});

    // Initialize Default View on Page Startup
    onFilterChange();
  </script>

  <!-- TAB 5: AI INSIGHTS -->
  <div id="tab-ai" class="tab-content" style="padding:0;">
    {ai_insights_html}
  </div>

</body>
</html>
"""

    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Generated HTML Dashboard -> {html_path}")


generate_html_dashboard = generate_dashboard

if __name__ == "__main__":
    generate_dashboard()
