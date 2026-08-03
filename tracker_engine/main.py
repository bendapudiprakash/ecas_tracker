"""
CAS Tracker Main CLI Orchestrator
--------------------------------
Orchestrates end-to-end execution:
1. Multi-Mailbox Gmail eCAS Sync (--sync / -s or --force-all)
2. Incremental eCAS PDF Ingestion into SQLite (cas_tracker.db)
3. Strict Real Trade Transaction Extraction (extract_transactions.py)
4. Multi-PAN Family Portfolio Analysis & Zerodha Performance Curve (track_growth.py)
5. 4-Tab Interactive HTML Dashboard Generator (generate_report.py -> output/dashboard.html)
6. Google Sheets & Excel Workbook Exporter (export_sheets.py -> output/ecas_portfolio_tracker.xlsx)

Usage:
    python run_tracker.py          # Fast local execution using SQLite cache
    python run_tracker.py --sync   # Incremental mailbox sync (SINCE latest statement date)
    python run_tracker.py --force-all # Force full mailbox re-sync
"""

import os
import sys
import glob
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

from tracker_engine.src.parsers.gmail_sync import fetch_new_cas_from_gmail
from tracker_engine.src.parsers.ecas_parser import extract_data_from_pdf, extract_statement_period
from tracker_engine.src.storage.repository import init_db, is_pdf_processed, store_statement_data, get_all_statements_data
from tracker_engine.src.analytics.growth_tracker import analyze_growth_in_memory
from tracker_engine.src.reporting.html_report import generate_dashboard
from tracker_engine.src.parsers.tx_parser import extract_all_transactions
from tracker_engine.src.reporting.excel_report import export_portfolio_to_excel


def get_latest_period_from_db():
    datasets = get_all_statements_data()
    if not datasets:
        return None
    periods = [ds["statement_period"] for ds in datasets]
    months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]

    def sort_key(p):
        parts = p.split()
        if len(parts) == 2 and parts[0] in months and parts[1].isdigit():
            return (int(parts[1]), months.index(parts[0]))
        return (0, 0)

    sorted_periods = sorted(periods, key=sort_key)
    return sorted_periods[-1]


def run_all(sync=False, force_all=False, with_ai=False):
    print("=" * 60)
    print("CAS TRACKER: Automated Pipeline Engine")
    print("=" * 60)

    init_db()

    INPUT_DIR = os.path.join(BASE_DIR, "input")
    OUTPUT_DIR = os.path.join(BASE_DIR, "output")

    # 1. Multi-Mailbox Sync
    if sync or force_all:
        since_date = None
        if not force_all:
            latest_period = get_latest_period_from_db()
            if latest_period:
                parts = latest_period.split()
                since_date = f"01-{parts[0].capitalize()}-{parts[1]}"
        fetch_new_cas_from_gmail(since_date=since_date)
    else:
        print("ℹ️ Gmail sync skipped (pass '--sync' or '-s' to check mailbox for new eCAS statements).")

    # 2. Ingest PDFs into SQLite (strictly NSDLe-CAS_*.PDF)
    pdf_files = sorted(glob.glob(os.path.join(INPUT_DIR, "NSDLe-CAS_*.PDF")) + glob.glob(os.path.join(INPUT_DIR, "NSDLe-CAS_*.pdf")))

    new_ingested = 0
    cached_count = 0
    skipped_count = 0

    for pdf_path in pdf_files:
        pdf_name = os.path.basename(pdf_path)
        existing = is_pdf_processed(pdf_name)

        if existing:
            cached_count += 1
            print(f"⚡ [Cached in SQLite] {pdf_name}")
        else:
            print(f"🔍 [Parsing PDF] {pdf_name}...")
            data = extract_data_from_pdf(pdf_path)
            if data and data.get("statement_period"):
                store_statement_data(
                    pdf_filename=pdf_name,
                    statement_period=data["statement_period"],
                    cas_type="NSDL",
                    summary_dict=data["summary"],
                    holdings_list=data["holdings"],
                    investor_name=data.get("investor_name", "BENDAPUDI SRI SAI SATYA PRAKASH"),
                    pan=data.get("pan", "ABCDE1234F"),
                    cas_id=data.get("cas_id", "12345678"),
                )
                new_ingested += 1
                print(f"  └─ Ingested into SQLite: {pdf_name} ({data['statement_period']})")
            else:
                skipped_count += 1

    print(f"\nPipeline status: {cached_count} cached, {new_ingested} newly ingested, {skipped_count} skipped.")

    # 3. Extract strict real trade transactions (loaded from SQLite cache unless force_all is requested)
    extract_all_transactions(force_reextract=force_all)

    # 4. Load historical records directly from SQLite
    datasets = get_all_statements_data()

    print("\n" + "=" * 60)
    print("ANALYZING MULTI-MONTH GROWTH & PERFORMANCE...")
    print("=" * 60)
    analysis = analyze_growth_in_memory(datasets)

    if analysis:
        print("\n" + "=" * 60)
        print("GENERATING HTML DASHBOARD & EXCEL/GOOGLE SHEETS WORKBOOK...")
        print("=" * 60)
        generate_dashboard(analysis, output_path=os.path.join(OUTPUT_DIR, "dashboard.html"), with_ai=with_ai)
        export_portfolio_to_excel(output_path=os.path.join(OUTPUT_DIR, "ecas_portfolio_tracker.xlsx"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run complete eCAS portfolio tracking pipeline.")
    parser.add_argument("--sync", "-s", action="store_true", help="Sync Gmail for new eCAS statements incrementally.")
    parser.add_argument("--force-all", action="store_true", help="Force search entire Gmail mailbox history.")
    parser.add_argument("--ai", "-a", action="store_true", help="Run Claude Sonnet AI portfolio insights analysis.")

    args = parser.parse_args()
    run_all(sync=args.sync, force_all=args.force_all, with_ai=args.ai)
