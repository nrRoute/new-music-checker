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
        artist_name: str,
        spotify_url: str,
        release_date: str,
        release_type: str = None,
    ):
        self.id = id
        self.artist_name = artist_name
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

def save_releases_to_file(releases: list[Release]):
    releases_record = []
    for release in releases:
        releases_record.append({
            'id': release.id,
            'artist_name': release.artist_name,
            'spotify_url': release.spotify_url,
            'release_date': release.release_date,
            'release_type': release.release_type
        })
    with open('releases.json', 'w') as file:
        json.dump(releases_record, file)
    logging.info("Releases saved to releases.json")

def add_new_releases_to_file(releases: list[Release]):
    releases_record = load_releases_from_file()
    for release in releases:
        releases_record.append(release)
    save_releases_to_file(releases_record)

def load_releases_from_file() -> list[Release]:
    if not os.path.exists('releases.json'):
        logging.info("No releases.json file found.")
        return []

    with open('releases.json', 'r') as file:
        releases_record = json.load(file)

    releases = []
    for record in releases_record:
        releases.append(Release(
            id=record['id'],
            artist_name=record['artist_name'],
            spotify_url=record['spotify_url'],
            release_date=record['release_date'],
            release_type=record['release_type']
        ))
    return releases

def contains_release(releases_record: list[Release], release: Release) -> bool:
    for record in releases_record:
        if record.id == release.id:
            return True
    return False

def check_if_new_release(releases_record: list[Release], release: Release) -> bool:
    return not contains_release(releases_record, release)

def get_following_artists_new_releases(sp: spotipy.Spotify) -> list:
    artists = get_following_artists(sp)
    if not artists:
        return []
    new_releases = []
    for artist in artists:
        latest_releases = sp.artist_albums(artist.id, include_groups='album,single,appears_on', limit=5)
        if not latest_releases['items']:
            continue

        for album in latest_releases['items']:
            today = datetime.date.today().strftime('%Y-%m-%d')
            release_date = album['release_date']
            if release_date >= today:
                release = Release(
                    id=album['id'],
                    artist_name=artist.name,
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
            "content": f"New release from {release.artist_name}: {release.release_date} - {release.spotify_url}"
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

    spotify_releases = get_following_artists_new_releases(sp)

    if not spotify_releases:
        logging.info("No recent releases found.")
        return

    releases_record = load_releases_from_file()
    new_releases = []
    for release in spotify_releases:
        if not check_if_new_release(releases_record=releases_record, release=release):
            continue
        new_releases.append(release)

    logging.info(f"Found {len(new_releases)} new releases.")
    send_message_to_discord(new_releases)
    add_new_releases_to_file(new_releases)


if __name__ == "__main__":
    load_dotenv()
    main()
