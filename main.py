import spotipy
from spotipy.oauth2 import SpotifyOAuth
import requests

import json
import logging
import os
import time
import datetime
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("new_music_checker.log"), logging.StreamHandler()],
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
    def __init__(
        self,
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
    sp = spotipy.Spotify(auth_manager=auth_manager, requests_timeout=10)
    return sp


def create_artist_from_data(artist_data: dict) -> Artist:
    return Artist(
        id=artist_data["id"],
        name=artist_data["name"],
        spotify_url=artist_data["external_urls"]["spotify"],
    )


def create_release_from_data(release_data: dict, artist_name: str) -> Release:
    return Release(
        id=release_data["id"],
        artist_name=artist_name,
        spotify_url=release_data["external_urls"]["spotify"],
        release_date=release_data["release_date"],
        release_type=release_data["album_type"],
    )


def get_following_artists(sp: spotipy.Spotify) -> list[Artist]:
    followed_artists_data = fetch_all_followed_artists(sp)
    return [create_artist_from_data(artist) for artist in followed_artists_data]


def fetch_all_followed_artists(sp: spotipy.Spotify) -> list[dict]:
    results = sp.current_user_followed_artists(limit=50)
    all_artists = results["artists"]["items"]
    next_page = results["artists"]["next"]

    retry_count = 0
    MAX_RETRIES = 5

    while retry_count < MAX_RETRIES and next_page:
        try:
            results = sp.next(results["artists"])
            next_page = results["artists"]["next"]
            all_artists.extend(results["artists"]["items"])
        except requests.exceptions.ConnectionError as e:
            logging.error(f"Connection error: {e}")
            retry_count += 1
            time.sleep(1)
            if retry_count >= MAX_RETRIES:
                logging.error("Max retries reached. Exiting.")
                break

    return all_artists


def save_releases_to_file(releases: list[Release]):
    releases_record = []
    for release in releases:
        releases_record.append(
            {
                "id": release.id,
                "artist_name": release.artist_name,
                "spotify_url": release.spotify_url,
                "release_date": release.release_date,
                "release_type": release.release_type,
            }
        )
    with open("releases.json", "w") as file:
        json.dump(releases_record, file)
    logging.info("Releases saved to releases.json")


def add_new_releases_to_file(releases: list[Release]):
    releases_record = load_releases_from_file()
    for release in releases:
        releases_record.append(release)
    save_releases_to_file(releases_record)


def load_releases_from_file() -> list[Release]:
    if not os.path.exists("releases.json"):
        logging.info("No releases.json file found.")
        return []

    with open("releases.json", "r") as file:
        releases_record = json.load(file)

    releases = []
    for record in releases_record:
        releases.append(
            Release(
                id=record["id"],
                artist_name=record["artist_name"],
                spotify_url=record["spotify_url"],
                release_date=record["release_date"],
                release_type=record["release_type"],
            )
        )
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
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    for artist in artists:
        latest_releases = {
            "items": []
        }
        for group in ["album", "single", "appears_on", "compilation"]:
            try:
                latest_items = sp.artist_albums(
                    artist.id, include_groups=group, limit=5
                )
            except requests.exceptions.ConnectionError as e:
                logging.error(f"Error fetching {group}s for {artist.name}: {e}")
                continue
            except requests.exceptions.ReadTimeout as e:
                logging.error(f"Timeout error fetching {group}s for {artist.name}: {e}")
                continue
            if latest_items["items"]:
                latest_releases["items"].extend(latest_items["items"])
            time.sleep(1.5)  # Add a delay to avoid hitting rate limits

        if not latest_releases["items"]:
            continue

        for album in latest_releases["items"]:
            release_date = album["release_date"]
            if release_date >= yesterday:
                new_releases.append(
                    create_release_from_data(album, artist.name)
                )

    return new_releases


def send_message_to_discord(releases: list[Release]):
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        logging.error("Discord webhook URL not set.")
        return

    push_message_to_discord(webhook_url, releases)


def push_message_to_discord(webhook_url: str, releases: list[Release]):
    headers = {"Content-Type": "application/json"}
    for release in releases:
        data = {
            "content": f"New {release.release_date} from {release.artist_name}: {release.release_date} - {release.spotify_url}"
        }
        response = requests.post(webhook_url, headers=headers, data=json.dumps(data))
        if response.status_code != 204:
            logging.error(
                f"Failed to send message to Discord: {response.status_code} - {response.text}"
            )
        else:
            logging.info(
                f"Message sent to Discord: {release.release_date} - {release.spotify_url}"
            )


def main():
    sp = get_spotify_client()
    artists = get_following_artists(sp)

    if not artists:
        logging.info("No followed artists found.")
        return
    logging.info(f"Found {len(artists)} followed artists.")

    logging.info("Checking for new releases...")
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
