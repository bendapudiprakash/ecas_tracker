"""
SQLite Database Storage Layer for CAS Tracker
---------------------------------------------
Manages persistence of monthly eCAS statement summaries, holdings, and transactions
in cas_tracker.db. Supports multi-PAN Family Portfolio views.
"""

import sqlite3
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "cas_tracker.db")


def get_connection():
    return sqlite3.connect(DB_PATH)


def normalize_pan(raw_pan):
    if not raw_pan:
        return "UNKNOWN_PAN"
    clean = raw_pan.strip().upper()
    if "X" in clean or "*" in clean:
        if clean.startswith("BF") and clean.endswith("2G"):
            return "ABCDE1234F"
    return clean


def init_db():
    conn = get_connection()
    c = conn.cursor()

    # 1. Statements Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS statements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pdf_filename TEXT UNIQUE,
            statement_period TEXT,
            cas_type TEXT,
            investor_name TEXT,
            pan TEXT,
            cas_id TEXT,
            total_portfolio_value REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    for col in ["cas_type TEXT", "investor_name TEXT", "pan TEXT", "cas_id TEXT", "total_portfolio_value REAL"]:
        try:
            c.execute(f"ALTER TABLE statements ADD COLUMN {col}")
        except Exception:
            pass

    # 2. Holdings Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_id INTEGER,
            statement_period TEXT,
            pan TEXT,
            investor_name TEXT,
            asset_class TEXT,
            isin TEXT,
            security_name TEXT,
            quantity REAL,
            price REAL,
            value REAL,
            cost_price REAL,
            total_cost REAL,
            dp_id TEXT,
            depository TEXT,
            pdf_filename TEXT,
            FOREIGN KEY (statement_id) REFERENCES statements(id)
        )
    """
    )

    for col in ["pan TEXT", "investor_name TEXT", "statement_id INTEGER"]:
        try:
            c.execute(f"ALTER TABLE holdings ADD COLUMN {col}")
        except Exception:
            pass

    # 3. Transactions Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            statement_period TEXT,
            transaction_date TEXT,
            pan TEXT,
            investor_name TEXT,
            isin TEXT,
            security_name TEXT,
            asset_class TEXT,
            transaction_type TEXT,
            amount REAL,
            units REAL,
            price_nav REAL,
            pdf_filename TEXT
        )
    """
    )

    # 4. Processed Transaction Files Table
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_tx_files (
            pdf_filename TEXT PRIMARY KEY
        )
    """
    )

    conn.commit()
    conn.close()


def is_pdf_processed(pdf_filename):
    init_db()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id FROM statements WHERE pdf_filename = ?", (pdf_filename,))
    row = c.fetchone()
    conn.close()
    return row is not None


def store_statement_data(pdf_filename, statement_period, cas_type, summary_dict, holdings_list, investor_name="INVESTOR NAME", pan="ABCDE1234F", cas_id="12345678"):
    init_db()
    conn = get_connection()
    c = conn.cursor()

    norm_pan = normalize_pan(pan)
    tot_val = summary_dict.get("total_portfolio_value", 0.0) if summary_dict else 0.0

    c.execute(
        """
        INSERT INTO statements (pdf_filename, statement_period, cas_type, investor_name, pan, cas_id, total_portfolio_value)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pdf_filename) DO UPDATE SET
            statement_period=excluded.statement_period,
            cas_type=excluded.cas_type,
            investor_name=excluded.investor_name,
            pan=excluded.pan,
            cas_id=excluded.cas_id,
            total_portfolio_value=excluded.total_portfolio_value,
            created_at=CURRENT_TIMESTAMP
    """,
        (pdf_filename, statement_period, cas_type, investor_name, norm_pan, cas_id, tot_val),
    )

    c.execute("SELECT id FROM statements WHERE pdf_filename = ?", (pdf_filename,))
    stmt_id = c.fetchone()[0]

    c.execute("DELETE FROM holdings WHERE statement_id = ? OR pdf_filename = ?", (stmt_id, pdf_filename))

    for h in holdings_list:
        c.execute(
            """
            INSERT INTO holdings (
                statement_id, statement_period, pan, investor_name, asset_class, isin, security_name,
                quantity, price, value, cost_price, total_cost, dp_id, depository, pdf_filename
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                stmt_id,
                statement_period,
                norm_pan,
                investor_name,
                h.get("asset_class"),
                h.get("isin"),
                h.get("security_name"),
                h.get("quantity", 0.0),
                h.get("price", 0.0),
                h.get("value", 0.0),
                h.get("cost_price", 0.0),
                h.get("total_cost", 0.0),
                h.get("dp_id", ""),
                h.get("depository", ""),
                pdf_filename,
            ),
        )

    conn.commit()
    conn.close()


save_statement_data = store_statement_data


def get_all_statements_data():
    init_db()
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT id, pdf_filename, statement_period, total_portfolio_value, investor_name, pan, cas_id FROM statements")
    rows = c.fetchall()

    datasets = []
    for r in rows:
        stmt_id, pdf_filename, statement_period, total_val, investor_name, pan, cas_id = r

        c.execute(
            """
            SELECT asset_class, isin, security_name, quantity, price, value, cost_price, total_cost, dp_id, depository, pan, investor_name
            FROM holdings WHERE statement_id = ? OR pdf_filename = ?
        """,
            (stmt_id, pdf_filename),
        )
        h_rows = c.fetchall()

        holdings = []
        for hr in h_rows:
            holdings.append(
                {
                    "asset_class": hr[0],
                    "isin": hr[1],
                    "security_name": hr[2],
                    "quantity": hr[3],
                    "price": hr[4],
                    "value": hr[5],
                    "cost_price": hr[6],
                    "total_cost": hr[7],
                    "dp_id": hr[8],
                    "depository": hr[9],
                    "pan": hr[10] or pan or "ABCDE1234F",
                    "investor_name": hr[11] or investor_name or "INVESTOR NAME",
                }
            )

        summary = {
            "statement_period": statement_period,
            "total_portfolio_value": total_val or sum(h["value"] for h in holdings),
        }

        datasets.append(
            {
                "id": stmt_id,
                "pdf_filename": pdf_filename,
                "statement_period": statement_period,
                "cas_type": "NSDL",
                "investor_name": investor_name or "INVESTOR NAME",
                "pan": pan or "ABCDE1234F",
                "cas_id": cas_id or "12345678",
                "summary": summary,
                "holdings": holdings,
            }
        )

    conn.close()
    return datasets
