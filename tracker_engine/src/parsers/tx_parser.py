"""
eCAS Transaction Extraction Engine
----------------------------------
Extracts strict real trade transactions (SIPs, Purchases, Redemptions, Demat Credits/Debits)
across all eCAS PDF statements in input/ and stores them into SQLite and CSV format.
Supports multi-PAN Family Portfolio filtering.
"""

import pdfplumber
import glob
import os
import re
import datetime
import csv

from tracker_engine.src.parsers.ecas_parser import (
    get_canonical_asset_class,
    extract_statement_period,
    extract_investor_profile,
    to_num,
)
from tracker_engine.src.storage.repository import get_connection, init_db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INPUT_DIR = os.path.join(BASE_DIR, "input")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

MONTHS_ORDER = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def parse_date(d_str):
    try:
        parts = d_str.strip().split("-")
        if len(parts) == 3:
            day = int(parts[0])
            m_idx = MONTHS_ORDER.index(parts[1].upper()) + 1
            yr = int(parts[2])
            return datetime.date(yr, m_idx, day).strftime("%Y-%m-%d")
    except Exception:
        pass
    return d_str


def get_stored_transactions():
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        """
        SELECT statement_period, transaction_date, pan, investor_name, isin, security_name,
               asset_class, transaction_type, amount, units, price_nav, pdf_filename
        FROM transactions
        ORDER BY id ASC
    """
    )
    rows = c.fetchall()
    conn.close()

    txs = []
    for r in rows:
        txs.append(
            {
                "statement_period": r[0],
                "transaction_date": r[1],
                "pan": r[2],
                "investor_name": r[3],
                "isin": r[4],
                "security_name": r[5],
                "asset_class": r[6],
                "transaction_type": r[7],
                "amount": r[8],
                "units": r[9],
                "price_nav": r[10],
                "pdf_filename": r[11],
            }
        )
    return txs


def extract_all_transactions(force_reextract=False):
    init_db()
    conn = get_connection()
    c = conn.cursor()

    files = sorted(glob.glob(os.path.join(INPUT_DIR, "NSDLe-CAS_*")) + glob.glob(os.path.join(INPUT_DIR, "CDSLe-CAS_*")))
    if not files:
        files = sorted(glob.glob(os.path.join(INPUT_DIR, "*.pdf")) + glob.glob(os.path.join(INPUT_DIR, "*.PDF")))

    def sort_key(f):
        fn = os.path.basename(f)
        m = re.search(r"(?:NSDL|CDSL)e-CAS_\d+_([A-Z]{3})_(\d{4})\.PDF", fn, re.IGNORECASE)
        if m:
            return (int(m.group(2)), MONTHS_ORDER.index(m.group(1).upper()))
        return (0, 0)

    sorted_files = sorted(files, key=sort_key)

    c.execute("CREATE TABLE IF NOT EXISTS processed_tx_files (pdf_filename TEXT PRIMARY KEY)")
    c.execute("SELECT pdf_filename FROM processed_tx_files")
    existing_pdfs = set(r[0] for r in c.fetchall())

    unprocessed_files = [f for f in sorted_files if os.path.basename(f) not in existing_pdfs]

    if not force_reextract and not unprocessed_files:
        conn.close()
        stored_txs = get_stored_transactions()
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        csv_path = os.path.join(OUTPUT_DIR, "transactions.csv")
        if stored_txs:
            fieldnames = list(stored_txs[0].keys())
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(stored_txs)
        print(f"⚡ [Cached in SQLite] Loaded {len(stored_txs)} strict real trade transactions -> {csv_path}")
        return stored_txs

    if force_reextract:
        c.execute("DELETE FROM transactions")
        c.execute("DELETE FROM processed_tx_files")
        conn.commit()
        unprocessed_files = sorted_files

    try:
        from dotenv import load_dotenv

        load_dotenv()
        password = os.getenv("PDF_PASSWORD") or os.getenv("CAS_PDF_PASSWORD") or None
    except Exception:
        password = None

    all_txs = []
    print(f"Extracting strict real trade transactions across {len(unprocessed_files)} new/unprocessed eCAS PDF statements...")

    for pdf_path in unprocessed_files:
        fn = os.path.basename(pdf_path)
        c.execute("INSERT OR IGNORE INTO processed_tx_files (pdf_filename) VALUES (?)", (fn,))
        open_kwargs = {"password": password} if password else {}

        try:
            with pdfplumber.open(pdf_path, **open_kwargs) as pdf:
                full_text = "\n".join(p.extract_text() or "" for p in pdf.pages[:2])
                period = extract_statement_period(full_text, pdf_path=pdf_path) or fn
                profile = extract_investor_profile(full_text)
                pan = profile["pan"]
                investor_name = profile["investor_name"]

                curr_isin = ""
                curr_security = ""
                curr_raw_class = ""
                is_tx_table = False

                for p_idx, page in enumerate(pdf.pages):
                    tables = page.extract_tables()
                    for t in tables:
                        is_tx_table = False
                        for row in t:
                            if not row or not any(row):
                                continue
                            cells = [str(cell).strip() if cell else "" for cell in row]
                            r_str = " ".join(cells)
                            r_str_u = r_str.upper()
                            if any(
                                hdr.upper() in r_str_u
                                for hdr in [
                                    "Transaction Details",
                                    "Transaction Particulars",
                                    "NPS Transaction Details",
                                    "Credit Debit",
                                    "Credit / Debit",
                                    "Transaction Statement",
                                    "Transactions",
                                    "Particulars",
                                ]
                            ):
                                is_tx_table = True
                                continue
                            if "HOLDINGS" in r_str_u or "HOLDING DETAILS" in r_str_u or "SUMMARY OF HOLDINGS" in r_str_u:
                                is_tx_table = False
                                continue

                            m_isin = re.search(r"(IN[A-Z0-9]{10})", r_str)
                            if m_isin:
                                curr_isin = m_isin.group(1)
                                curr_security = cells[1] if len(cells) > 1 and cells[1] else curr_isin

                            m_date = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4})", r_str)
                            if m_date and is_tx_table:
                                date_raw = m_date.group(1)
                                iso_date = parse_date(date_raw)

                                non_empty = [c.replace("\n", " ") for c in cells if c != ""]
                                if len(non_empty) < 2:
                                    continue

                                desc = non_empty[1] if len(non_empty) > 1 else "Transaction"
                                desc_u = desc.upper()

                                # Skip balance snapshots and non-trade administrative lines
                                if any(kw in desc_u for kw in [
                                    "OPENING BALANCE", "CLOSING BALANCE", "ADDRESS", "NOMINEE",
                                    "KYC", "BANK DETAILS", "ISIN :", "STATEMENT OF ACCOUNT"
                                ]):
                                    continue

                                num_vals = []
                                for cell in non_empty:
                                    n = to_num(cell)
                                    if n != 0.0 or cell in ("0", "0.00", "0.000"):
                                        num_vals.append(n)

                                if not num_vals:
                                    continue

                                amount = num_vals[0] if len(num_vals) >= 1 else 0.0
                                price_nav = num_vals[1] if len(num_vals) >= 2 else 0.0
                                units = num_vals[-1] if len(num_vals) >= 3 else (num_vals[0] if num_vals else 0.0)

                                asset_class = get_canonical_asset_class(curr_isin, curr_raw_class, curr_security)

                                tx_record = {
                                    "statement_period": period,
                                    "transaction_date": iso_date,
                                    "pan": pan,
                                    "investor_name": investor_name,
                                    "isin": curr_isin,
                                    "security_name": curr_security,
                                    "asset_class": asset_class,
                                    "transaction_type": desc,
                                    "amount": amount,
                                    "units": units,
                                    "price_nav": price_nav,
                                    "pdf_filename": fn,
                                }

                                all_txs.append(tx_record)

                                c.execute(
                                    """
                                    INSERT INTO transactions (
                                        statement_period, transaction_date, pan, investor_name, isin, security_name,
                                        asset_class, transaction_type, amount, units, price_nav, pdf_filename
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                    (
                                        period,
                                        iso_date,
                                        pan,
                                        investor_name,
                                        curr_isin,
                                        curr_security,
                                        asset_class,
                                        desc,
                                        amount,
                                        units,
                                        price_nav,
                                        fn,
                                    ),
                                )
        except Exception as e:
            print(f"⚠️ Error extracting transactions from '{fn}': {e}")

    conn.commit()
    conn.close()

    stored_txs = get_stored_transactions()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUTPUT_DIR, "transactions.csv")
    if stored_txs:
        fieldnames = list(stored_txs[0].keys())
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(stored_txs)

    print(f"✅ Extracted {len(all_txs)} new transactions. Total cached in SQLite: {len(stored_txs)} -> {csv_path}")
    return stored_txs


if __name__ == "__main__":
    extract_all_transactions()
