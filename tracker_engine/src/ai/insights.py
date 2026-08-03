"""
Gemini AI Portfolio Insights Generator
---------------------------------------
Uses Antigravity agentapi (your existing Gemini subscription, no API key needed)
to analyse anonymised portfolio data and generate structured AI insights.

How it works:
  1. Calls `agentapi new-conversation --model=flash "<prompt>"` headlessly
  2. Polls the transcript file until the model response appears
  3. Extracts JSON insights and renders them as HTML for the dashboard

Privacy Policy for Prompt Data:
  ✅ Included (public financial instrument data, not PII):
      - Asset class names, ISIN codes, security/fund names
      - Portfolio totals, percentages, XIRR rates, holdings count
  ❌ Excluded (personal identifiers):
      - PAN, investor name, NSDL ID, DP ID, folio number, email, PDF filenames
"""

import json
import subprocess
import os
import re
import time
import glob


AGENTAPI = os.path.expanduser("~/.gemini/antigravity/bin/agentapi")
BRAIN_DIR = os.path.expanduser("~/.gemini/antigravity/brain")


# ---------------------------------------------------------------------------
# Privacy-safe aggregation
# ---------------------------------------------------------------------------

def _safe_aggregate(analysis: dict, curr_holdings: list) -> dict:
    """
    Build an anonymised-but-detailed portfolio snapshot for the AI prompt.

    ✅ Included  : asset class names, ISIN codes, security/fund names, values,
                   portfolio totals, XIRR rates, holdings counts
    ❌ Excluded  : PAN, investor name, NSDL ID, DP ID, folio, email, PDF filenames
    """
    ps = analysis["portfolio_summary"]
    xirr = analysis["xirr_summary"]
    timeline = analysis["timeline"]
    mom = analysis["asset_class_summary"]

    cat_summary = {}
    for cat, s in mom.items():
        cat_summary[cat] = {
            "deployed": round(s["net_capital_inflow"], 0),
            "current_value": round(s["curr_value"], 0),
            "organic_growth_pct": round(s["organic_growth_pct"], 2),
        }

    cat_xirrs = {}
    for cat, info in xirr.get("category_xirr", {}).items():
        cat_xirrs[cat] = round(info["xirr_pct"], 2)

    # Individual holdings — include ISIN + security name (public instrument data)
    # Exclude: pan, investor_name, dp_id, folio, depository, pdf_filename
    sanitised_holdings = [
        {
            "asset_class": h.get("asset_class", "Unknown"),
            "isin": h.get("isin", ""),
            "security_name": h.get("security_name", ""),
            "quantity": round(h.get("quantity", 0), 4),
            "price": round(h.get("price", 0), 2),
            "value": round(h.get("value", 0), 2),
            "cost_price": round(h.get("cost_price", 0), 2),
            "total_cost": round(h.get("total_cost", 0), 2),
        }
        for h in curr_holdings
    ]

    holdings_by_class: dict[str, int] = {}
    for h in sanitised_holdings:
        ac = h["asset_class"]
        holdings_by_class[ac] = holdings_by_class.get(ac, 0) + 1

    return {
        "period_from": timeline["periods"][0],
        "period_to": timeline["periods"][-1],
        "portfolio_value": round(ps["curr_portfolio_value"], 0),
        "net_deployed": round(
            analysis.get("cumulative_net_injected")
            or analysis.get("xirr_summary", {}).get("total_invested", 0)
            or sum(s.get("net_capital_inflow", 0) for s in mom.values()),
            0,
        ),
        "nav_index": round(timeline["nav_series"][-1], 2),
        "nav_return_pct": round(timeline["nav_series"][-1] - 100.0, 2),
        "portfolio_xirr_pct": round(xirr["portfolio_xirr"], 2),
        "mom_value_change": round(ps["total_value_change"], 0),
        "mom_organic_growth_pct": round(ps["portfolio_organic_growth_pct"], 2),
        "total_holdings_count": len(curr_holdings),
        "holdings_by_class": holdings_by_class,
        "category_breakdown": cat_summary,
        "category_xirrs": cat_xirrs,
        "holdings": sanitised_holdings,
    }


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def build_prompt(analysis: dict, curr_holdings: list) -> str:
    safe = _safe_aggregate(analysis, curr_holdings)

    cat_summary_lines = "\n".join(
        f"  - {cat}: Deployed ₹{v['deployed']:,.0f}, Current ₹{v['current_value']:,.0f}, "
        f"Growth {v['organic_growth_pct']:+.1f}%"
        for cat, v in safe["category_breakdown"].items()
    )

    cat_xirr_lines = "\n".join(
        f"  - {cat}: {pct:+.2f}% annualized XIRR"
        for cat, pct in safe["category_xirrs"].items()
    )

    top_holdings = sorted(safe["holdings"], key=lambda h: h["value"], reverse=True)[:15]
    top_holdings_lines = "\n".join(
        f"  - [{h['asset_class']}] {h['security_name']} ({h['isin']}) | "
        f"Qty: {h['quantity']:,.2f} | Value: ₹{h['value']:,.0f} | "
        f"Cost: ₹{h['total_cost']:,.0f} | Gain: ₹{h['value']-h['total_cost']:+,.0f}"
        for h in top_holdings
        if h.get("security_name") and h.get("isin")
    )

    return f"""You are an expert Indian retail investment analyst.
Analyse the following anonymised multi-year portfolio summary and provide concise, actionable insights.

## Portfolio Period
From {safe['period_from']} to {safe['period_to']}

## Overall Performance
- Current Portfolio Value: ₹{safe['portfolio_value']:,.0f}
- Cumulative Net Capital Deployed: ₹{safe['net_deployed']:,.0f}
- Zerodha NAV Index (Base 100): {safe['nav_index']:.2f} ({safe['nav_return_pct']:+.2f}% true market return)
- Portfolio XIRR: {safe['portfolio_xirr_pct']:+.2f}%
- MoM Change: ₹{safe['mom_value_change']:+,.0f} ({safe['mom_organic_growth_pct']:+.2f}% organic)

## Asset Class Breakdown (Capital Deployed vs Current Value)
{cat_summary_lines}

## Category-Wise Annualized XIRR
{cat_xirr_lines}

## Top 15 Holdings by Value (public instrument data — ISIN, Name, Gain/Loss)
{top_holdings_lines}

## Holdings Composition
{chr(10).join(f'  - {ac}: {count} securities' for ac, count in safe['holdings_by_class'].items())}
Total: {safe['total_holdings_count']} distinct securities

---

Respond with ONLY a JSON object, no other text, no markdown fences:
{{
  "overall_health": "<2-3 sentence overall portfolio health summary>",
  "top_performers": ["<insight 1 referencing specific funds/ISINs>", "<insight 2>", "<insight 3>"],
  "concerns": ["<concern 1>", "<concern 2>"],
  "allocation_advice": "<1-2 sentences on current allocation balance>",
  "action_items": ["<action 1>", "<action 2>", "<action 3>"]
}}

Be specific — reference actual fund names, asset classes, and numbers. Keep each point under 30 words."""


# ---------------------------------------------------------------------------
# Antigravity agentapi caller — polls transcript for response
# ---------------------------------------------------------------------------

def _call_via_agentapi(prompt: str, timeout: int = 90) -> tuple[dict | None, str | None]:
    """
    Launch a headless Antigravity conversation via agentapi,
    poll transcript_full.jsonl until a successful model response appears.
    Returns (result_dict, error_reason_str).
    """
    if not os.path.exists(AGENTAPI):
        return None, f"agentapi not found at {AGENTAPI}"

    def _start_conversation() -> str | None:
        try:
            result = subprocess.run(
                [AGENTAPI, "new-conversation", "--model=pro", prompt],
                capture_output=True,
                text=True,
                timeout=30,
            )
            resp = json.loads(result.stdout)
            return resp["response"]["newConversation"]["conversationId"]
        except Exception as e:
            print(f"⚠️ agentapi new-conversation failed: {e}")
            return None

    def _poll_transcript(conversation_id: str, deadline: float) -> tuple[dict | None, str | None]:
        transcript_path = os.path.join(
            BRAIN_DIR, conversation_id,
            ".system_generated", "logs", "transcript_full.jsonl"
        )
        while time.time() < deadline:
            time.sleep(3)
            if not os.path.exists(transcript_path):
                continue
            try:
                with open(transcript_path, "r") as f:
                    steps = [json.loads(l) for l in f if l.strip()]

                error_steps = [s for s in steps if s.get("type") == "ERROR_MESSAGE"]
                if error_steps and len(error_steps) >= 2:
                    last_err = error_steps[-1]
                    code = last_err.get("error_code", 0)
                    msg = last_err.get("error", "unknown error")
                    print(f"   ✗ Antigravity API error ({code}): {msg}")
                    return None, f"{code}: {msg}"

                for step in reversed(steps):
                    if step.get("type") == "PLANNER_RESPONSE" and step.get("status") == "DONE":
                        content = step.get("content", "")
                        json_match = re.search(r"\{[\s\S]+\}", content)
                        if json_match:
                            return json.loads(json_match.group()), None
            except Exception:
                continue
        return None, "Timed out waiting for model response"

    # Attempt 1
    cid = _start_conversation()
    if not cid:
        return None, "Failed to start Antigravity conversation"
    print(f"   → Antigravity conversation: {cid}")
    result, err = _poll_transcript(cid, time.time() + timeout)
    if result:
        return result, None

    # Retry once after 10s backoff (in case of transient 429)
    print("   → Retrying after 10s backoff...")
    time.sleep(10)
    cid2 = _start_conversation()
    if not cid2:
        return None, err
    print(f"   → Retry conversation: {cid2}")
    result2, err2 = _poll_transcript(cid2, time.time() + timeout)
    return result2, err2 or err


def get_ai_insights(analysis: dict, curr_holdings: list) -> tuple[dict | None, str | None]:
    """
    Fetch AI insights via Antigravity agentapi.
    Returns (insights_dict, error_reason) — error_reason is None on success.
    """
    prompt = build_prompt(analysis, curr_holdings)
    result, error = _call_via_agentapi(prompt)
    if result:
        print("✅ AI insights generated via Antigravity (Claude Sonnet)")
        return result, None
    print(f"⚠️ AI insights unavailable: {error}")
    return None, error


# ---------------------------------------------------------------------------
# HTML renderer
# ---------------------------------------------------------------------------

def render_ai_insights_html(insights: dict | None, error: str | None = None) -> str:
    is_rate_limit = error and "429" in str(error)
    is_timeout = error and "Timed out" in str(error)

    if not insights:
        if is_rate_limit:
            detail = """
              <div style="background:#1c1008;border:1px solid #92400e;border-radius:8px;padding:14px 18px;margin-top:16px;font-size:13px;color:#fcd34d;">
                <strong>Rate limit hit (429)</strong> — the model API is temporarily overloaded.<br>
                Re-run <code>python run_tracker.py</code> in a few minutes and AI insights will populate automatically.
              </div>"""
        elif is_timeout:
            detail = """
              <div style="background:#0f1c2e;border:1px solid #1e40af;border-radius:8px;padding:14px 18px;margin-top:16px;font-size:13px;color:#93c5fd;">
                <strong>Response timed out</strong> — the model took too long to respond.<br>
                Re-run <code>python run_tracker.py</code> to try again.
              </div>"""
        else:
            detail = """
              <div style="background:#0f1c2e;border:1px solid #1e293b;border-radius:8px;padding:14px 18px;margin-top:16px;font-size:13px;color:#94a3b8;">
                Make sure <strong>Antigravity 2.0</strong> is running when you execute <code>python run_tracker.py</code>.
              </div>"""
        return f"""
        <div style="padding:48px;text-align:center;color:#64748b;">
          <div style="font-size:52px;margin-bottom:16px;">{"⏱️" if is_rate_limit else "🤖"}</div>
          <div style="font-size:17px;font-weight:700;color:#94a3b8;margin-bottom:10px;">
            {"Rate Limit — Try Again Shortly" if is_rate_limit else "AI Insights Unavailable"}
          </div>
          {detail}
        </div>
        """

    def render_list(items: list, color: str, icon: str) -> str:
        return "".join(
            f'<li style="padding:9px 0;border-bottom:1px solid #1e293b;color:#e2e8f0;font-size:14px;line-height:1.5;">'
            f'<span style="color:{color};margin-right:8px;font-weight:700;">{icon}</span>{item}</li>'
            for item in items
        )

    return f"""
    <div style="padding:32px 24px;max-width:960px;margin:0 auto;">

      <div style="background:linear-gradient(135deg,#1e293b,#0f172a);border:1px solid #334155;border-radius:12px;padding:24px;margin-bottom:24px;">
        <div style="font-size:11px;font-weight:700;color:#94a3b8;letter-spacing:1.5px;margin-bottom:10px;">🤖 GEMINI AI — PORTFOLIO HEALTH SUMMARY</div>
        <p style="color:#f1f5f9;font-size:15px;line-height:1.8;margin:0;">{insights.get("overall_health","")}</p>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-bottom:20px;">
        <div style="background:#151c2c;border:1px solid #1e293b;border-radius:12px;padding:20px;">
          <div style="font-size:11px;font-weight:700;color:#10b981;letter-spacing:1.5px;margin-bottom:14px;">✅ TOP PERFORMERS</div>
          <ul style="list-style:none;margin:0;padding:0;">
            {render_list(insights.get("top_performers", []), "#10b981", "▲")}
          </ul>
        </div>
        <div style="background:#151c2c;border:1px solid #1e293b;border-radius:12px;padding:20px;">
          <div style="font-size:11px;font-weight:700;color:#f59e0b;letter-spacing:1.5px;margin-bottom:14px;">⚠️ WATCH POINTS</div>
          <ul style="list-style:none;margin:0;padding:0;">
            {render_list(insights.get("concerns", []), "#f59e0b", "△")}
          </ul>
        </div>
      </div>

      <div style="background:#151c2c;border:1px solid #1e293b;border-radius:12px;padding:20px;margin-bottom:20px;">
        <div style="font-size:11px;font-weight:700;color:#a78bfa;letter-spacing:1.5px;margin-bottom:10px;">📊 ALLOCATION ASSESSMENT</div>
        <p style="color:#e2e8f0;font-size:14px;line-height:1.7;margin:0;">{insights.get("allocation_advice","")}</p>
      </div>

      <div style="background:#151c2c;border:1px solid #1e293b;border-radius:12px;padding:20px;">
        <div style="font-size:11px;font-weight:700;color:#3b82f6;letter-spacing:1.5px;margin-bottom:14px;">🎯 RECOMMENDED ACTIONS</div>
        <ul style="list-style:none;margin:0;padding:0;">
          {render_list(insights.get("action_items", []), "#3b82f6", "→")}
        </ul>
      </div>

      <div style="margin-top:16px;text-align:right;font-size:11px;color:#475569;">
        Generated by Gemini via Antigravity &nbsp;•&nbsp; No PII was sent to the model
      </div>

    </div>
    """
