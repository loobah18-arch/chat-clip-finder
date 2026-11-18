#!/usr/bin/env python3
"""
YouTube OAuth Refresh Token Generator for Termux / Cloud Automation.

Usage:
  python3 get_yt_token.py --client-id YOUR_ID --client-secret YOUR_SECRET
"""

import argparse
import http.server
import socketserver
import urllib.parse
import webbrowser
import requests

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]

PORT = 8080
REDIRECT_URI = f"http://localhost:{PORT}/"


def main():
    parser = argparse.ArgumentParser(description="Generate YouTube OAuth Refresh Token")
    parser.add_argument("--client-id", help="Google Cloud OAuth Client ID")
    parser.add_argument("--client-secret", help="Google Cloud OAuth Client Secret")
    args = parser.parse_args()

    client_id = args.client_id or input("Enter Client ID: ").strip()
    client_secret = args.client_secret or input("Enter Client Secret: ").strip()

    if not client_id or not client_secret:
        print("Both Client ID and Client Secret are required.")
        return

    auth_params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(auth_params)

    auth_code = None

    class OAuthHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal auth_code
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if "code" in query:
                auth_code = query["code"][0]
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h1>Authorization successful!</h1><p>You can close this tab and return to Termux.</p>")
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"<h1>Authorization failed</h1>")

        def log_message(self, format, *args):
            pass

    print("\n1. Open this link in your browser to sign in to your YouTube channel:\n")
    print(auth_url)
    print("\nWaiting for browser callback on http://localhost:8080/ ...\n")

    with socketserver.TCPServer(("", PORT), OAuthHandler) as httpd:
        httpd.handle_request()

    if not auth_code:
        print("Failed to capture authorization code.")
        return

    # Exchange code for tokens
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        },
        timeout=15,
    )

    if resp.status_code == 200:
        data = resp.json()
        refresh_token = data.get("refresh_token")
        print("\n✅ OAuth Success! Add these to your repo/workflow secrets:\n")
        print(f"CLIENT_ID={client_id}")
        print(f"CLIENT_SECRET={client_secret}")
        print(f"REFRESH_TOKEN={refresh_token}")
    else:
        print(f"\n❌ Error exchanging code: {resp.status_code} - {resp.text}")


if __name__ == "__main__":
    main()
