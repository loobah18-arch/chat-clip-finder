#!/usr/bin/env python3
"""Read-only check that the YouTube OAuth secrets can still mint an access token.

Exchanges CLIENT_ID / CLIENT_SECRET / REFRESH_TOKEN for an access token, reports
the granted scopes, and asks the Data API who the channel is. It never uploads,
never writes and never prints a secret - only whether the exchange worked.

Exit codes: 0 = usable, 1 = secrets missing, 2 = Google rejected the refresh
token (expired / revoked / wrong client), 3 = token minted but lacks upload scope.
"""

import os
import sys

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def _creds():
    cid = os.environ.get("CLIENT_ID") or os.environ.get("YOUTUBE_CLIENT_ID")
    secret = os.environ.get("CLIENT_SECRET") or os.environ.get("YOUTUBE_CLIENT_SECRET")
    refresh = os.environ.get("REFRESH_TOKEN") or os.environ.get("YOUTUBE_REFRESH_TOKEN")
    return cid, secret, refresh


def main() -> int:
    cid, secret, refresh = _creds()
    missing = [n for n, v in (("CLIENT_ID", cid), ("CLIENT_SECRET", secret), ("REFRESH_TOKEN", refresh)) if not v]
    if missing:
        print(f"::error::Missing secret(s): {', '.join(missing)}")
        return 1

    resp = requests.post(
        TOKEN_URL,
        data={"client_id": cid, "client_secret": secret, "refresh_token": refresh,
              "grant_type": "refresh_token"},
        timeout=20,
    )
    if resp.status_code != 200:
        body = {}
        try:
            body = resp.json()
        except ValueError:
            body = {"raw": resp.text[:300]}
        error = body.get("error", "unknown_error")
        description = body.get("error_description") or body.get("raw", "")
        print(f"::error::Refresh token rejected ({resp.status_code} {error}): {description}")
        if error == "invalid_grant":
            print("The refresh token is expired or revoked. Google expires refresh tokens after 7 days "
                  "while the OAuth consent screen is in 'Testing'; publish the app (or re-consent) and "
                  "store a fresh token with get_yt_token.py.")
        return 2

    payload = resp.json()
    access_token = payload["access_token"]
    print(f"✅ Access token minted (expires in {payload.get('expires_in')}s, "
          f"scope: {payload.get('scope', 'not reported')})")

    info = requests.get(TOKENINFO_URL, params={"access_token": access_token}, timeout=20)
    granted = info.json().get("scope", "") if info.status_code == 200 else payload.get("scope", "")
    scopes = granted.split()
    has_upload = UPLOAD_SCOPE in scopes or "https://www.googleapis.com/auth/youtube" in scopes
    print(f"Granted scopes: {' '.join(scopes) or '(none reported)'}")

    channel = requests.get(CHANNELS_URL, params={"part": "snippet", "mine": "true"},
                           headers={"Authorization": f"Bearer {access_token}"}, timeout=20)
    if channel.status_code == 200:
        items = channel.json().get("items") or []
        if items:
            snippet = items[0].get("snippet", {})
            print(f"Channel: {snippet.get('title')} ({items[0].get('id')})")
        else:
            print("⚠️ Token works but no channel is attached to it.")
    else:
        print(f"⚠️ channels.list returned {channel.status_code}: {channel.text[:200]}")

    if not has_upload:
        print("::error::Token works but does not carry the youtube.upload scope; uploads will fail.")
        return 3
    print("✅ Upload scope present - uploads can proceed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
