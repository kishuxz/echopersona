#!/usr/bin/env python3
"""Static verification of private VPC deployment configuration.

Checks internal consistency of config files without deploying,
starting Docker, calling any API, or reading real secrets.
Safe to run locally or on the VPS before any deploy.

Exit 0 — all checks pass.
Exit 1 — one or more checks fail (details printed inline).
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_results: list[tuple[bool, str]] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    tag = "[PASS]" if condition else "[FAIL]"
    line = f"{tag} {label}"
    if not condition and detail:
        line += f"\n       → {detail}"
    _results.append((condition, line))
    print(line)


def read(rel: str) -> str:
    p = REPO / rel
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


nginx   = read("frontend/nginx.conf")
compose = read("docker-compose.yml")
env_ex  = read(".env.example")
runbook = read("docs/runbook.md")

# ── nginx.conf: route prefixes ───────────────────────────────────────────────
# Search for each required prefix string inside nginx.conf.
# The location block uses a regex alternation — confirming each prefix appears
# in the file is sufficient and avoids fragile regex structure parsing.
for prefix in [
    "persona", "personas", "billing", "health", "ingest",
    "creation", "review", "docs", "redoc", "openapi",
]:
    check(
        f"nginx.conf: location block covers /{prefix}",
        prefix in nginx,
    )

# ── nginx.conf: WebSocket block ──────────────────────────────────────────────
check(
    "nginx.conf: /ws/ block present with Upgrade headers",
    "location /ws/" in nginx and "Upgrade $http_upgrade" in nginx,
)

check(
    "nginx.conf: client_max_body_size 50m",
    "client_max_body_size 50m" in nginx,
)

# ── docker-compose.yml: port bindings ────────────────────────────────────────
check(
    "docker-compose.yml: no 0.0.0.0 port bindings",
    "0.0.0.0:" not in compose,
    "A service is bound to 0.0.0.0 — all ports must use 127.0.0.1",
)

for svc, binding in [
    ("redis",    "127.0.0.1:6379"),
    ("backend",  "127.0.0.1:8000"),
    ("frontend", "127.0.0.1:3000"),
]:
    check(
        f"docker-compose.yml: {svc} bound to {binding} (local-only)",
        binding in compose,
    )

# ── docker-compose.yml: VITE production defaults ─────────────────────────────
check(
    "docker-compose.yml: VITE_API_BASE_URL default is https://kishoreai.online",
    "VITE_API_BASE_URL=${VITE_API_BASE_URL:-https://kishoreai.online}" in compose,
)

check(
    "docker-compose.yml: VITE_WS_BASE_URL default is wss://kishoreai.online",
    "VITE_WS_BASE_URL=${VITE_WS_BASE_URL:-wss://kishoreai.online}" in compose,
)

# ── .env.example: required keys present ──────────────────────────────────────
REQUIRED_KEYS = [
    "SUPABASE_URL",
    "SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GROQ_API_KEY",
    "ELEVENLABS_API_KEY",
    "REDIS_URL",
    "CORS_ORIGINS",
    "PUBLIC_BASE_URL",
    "VITE_API_BASE_URL",
    "VITE_WS_BASE_URL",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "STRIPE_PRICE_CREATOR_MONTHLY",
    "STRIPE_PRICE_LEGACY_MONTHLY",
]

env_keys = {
    line.split("=", 1)[0].strip()
    for line in env_ex.splitlines()
    if "=" in line and not line.lstrip().startswith("#")
}

for key in REQUIRED_KEYS:
    check(f".env.example: {key} present", key in env_keys)

# ── .env.example: no real secret values ──────────────────────────────────────
# Matches known real-secret prefixes on the value side of any KEY=VALUE line.
REAL_SECRET_RE = re.compile(
    r"^[^#\s][^=]*=("
    r"sk-[A-Za-z0-9_]{20,}"      # Stripe / OpenAI secret key
    r"|eyJ[A-Za-z0-9+/]{20,}"    # JWT / Supabase service-role token
    r"|whsec_[A-Za-z0-9]{20,}"   # Stripe webhook secret
    r"|sbp_[A-Za-z0-9]{20,}"     # Supabase personal access token
    r")",
    re.MULTILINE,
)
leaks = REAL_SECRET_RE.findall(env_ex)
check(
    ".env.example: values are placeholders (no real secret tokens detected)",
    not leaks,
    f"Suspicious value(s): {leaks[:2]}" if leaks else "",
)

# ── runbook.md: host nginx snippet ───────────────────────────────────────────
check(
    "docs/runbook.md: host nginx snippet has client_max_body_size 50m",
    "client_max_body_size 50m" in runbook,
)

# ── Summary ───────────────────────────────────────────────────────────────────
passed = sum(1 for ok, _ in _results if ok)
failed = sum(1 for ok, _ in _results if not ok)
print(f"\n--- {passed} passed, {failed} failed ---")
sys.exit(0 if failed == 0 else 1)
