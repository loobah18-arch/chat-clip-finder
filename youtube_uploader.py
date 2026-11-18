#!/usr/bin/env python3
"""
YouTube Shorts Auto-Uploader for Chat Clip Finder.
Uploads 9:16 vertical clips directly to YouTube channel via Data API v3.
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
import requests

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube"]


def get_access_token():
    """Exchange OAuth credentials for a fresh access token."""
    creds_file = os.path.expanduser("~/.youtube_credentials.json")
    client_id = os.environ.get("CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET")
    refresh_token = os.environ.get("REFRESH_TOKEN")

    if not (client_id and client_secret and refresh_token) and os.path.exists(creds_file):
        try:
            with open(creds_file, "r") as f:
                d = json.load(f)
            client_id = client_id or d.get("client_id")
            client_secret = client_secret or d.get("client_secret")
            refresh_token = refresh_token or d.get("refresh_token")
        except Exception:
            pass

    if not (client_id and client_secret and refresh_token):
        raise RuntimeError("Missing YouTube credentials: set CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN")

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed to refresh access token ({resp.status_code}): {resp.text}")

    return resp.json()["access_token"]


def upload_short(video_path: Path, title: str, description: str = "", tags: list = None, privacy: str = "public"):
    """Resumable upload of a video to YouTube Shorts."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2.credentials import Credentials

    access_token = get_access_token()
    creds = Credentials(token=access_token)
    youtube = build("youtube", "v3", credentials=creds)

    clean_title = title.strip()
    if "#shorts" not in clean_title.lower():
        clean_title = f"{clean_title[:85]} #Shorts"

    tags = tags or ["shorts", "gaming", "streamer", "twitch"]

    body = {
        "snippet": {
            "title": clean_title,
            "description": description or f"{clean_title}\n\n#Shorts #Gaming #TwitchHighlights",
            "tags": [t.replace("#", "") for t in tags],
            "categoryId": "20",  # Gaming
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"🚀 Uploading '{clean_title}' to YouTube...")
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            print(f"   ↳ Upload progress: {int(status.progress() * 100)}%")

    video_id = resp.get("id")
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"✅ Published successfully: {video_url}")
    return video_url


def main():
    parser = argparse.ArgumentParser(description="Upload video to YouTube Shorts")
    parser.add_argument("video", help="Path to video file (.mp4)")
    parser.add_argument("--title", required=True, help="Video title")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", default="shorts,twitch,highlights,gaming", help="Comma-separated tags")
    parser.add_argument("--privacy", default="public", choices=["public", "unlisted", "private"])

    args = parser.parse_args()
    video_path = Path(args.video)
    if not video_path.exists():
        print(f"Error: file not found: {video_path}", file=sys.stderr)
        sys.exit(1)

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    upload_short(video_path, args.title, args.description, tags, args.privacy)


if __name__ == "__main__":
    main()
