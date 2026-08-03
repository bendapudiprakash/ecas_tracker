"""
Multi-Mailbox NSDL eCAS PDF Downloader & Password Mapper
-------------------------------------------------------
Connects to multiple Gmail/IMAP mailboxes over SSL, searches for official NSDL/CDSL eCAS emails,
downloads attachments into input/, and maps per-mailbox CAS PDF passwords.

Supported Environment Configs (.env):
1. Single Mailbox Mode:
   GMAIL_USER=user1@gmail.com
   GMAIL_APP_PASSWORD=pass1
   PDF_PASSWORD=PAN1_PASSWORD

2. Multi-Mailbox Mode (Indexed):
   MAILBOX_1_USER=user1@gmail.com
   MAILBOX_1_APP_PASSWORD=app_pass_1
   MAILBOX_1_PDF_PASSWORD=PAN1_PASSWORD

   MAILBOX_2_USER=user2@gmail.com
   MAILBOX_2_APP_PASSWORD=app_pass_2
   MAILBOX_2_PDF_PASSWORD=PAN2_PASSWORD

3. JSON Config Mode:
   GMAIL_ACCOUNTS_JSON='[{"user":"user1@example.com","app_password":"p1","pdf_password":"PAN1"},{"user":"user2@example.com","app_password":"p2","pdf_password":"PAN2"}]'
"""

import os
import sys
import argparse
import imaplib
import email
import json
from email.header import decode_header
from dotenv import load_dotenv

load_dotenv()

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
PASSWORD_MAP_FILE = "cas_passwords.json"


def clean_filename(filename):
    if not filename:
        return ""
    decoded, encoding = decode_header(filename)[0]
    if isinstance(decoded, bytes):
        try:
            return decoded.decode(encoding or "utf-8", errors="ignore")
        except Exception:
            return str(decoded)
    return str(decoded)


def get_configured_mailboxes():
    """Discover all configured mailboxes and their mapped CAS PDF passwords."""
    mailboxes = []

    # 1. Check GMAIL_ACCOUNTS_JSON
    json_conf = os.getenv("GMAIL_ACCOUNTS_JSON")
    if json_conf:
        try:
            parsed = json.loads(json_conf)
            if isinstance(parsed, list):
                for acc in parsed:
                    mailboxes.append(
                        {
                            "user": acc.get("user") or acc.get("email"),
                            "app_password": acc.get("app_password") or acc.get("password"),
                            "pdf_password": acc.get("pdf_password") or acc.get("pan"),
                        }
                    )
        except Exception as e:
            print(f"⚠️ Error parsing GMAIL_ACCOUNTS_JSON: {e}")

    # 2. Check Indexed MAILBOX_1_USER, MAILBOX_2_USER...
    for i in range(1, 10):
        u = os.getenv(f"MAILBOX_{i}_USER") or os.getenv(f"MAILBOX_{i}_EMAIL")
        p = os.getenv(f"MAILBOX_{i}_APP_PASSWORD") or os.getenv(f"MAILBOX_{i}_PASSWORD")
        pdf_p = os.getenv(f"MAILBOX_{i}_PDF_PASSWORD") or os.getenv(f"MAILBOX_{i}_PAN")
        if u and p:
            mailboxes.append({"user": u, "app_password": p, "pdf_password": pdf_p})

    # 3. Fallback to single GMAIL_USER / GMAIL_EMAIL
    single_u = os.getenv("GMAIL_USER") or os.getenv("GMAIL_EMAIL")
    single_p = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_PASSWORD")
    single_pdf_p = os.getenv("PDF_PASSWORD") or os.getenv("CAS_PDF_PASSWORD")

    if single_u and single_p:
        if not any(m["user"] == single_u for m in mailboxes):
            mailboxes.append({"user": single_u, "app_password": single_p, "pdf_password": single_pdf_p})

    return [m for m in mailboxes if m["user"] and m["app_password"]]


def save_mapped_passwords(passwords):
    """Save discovered candidate passwords to cas_passwords.json for PDF decryption."""
    existing = set()
    if os.path.exists(PASSWORD_MAP_FILE):
        try:
            with open(PASSWORD_MAP_FILE, "r") as f:
                existing = set(json.load(f))
        except Exception:
            pass

    for pwd in passwords:
        if pwd:
            existing.add(pwd)

    with open(PASSWORD_MAP_FILE, "w") as f:
        json.dump(list(existing), f, indent=2)


def get_candidate_passwords():
    """Retrieve all candidate passwords from .env and cas_passwords.json."""
    candidates = set()

    for m in get_configured_mailboxes():
        if m.get("pdf_password"):
            candidates.add(m["pdf_password"])

    if os.getenv("PDF_PASSWORD"):
        candidates.add(os.getenv("PDF_PASSWORD"))
    if os.getenv("CAS_PDF_PASSWORD"):
        candidates.add(os.getenv("CAS_PDF_PASSWORD"))

    if os.path.exists(PASSWORD_MAP_FILE):
        try:
            with open(PASSWORD_MAP_FILE, "r") as f:
                saved = json.load(f)
                for s in saved:
                    candidates.add(s)
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_INPUT_DIR = os.path.join(BASE_DIR, "input")


def fetch_from_single_mailbox(mailbox_cfg, input_dir=None, since_date=None):
    if input_dir is None:
        input_dir = DEFAULT_INPUT_DIR
    user = mailbox_cfg["user"]
    app_pass = mailbox_cfg["app_password"]
    pdf_pass = mailbox_cfg.get("pdf_password")

    print(f"📧 Connecting to Mailbox ({user}) via IMAP...")
    if since_date:
        print(f"📅 Incremental sync for {user}: Searching SINCE {since_date}...")

    downloaded = []

    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(user, app_pass)
        mail.select("inbox")

        if since_date:
            search_queries = [
                f'(FROM "NSDL-CAS@nsdl.co.in" SINCE {since_date})',
                f'(SUBJECT "Your NSDL CAS" SINCE {since_date})',
                f'(SUBJECT "NSDL eCAS" SINCE {since_date})',
                f'(SUBJECT "Consolidated Account Statement" SINCE {since_date})',
            ]
        else:
            search_queries = [
                'FROM "NSDL-CAS@nsdl.co.in"',
                'SUBJECT "Your NSDL CAS"',
                'SUBJECT "NSDL eCAS"',
                'SUBJECT "Consolidated Account Statement"',
                'SUBJECT "CDSL eCAS"',
            ]

        all_msg_ids = set()
        for query in search_queries:
            status, data = mail.search(None, query)
            if status == "OK" and data[0]:
                ids = data[0].split()
                for i in ids:
                    all_msg_ids.add(i)

        if not all_msg_ids:
            print(f"ℹ️ No new eCAS emails in inbox for {user}.")
            mail.logout()
            return []

        print(f"Found {len(all_msg_ids)} eCAS email(s) for {user}. Extracting attachments...")

        for msg_id in sorted(list(all_msg_ids), key=lambda x: int(x)):
            status, data = mail.fetch(msg_id, "(RFC822)")
            if status != "OK":
                continue

            raw_email = data[0][1]
            msg = email.message_from_bytes(raw_email)

            for part in msg.walk():
                if part.get_content_maintype() == "multipart" or part.get("Content-Disposition") is None:
                    continue

                fn = clean_filename(part.get_filename())
                if fn and fn.upper().startswith("NSDLE-CAS_") and fn.upper().endswith(".PDF"):
                    filepath = os.path.join(input_dir, fn)

                    if not os.path.exists(filepath):
                        with open(filepath, "wb") as f:
                            f.write(part.get_payload(decode=True))
                        print(f"  📥 Saved: {fn} (from {user})")
                        downloaded.append(filepath)
                    else:
                        print(f"  ⚡ Already exists: {fn}")

        mail.logout()
    except Exception as e:
        print(f"⚠️ Error fetching from mailbox {user}: {e}")

    if pdf_pass:
        save_mapped_passwords([pdf_pass])

    return downloaded


def fetch_new_cas_from_gmail(input_dir="input", since_date=None):
    os.makedirs(input_dir, exist_ok=True)
    mailboxes = get_configured_mailboxes()

    if not mailboxes:
        print("ℹ️ Mailbox sync skipped: No mailboxes configured in .env")
        return []

    print(f"🌐 Synchronizing {len(mailboxes)} configured mailbox(es)...")
    all_downloaded = []

    for cfg in mailboxes:
        d = fetch_from_single_mailbox(cfg, input_dir=input_dir, since_date=since_date)
        all_downloaded.extend(d)

    return all_downloaded


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch eCAS PDFs from multiple Gmail mailboxes.")
    parser.add_argument("--since", help="Incremental search start date (e.g. 01-Jul-2026)")
    args = parser.parse_args()

    fetch_new_cas_from_gmail(since_date=args.since)
