import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests

import json
import logging
import os
import datetime
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("new_music_checker.log"),
        logging.StreamHandler()
    ]
)

class Artist:
    def __init__(
        self,
        id: str,
        name: str,
        spotify_url: str,
    ):
        self.id = id
        self.name = name
        self.spotify_url = spotify_url

    def __repr__(self):
        return f"{self.name} ({self.spotify_url})"

class Release:
    def __init__(self,
        id: str,
        spotify_url: str,
        release_date: str,
        release_type: str = None,
    ):
        self.id = id
        self.spotify_url = spotify_url
        self.release_date = release_date
        self.release_type = release_type

    def __repr__(self):
        return f"{self.release_date} ({self.spotify_url})"

def get_spotify_client() -> spotipy.Spotify:
    scope = "user-follow-read"
    auth_manager = SpotifyOAuth(
        scope=scope,
    )
    sp = spotipy.Spotify(auth_manager=auth_manager)
    return sp

def get_following_artists(sp: spotipy.Spotify) -> list[Artist]:
    results = sp.current_user_followed_artists(limit=50)
    artists = []
    for artist in results['artists']['items']:
        artists.append(Artist(artist['id'], artist['name'], artist['external_urls']['spotify']))
    return artists

def get_following_artists_new_releases(sp: spotipy.Spotify) -> list:
    artists = get_following_artists(sp)
    artist_ids = [artist.id for artist in artists]
    if not artist_ids:
        return []
    new_releases = []
    for artist_id in artist_ids:
        latest_releases = sp.artist_albums(artist_id, include_groups='album,single,appears_on', limit=5)
        if not latest_releases['items']:
            continue

        for album in latest_releases['items']:
            today = datetime.date.today().strftime('%Y-%m-%d')
            release_date = album['release_date']
            if release_date >= today:
                release = Release(
                    id=album['id'],
                    spotify_url=album['external_urls']['spotify'],
                    release_date=release_date,
                    release_type=album['album_type']
                )
                new_releases.append(release)
    return new_releases

def send_message_to_discord(releases: list[Release]):
    webhook_url = os.getenv('DISCORD_WEBHOOK_URL')
    if not webhook_url:
        logging.error("Discord webhook URL not set.")
        return

    push_message_to_discord(webhook_url, releases)

def push_message_to_discord(webhook_url: str, releases: list[Release]):
    headers = {
        'Content-Type': 'application/json'
    }
    for release in releases:
        data = {
            "content": f"New release: {release.release_date} - {release.spotify_url}"
        }
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data))
        if response.status_code != 204:
            logging.error(f"Failed to send message to Discord: {response.status_code} - {response.text}")
        else:
            logging.info(f"Message sent to Discord: {release.release_date} - {release.spotify_url}")

def main():
    sp = get_spotify_client()
    artists = get_following_artists(sp)

    if not artists:
        logging.info("No followed artists found.")
        return

    spotify_new_releases = get_following_artists_new_releases(sp)

    if not spotify_new_releases:
        logging.info("No new releases found.")
        return

    logging.info(f"Found {len(spotify_new_releases)} new releases.")
    send_message_to_discord(spotify_new_releases)


if __name__ == "__main__":
    load_dotenv()
    main()
