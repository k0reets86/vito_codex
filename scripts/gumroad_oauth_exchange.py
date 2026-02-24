#!/usr/bin/env python3
"""Gumroad OAuth helper.

Usage:
  1) Ensure GUMROAD_APP_ID and GUMROAD_APP_SECRET are set in .env
  2) Run: python3 scripts/gumroad_oauth_exchange.py --print-url
  3) Open the URL, authorize, copy the `code` param from redirect URL
  4) Run: python3 scripts/gumroad_oauth_exchange.py --code <CODE>
  5) Token will be printed and optionally saved to .env
"""
import argparse
import os
from pathlib import Path
import re
import sys
import requests

AUTHORIZE_URL = "https://gumroad.com/oauth/authorize"
TOKEN_URL = "https://gumroad.com/oauth/token"

ENV_PATH = Path("/home/vito/vito-agent/.env")


def load_env():
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)


def save_env(key: str, value: str):
    text = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    if re.search(rf"^{key}=.*$", text, flags=re.M):
        text = re.sub(rf"^{key}=.*$", f"{key}={value}", text, flags=re.M)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += f"{key}={value}\n"
    ENV_PATH.write_text(text)


def main():
    load_env()
    app_id = os.getenv("GUMROAD_APP_ID", "").strip()
    app_secret = os.getenv("GUMROAD_APP_SECRET", "").strip()

    parser = argparse.ArgumentParser()
    parser.add_argument("--print-url", action="store_true", help="Print OAuth authorization URL")
    parser.add_argument("--code", help="Authorization code from redirect")
    parser.add_argument("--redirect-uri", default="urn:ietf:wg:oauth:2.0:oob", help="Redirect URI used in app settings")
    parser.add_argument("--save", action="store_true", help="Save token to .env as GUMROAD_OAUTH_TOKEN")
    args = parser.parse_args()

    if not app_id or not app_secret:
        print("Missing GUMROAD_APP_ID or GUMROAD_APP_SECRET in .env", file=sys.stderr)
        sys.exit(1)

    if args.print_url:
        url = f"{AUTHORIZE_URL}?client_id={app_id}&redirect_uri={args.redirect_uri}&response_type=code"
        print(url)
        return

    if not args.code:
        print("Provide --code or use --print-url", file=sys.stderr)
        sys.exit(1)

    data = {
        "client_id": app_id,
        "client_secret": app_secret,
        "code": args.code,
        "redirect_uri": args.redirect_uri,
        "grant_type": "authorization_code",
    }
    resp = requests.post(TOKEN_URL, data=data, timeout=20)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code}: {resp.text}")
        sys.exit(2)
    payload = resp.json()
    token = payload.get("access_token") or payload.get("access_token", "")
    if not token:
        print(f"Unexpected response: {payload}")
        sys.exit(3)
    print(token)
    if args.save:
        save_env("GUMROAD_OAUTH_TOKEN", token)
        print("Saved to .env")


if __name__ == "__main__":
    main()
