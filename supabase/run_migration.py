"""
Run the initial schema migration against the remote Supabase project.

Usage:
  SUPABASE_ACCESS_TOKEN=<your_token> python supabase/run_migration.py

Get your personal access token from:
  https://supabase.com/dashboard/account/tokens
"""
import os
import sys
import pathlib
import urllib.request
import urllib.error
import json

PROJECT_REF = "acngivwdqttgtalopsjw"
MIGRATION_FILE = pathlib.Path(__file__).parent / "migrations" / "20260511000000_initial_schema.sql"
API_URL = f"https://api.supabase.com/v1/projects/{PROJECT_REF}/database/query"

token = os.environ.get("SUPABASE_ACCESS_TOKEN")
if not token:
    print("ERROR: Set SUPABASE_ACCESS_TOKEN environment variable.")
    print("  Get your token at: https://supabase.com/dashboard/account/tokens")
    sys.exit(1)

sql = MIGRATION_FILE.read_text()
payload = json.dumps({"query": sql}).encode()
req = urllib.request.Request(
    API_URL,
    data=payload,
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(req) as resp:
        body = resp.read()
        print("Migration applied successfully.")
        print(body.decode())
except urllib.error.HTTPError as e:
    body = e.read().decode()
    print(f"ERROR {e.code}: {body}")
    sys.exit(1)
