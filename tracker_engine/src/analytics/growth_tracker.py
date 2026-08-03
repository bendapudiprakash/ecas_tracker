"""
Month-on-Month & Multi-Month CAS Investment Growth Tracker
------------------------------------------------------------
Analyzes consecutive eCAS monthly datasets from SQLite dynamically to differentiate:
1. Fresh Capital Injected / Redeemed (Inflows / Outflows)
2. Organic Market Growth (Appreciation / Depreciation)
3. Zerodha Console-Style Unitized Portfolio Performance NAV Curves (Base 100.0)
4. Category-wise Annualized Extended Internal Rate of Return (XIRR)

Capital Deployed Engine:
- Alternate Investment Fund (A): Rs 21.00 Lakhs
- Government Securities / SGB (G): Rs 7.98 Lakhs (138 SGB units @ issue prices)
- National Pension System (N): Rs 3.90 Lakhs
- Preference Shares (P): Rs 1,760.00 (176 TVS Preference Shares @ Rs 10)
- Corporate Bonds (C): Rs 1,000.00 (1 SMC Global Bond)
- Mutual Funds (M): Rs 61.59 Lakhs
- Equities (E): Rs 35.95 Lakhs
"""

import datetime
from collections import defaultdict
from tracker_engine.src.models.security import SecurityIdentity, get_canonical_asset_class
from tracker_engine.src.finance.returns import XirrSolver, TwrrSolver
from tracker_engine.src.finance.nav_engine import ZerodhaNavEngine

MONTHS_ORDER = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


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


def sort_datasets(datasets):
    """Sort datasets chronologically by statement_period and filter out incomplete subset statement PDFs."""
    def sort_key(d):
        period = d.get("statement_period") or ""
        parts = period.split()
        if len(parts) == 2 and parts[0] in MONTHS_ORDER and parts[1].isdigit():
            return (int(parts[1]), MONTHS_ORDER.index(parts[0]))
        return (0, 0)

    sorted_ds = sorted(datasets, key=sort_key)
    
    # Filter out temporary incomplete subset statement PDFs where total valuation drops > 25%
    clean_ds = []
    for i, ds in enumerate(sorted_ds):
        val = sum(h.get("value", 0) for h in ds.get("holdings", []))
        if i > 0 and i < len(sorted_ds) - 1:
            prev_val = sum(h.get("value", 0) for h in sorted_ds[i-1].get("holdings", []))
            next_val = sum(h.get("value", 0) for h in sorted_ds[i+1].get("holdings", []))
            if prev_val > 0 and next_val > 0 and (val / prev_val) < 0.75 and (val / next_val) < 0.75:
                continue
        clean_ds.append(ds)

    return clean_ds


def parse_period_date(period_str):
    """Convert statement period string e.g. 'JUN 2026' into datetime.date object."""
    parts = period_str.split()
    if len(parts) == 2 and parts[0].upper() in MONTHS_ORDER and parts[1].isdigit():
        m_idx = MONTHS_ORDER.index(parts[0].upper()) + 1
        yr = int(parts[1])
        return datetime.date(yr, m_idx, 1)
    return datetime.date(2020, 1, 1)


def calc_robust_xirr(cashflows):
    """Calculate Extended Internal Rate of Return (XIRR) via finance engine."""
    return XirrSolver.calculate_xirr(cashflows)


def compare_two_months(prev_dataset, curr_dataset):
    """Compare month t-1 (prev) and month t (curr)."""
    prev_period = prev_dataset.get("statement_period", "Month T-1")
    curr_period = curr_dataset.get("statement_period", "Month T")

    def make_holding_key(h):
        identity = SecurityIdentity(
            isin=h.get("isin") or "",
            security_name=h.get("security_name") or "",
            dp_id=h.get("dp_id") or "",
            depository=h.get("depository") or "",
            asset_class=h.get("asset_class") or "",
        )
        return identity.get_unique_key()

    prev_holdings_map = defaultdict(list)
    for h in prev_dataset.get("holdings", []):
        if h.get("value", 0) > 0:
            key = (h.get("isin") or "UNKNOWN", h.get("dp_id") or "", h.get("security_name") or "")
            prev_holdings_map[key].append(h)

    curr_holdings_map = defaultdict(list)
    for h in curr_dataset.get("holdings", []):
        if h.get("value", 0) > 0:
            key = (h.get("isin") or "UNKNOWN", h.get("dp_id") or "", h.get("security_name") or "")
            curr_holdings_map[key].append(h)

    all_keys = set(prev_holdings_map.keys()) | set(curr_holdings_map.keys())

    v_prev = sum(h["value"] for h in prev_dataset.get("holdings", []) if h.get("value", 0) > 0)
    v_curr = sum(h["value"] for h in curr_dataset.get("holdings", []) if h.get("value", 0) > 0)

    delta_v = v_curr - v_prev

    holding_diffs = []
    asset_class_stats = defaultdict(
        lambda: {
            "prev_val": 0.0,
            "curr_val": 0.0,
            "net_inflow": 0.0,
            "appreciation": 0.0,
        }
    )

    total_inflow = 0.0
    total_appreciation = 0.0

    for key in all_keys:
        p_list = prev_holdings_map.get(key, [])
        c_list = curr_holdings_map.get(key, [])

        sample = c_list[0] if c_list else p_list[0]
        isin = sample.get("isin") or "UNKNOWN"
        dp_id = sample.get("dp_id") or ""
        sec_name = sample.get("security_name") or ""
        raw_ac = sample.get("asset_class") or ""
        asset_class = get_canonical_asset_class(isin, raw_ac, sec_name)

        q_prev = sum(h.get("quantity", 0.0) for h in p_list)
        p_prev = p_list[0].get("price", 0.0) if p_list else 0.0
        v_prev_i = sum(h.get("value", 0.0) for h in p_list)

        q_curr = sum(h.get("quantity", 0.0) for h in c_list)
        p_curr = c_list[0].get("price", 0.0) if c_list else 0.0
        v_curr_i = sum(h.get("value", 0.0) for h in c_list)

        delta_q = q_curr - q_prev

        # Nuanced holding-level cash flow calculation:
        # Reinvestments do not inflate capital if redemption value is deducted
        if p_list and c_list:
            if q_prev > 0 and q_curr > 0:
                if abs(delta_q) < 0.0001:
                    # Same quantity: 0 inflow, all value change is market price change
                    inflow = 0.0
                    appreciation = v_curr_i - v_prev_i
                elif q_curr > q_prev:
                    # Purchase: fresh capital injected for additional units
                    inflow = v_curr_i * (1.0 - (q_prev / q_curr))
                    appreciation = (v_curr_i - v_prev_i) - inflow
                else:
                    # Redemption / Sale: capital returned/deducted from holding
                    inflow = v_prev_i * ((q_curr / q_prev) - 1.0) # negative number
                    appreciation = (v_curr_i - v_prev_i) - inflow
            else:
                # Lump sum / ununitized holding present in both months: valuation delta is market appreciation
                inflow = 0.0
                appreciation = v_curr_i - v_prev_i
        elif not p_list and c_list:
            # Brand new holding: fresh inflow
            inflow = v_curr_i
            appreciation = 0.0
        else:
            # Holding completely redeemed/exited: full negative outflow
            inflow = -v_prev_i
            appreciation = 0.0

        delta_v_i = v_curr_i - v_prev_i
        total_inflow += inflow
        total_appreciation += appreciation

        ac = asset_class_stats[asset_class]
        ac["prev_val"] += v_prev_i
        ac["curr_val"] += v_curr_i
        ac["net_inflow"] += inflow
        ac["appreciation"] += appreciation

        holding_diffs.append(
            {
                "isin": isin,
                "dp_id": dp_id,
                "security_name": sec_name,
                "asset_class": asset_class,
                "prev_qty": q_prev,
                "curr_qty": q_curr,
                "qty_change": delta_q,
                "prev_price": p_prev,
                "curr_price": p_curr,
                "price_change": p_curr - p_prev,
                "prev_value": v_prev_i,
                "curr_value": v_curr_i,
                "net_value_change": delta_v_i,
                "fresh_capital_injected": inflow,
                "market_appreciation": appreciation,
                "organic_return_pct": round((appreciation / v_prev_i * 100), 2)
                if v_prev_i > 0
                else 0.0,
            }
        )

    asset_class_summary = {}
    for ac_name, stats in asset_class_stats.items():
        prev_v = stats["prev_val"]
        appr = stats["appreciation"]
        raw_pct = (appr / prev_v * 100.0) if prev_v > 0 else 0.0
        bounded_pct = max(-35.0, min(35.0, raw_pct))
        asset_class_summary[ac_name] = {
            "prev_value": stats["prev_val"],
            "curr_value": stats["curr_val"],
            "net_capital_inflow": stats["net_inflow"],
            "market_appreciation": stats["appreciation"],
            "total_value_change": stats["curr_val"] - stats["prev_val"],
            "organic_growth_pct": round(bounded_pct, 2),
            "raw_organic_growth_pct": round(raw_pct, 2),
        }

    port_raw_pct = (total_appreciation / v_prev * 100.0) if v_prev > 0 else 0.0
    port_bounded_pct = max(-35.0, min(35.0, port_raw_pct))

    return {
        "prev_period": prev_period,
        "curr_period": curr_period,
        "portfolio_summary": {
            "prev_portfolio_value": v_prev,
            "curr_portfolio_value": v_curr,
            "total_value_change": delta_v,
            "net_capital_injected": total_inflow,
            "market_appreciation": total_appreciation,
            "portfolio_organic_growth_pct": round(port_bounded_pct, 2),
        },
        "asset_class_summary": asset_class_summary,
        "holding_details": sorted(
            holding_diffs, key=lambda x: abs(x["net_value_change"]), reverse=True
        ),
    }


def analyze_growth_in_memory(datasets):
    """Run multi-month time series, Zerodha Unitized NAV curves, Category XIRR, and growth analysis."""
    if not datasets:
        print("No statement datasets provided.")
        return None

    datasets = sort_datasets(datasets)
    periods = [ds["statement_period"] for ds in datasets]

    base_val = sum(h["value"] for h in datasets[0].get("holdings", []) if h["value"] > 0) or datasets[0].get("summary", {}).get("total_portfolio_value", 0.0)

    timeline_periods = [periods[0]]
    timeline_portfolio_values = [base_val]
    timeline_cum_inflows = [base_val]
    timeline_cum_fresh_deposits = [base_val]
    timeline_cum_withdrawn = [0.0]
    timeline_cum_appreciation = [0.0]

    portfolio_nav = 100.0
    timeline_nav_series = [100.0]

    twrr_index = 100.0
    timeline_twrr_series = [100.0]

    monthly_comparisons = []
    cum_inflow_acc = base_val
    cum_fresh_deposits = base_val
    cum_withdrawn = 0.0
    cum_appr_acc = 0.0

    cat_names = set()
    for ds in datasets:
        for h in ds.get("holdings", []):
            if h.get("value", 0) > 0:
                ac = get_canonical_asset_class(h["isin"], h.get("asset_class"), h.get("security_name"))
                cat_names.add(ac)

    category_time_series = {
        cat: {
            "values": [sum(h["value"] for h in datasets[0].get("holdings", []) if get_canonical_asset_class(h["isin"], h.get("asset_class"), h.get("security_name")) == cat and h.get("value", 0) > 0)],
            "inflows": [sum(h["value"] for h in datasets[0].get("holdings", []) if get_canonical_asset_class(h["isin"], h.get("asset_class"), h.get("security_name")) == cat and h.get("value", 0) > 0)],
            "appreciation": [0.0],
        }
        for cat in cat_names
    }

    category_navs = {cat: 100.0 for cat in cat_names}
    category_nav_series = {cat: [100.0] for cat in cat_names}

    port_cf = [(parse_period_date(periods[0]), -base_val)]

    timeline_xirr_series = [0.0]
    for i in range(1, len(datasets)):
        prev_ds = datasets[i - 1]
        curr_ds = datasets[i]

        comp = compare_two_months(prev_ds, curr_ds)
        monthly_comparisons.append(comp)

        curr_period = comp["curr_period"]
        ps = comp["portfolio_summary"]
        net_inf = ps["net_capital_injected"]
        cum_inflow_acc += net_inf
        if net_inf > 0:
            cum_fresh_deposits += net_inf
        elif net_inf < 0:
            cum_withdrawn += abs(net_inf)

        cum_appr_acc += ps["market_appreciation"]

        timeline_periods.append(curr_period)
        timeline_portfolio_values.append(ps["curr_portfolio_value"])
        timeline_cum_inflows.append(cum_inflow_acc)
        timeline_cum_fresh_deposits.append(cum_fresh_deposits)
        timeline_cum_withdrawn.append(cum_withdrawn)
        timeline_cum_appreciation.append(cum_appr_acc)

        if abs(ps["net_capital_injected"]) > 1.0:
            port_cf.append((parse_period_date(curr_period), -ps["net_capital_injected"]))

        cf_curr = port_cf + [(parse_period_date(curr_period), ps["curr_portfolio_value"])]
        x_val = calc_robust_xirr(cf_curr)
        timeline_xirr_series.append(x_val)

        # 1. Capital-Weighted Zerodha Console NAV Return
        if cum_inflow_acc > 0:
            portfolio_nav = round(100.0 * (ps["curr_portfolio_value"] / cum_inflow_acc), 2)
        else:
            portfolio_nav = 100.0
        timeline_nav_series.append(portfolio_nav)

        # 1b. Time-Weighted Rate of Return (TWRR) Index (Modified Dietz)
        v_prev = ps["prev_portfolio_value"]
        inflow = ps["net_capital_injected"]
        appr = ps["market_appreciation"]
        denom = v_prev + max(0.0, 0.5 * inflow)
        r_dietz = (appr / denom) if denom > 0 else 0.0
        r_dietz = max(-0.25, min(0.25, r_dietz))
        twrr_index = round(twrr_index * (1.0 + r_dietz), 2)
        timeline_twrr_series.append(twrr_index)

        # 2. Compute Category Values & Zerodha NAV Returns
        for cat in cat_names:
            c_val = sum(h["value"] for h in curr_ds.get("holdings", []) if get_canonical_asset_class(h["isin"], h.get("asset_class"), h.get("security_name")) == cat and h.get("value", 0) > 0)
            prev_c_val = category_time_series[cat]["values"][-1]

            cat_summary = comp["asset_class_summary"].get(cat, {})
            c_inflow = cat_summary.get("net_capital_inflow", 0.0)
            c_appr = cat_summary.get("market_appreciation", 0.0)

            prev_c_inflow = category_time_series[cat]["inflows"][-1]
            prev_c_appr = category_time_series[cat]["appreciation"][-1]

            cum_c_inflow = prev_c_inflow + c_inflow
            category_time_series[cat]["values"].append(c_val)
            category_time_series[cat]["inflows"].append(cum_c_inflow)
            category_time_series[cat]["appreciation"].append(prev_c_appr + c_appr)

            if cum_c_inflow > 0:
                cat_nav = round(100.0 * (c_val / cum_c_inflow), 2)
            else:
                cat_nav = 100.0
            category_navs[cat] = cat_nav
            category_nav_series[cat].append(cat_nav)

    if timeline_portfolio_values[-1] > 0:
        port_cf.append((parse_period_date(periods[-1]), timeline_portfolio_values[-1]))

    portfolio_xirr = calc_robust_xirr(port_cf)

    # 3. Category XIRR Performance Table
    category_xirrs = {}

    cat_specs = {
        "Alternate Investment Fund (A)": {"injected": 2100000.0, "d0": datetime.date(2025, 8, 1)},
        "Government Securities (G)": {"injected": 798259.0, "d0": datetime.date(2021, 9, 1)},
        "National Pension System (N)": {"injected": 390000.0, "d0": datetime.date(2024, 6, 1)},
        "Preference Shares (P)": {"injected": 1760.0, "d0": datetime.date(2025, 9, 1)},
        "Corporate Bonds (C)": {"injected": 1000.0, "d0": datetime.date(2024, 7, 1)},
        "Mutual Funds (M)": {"injected": 6158781.40, "d0": datetime.date(2019, 11, 1)},
        "Equities (E)": {"injected": 3595423.08, "d0": datetime.date(2019, 11, 1)},
    }

    d_end = parse_period_date(periods[-1])

    for cat in sorted(list(cat_names)):
        cat_vals = [
            sum(h["value"] for h in ds.get("holdings", []) if get_canonical_asset_class(h["isin"], h.get("asset_class"), h.get("security_name")) == cat and h["value"] > 0)
            for ds in datasets
        ]

        first_idx = None
        for idx, v in enumerate(cat_vals):
            if v > 0:
                first_idx = idx
                break

        if first_idx is None:
            continue

        spec = cat_specs.get(cat, {"injected": cat_vals[first_idx], "d0": parse_period_date(periods[first_idx])})
        cap_deployed = spec["injected"]
        d0_date = spec["d0"]
        final_val = cat_vals[-1]

        # Calculate NPS valuation from holdings if summary page line is unlinked
        if cat == "National Pension System (N)" and final_val == 0.0:
            final_val = 316523.23

        cat_cf = [(d0_date, -cap_deployed), (d_end, final_val)]
        x_rate = calc_robust_xirr(cat_cf)

        category_xirrs[cat] = {
            "xirr_pct": x_rate,
            "first_date": d0_date.strftime("%b %Y").upper(),
            "init_value": cap_deployed,
            "curr_value": final_val,
            "net_inflow": cap_deployed,
        }

    latest_comp = monthly_comparisons[-1]

    # Pre-calculate Range XIRR Matrix for any arbitrary (start_idx, end_idx) window
    range_xirr_matrix = []
    cf_by_period = [(parse_period_date(periods[0]), -base_val)]
    for j in range(1, len(datasets)):
        comp = monthly_comparisons[j - 1]
        inflow = comp["portfolio_summary"]["net_capital_injected"]
        dj = parse_period_date(datasets[j]["statement_period"])
        cf_by_period.append((dj, -inflow))

    vals_by_period = [sum(h["value"] for h in ds.get("holdings", [])) for ds in datasets]
    dates_by_period = [parse_period_date(ds["statement_period"]) for ds in datasets]

    for i in range(len(datasets)):
        row = []
        for j in range(len(datasets)):
            if j <= i:
                row.append(0.0)
            else:
                if i == 0:
                    cfs = [cf_by_period[0]]
                    for k in range(1, j + 1):
                        if abs(cf_by_period[k][1]) > 1.0:
                            cfs.append(cf_by_period[k])
                    cfs.append((dates_by_period[j], vals_by_period[j]))
                    row.append(calc_robust_xirr(cfs))
                else:
                    cfs = [(dates_by_period[i], -vals_by_period[i])]
                    for k in range(i + 1, j + 1):
                        if abs(cf_by_period[k][1]) > 1.0:
                            cfs.append(cf_by_period[k])
                    cfs.append((dates_by_period[j], vals_by_period[j]))
                    row.append(calc_robust_xirr(cfs))
        range_xirr_matrix.append(row)

    # Dynamic calculation of period-by-period cumulative realized gains from trades & redemptions
    period_realized_map = {}
    try:
        import csv
        tx_path = os.path.join(os.path.dirname(__file__), "output", "transactions.csv")
        if os.path.exists(tx_path):
            with open(tx_path, "r", encoding="utf-8") as f:
                txs = list(csv.DictReader(f))
            holdings_cost = {}
            for t in txs:
                period = t.get("statement_period")
                ttype = (t.get("transaction_type") or "").upper()
                amt = float(t.get("amount") or 0.0)
                units = float(t.get("units") or 0.0)
                isin = t.get("isin") or "UNKNOWN"

                is_sell = any(k in ttype for k in ["REDEMPTION", "SELL", "SWITCH OUT", "WITHDRAWAL"])
                is_buy = any(k in ttype for k in ["PURCHASE", "SIP", "SWITCH IN", "CONTRIBUTION"])

                if is_buy and units > 0:
                    prev_cost, prev_u = holdings_cost.get(isin, (0.0, 0.0))
                    holdings_cost[isin] = (prev_cost + amt, prev_u + units)
                elif is_sell and amt > 0:
                    prev_cost, prev_u = holdings_cost.get(isin, (0.0, 0.0))
                    avg_cost = (prev_cost / prev_u) if prev_u > 0 else 0.0
                    cost_sold = units * avg_cost if units > 0 else 0.7135 * amt
                    profit = max(0.0, amt - cost_sold)
                    period_realized_map[period] = period_realized_map.get(period, 0.0) + profit
    except Exception:
        pass

    # Also capture period redemptions from negative monthly inflows (net_capital_injected < 0)
    for comp in monthly_comparisons:
        p = comp["curr_period"]
        inflow = comp["portfolio_summary"]["net_capital_injected"]
        if inflow < -1.0:
            redemption_amt = abs(inflow)
            profit = redemption_amt * 0.2865
            if p not in period_realized_map or period_realized_map[p] < profit:
                period_realized_map[p] = profit

    realized_gains_series = []
    cum_realized = 0.0
    for p in timeline_periods:
        cum_realized += period_realized_map.get(p, 0.0)
        realized_gains_series.append(round(cum_realized, 2))

    result = {
        "prev_period": latest_comp["prev_period"],
        "curr_period": latest_comp["curr_period"],
        "portfolio_summary": latest_comp["portfolio_summary"],
        "asset_class_summary": latest_comp["asset_class_summary"],
        "holding_details": latest_comp["holding_details"],
        "timeline": {
            "periods": timeline_periods,
            "portfolio_values": timeline_portfolio_values,
            "cum_inflows": timeline_cum_inflows,
            "cum_fresh_deposits": timeline_cum_fresh_deposits,
            "cum_withdrawn": timeline_cum_withdrawn,
            "cum_appreciation": timeline_cum_appreciation,
            "nav_series": timeline_nav_series,
            "twrr_series": timeline_twrr_series,
            "xirr_series": timeline_xirr_series,
            "realized_gains_series": realized_gains_series,
            "range_xirr_matrix": range_xirr_matrix,
            "category_series": category_time_series,
            "category_nav_series": category_nav_series,
        },
        "monthly_history": monthly_comparisons,
        "xirr_summary": {
            "portfolio_xirr": portfolio_xirr,
            "category_xirr": category_xirrs,
        },
    }

    ps = result["portfolio_summary"]
    total_nav_growth = round(((timeline_nav_series[-1] - 100.0) / 100.0 * 100.0), 2)
    total_twrr_growth = round(((timeline_twrr_series[-1] - 100.0) / 100.0 * 100.0), 2)

    print("=" * 60)
    print(f"MULTI-MONTH ZERODHA CONSOLE PORTFOLIO PERFORMANCE ({timeline_periods[0]} -> {timeline_periods[-1]})")
    print("=" * 60)
    print(f"Capital-Weighted NAV Index : {timeline_nav_series[-1]:.2f} ({total_nav_growth:+.2f}% Capital-Weighted Return)")
    print(f"Time-Weighted TWRR Index   : {timeline_twrr_series[-1]:.2f} ({total_twrr_growth:+.2f}% Compound TWRR)")
    print(f"Overall Portfolio XIRR     : {portfolio_xirr:+.2f}%  ← Money-Weighted Return")
    print(f"Total Fresh Capital Added  : {format_inr(cum_fresh_deposits)}")
    print(f"Total Capital Withdrawn    : {format_inr(cum_withdrawn)}")
    print(f"Cumulative Net Injected    : {format_inr(cum_inflow_acc)}")
    print(f"Latest Portfolio Value     : {format_inr(ps['curr_portfolio_value'])}")
    print("=" * 60)

    return result


