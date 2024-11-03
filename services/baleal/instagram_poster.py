import asyncio
import os
import time
from pathlib import Path
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

load_dotenv()
USERNAME = os.getenv("INSTAGRAM_USERNAME")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
verification_code = os.getenv("INSTAGRAM_2FA_CODE")


cl = Client()
cl.delay_range = [1, 3]  # adds a random delay between 1 and 3 seconds after each request to mimic user

# Define your global variable to track posted URLs
posted_urls = set()


def login_user(session_path: str = "./sessions/instagram_session.json"):
    """
    Attempts to login to Instagram using either the provided session information
    or the provided username and password.
    """
    cl = Client()
    session = cl.load_settings(session_path)

    login_via_session = False
    login_via_pw = False

    if session:
        try:
            cl.set_settings(session)
            cl.login(USERNAME, PASSWORD)  # this doesn't actually login using username/password but uses the session

            # check if session is valid
            try:
                cl.get_timeline_feed()  # check session
            except LoginRequired:
                print("Session is invalid, need to login via username and password")

                old_session = cl.get_settings()

                # use the same device uuids across logins
                cl.set_settings({})
                cl.set_uuids(old_session["uuids"])

                cl.login(USERNAME, PASSWORD)
            login_via_session = True
        except Exception as e:
            print(f"Couldn't login user using session information: {e}")

    if not login_via_session:
        try:
            print(f"Attempting to login via username and password. username: {USERNAME}")
            if cl.login(USERNAME, PASSWORD):
                login_via_pw = True
        except Exception as e:
            print(f"Couldn't login user using username and password: {e}")

    if not login_via_pw and not login_via_session:
        raise Exception("Couldn't login user with either password or session")


# Function to retrieve URLs not yet posted
def get_unposted_urls():
    if not os.path.exists("urls_collection.txt"):
        return []

    # Read all collected URLs
    with open("urls_collection.txt", "r") as file:
        collected_urls = set(line.strip() for line in file)

    # Read posted URLs
    if os.path.exists("urls_posted.txt"):
        with open("urls_posted.txt", "r") as posted_file:
            posted_urls = set(line.strip() for line in posted_file)
    else:
        posted_urls = set()

    # Filter out URLs that have already been posted
    unposted_urls = list(collected_urls - posted_urls)
    return unposted_urls


# Function to post a single URL
async def post_url(url):
    try:
        media_pk = cl.media_pk_from_url(url)
        media_info = cl.media_info(media_pk)
        creator_username = media_info.user.username
        media_path = cl.video_download(media_pk)
        caption = f"Check out this amazing post!\n\nCredits: @{creator_username}"

        # Upload to Instagram
        cl.video_upload(media_path, caption=caption)
        print(f"Successfully posted: {url}")

        # Record the URL as posted
        with open("urls_posted.txt", "a") as posted_file:
            posted_file.write(url + "\n")

        # Clean up downloaded media
        if os.path.exists(media_path):
            os.remove(media_path)

        # Clean up thumbnail files
        # Using pathlib for path manipulation
        media_file = Path(media_path)
        thumbnail_path = media_file.with_suffix('.jpg')  # Change the extension to .jpg

        if thumbnail_path.exists():
            os.remove(thumbnail_path)
            print(f"Deleted thumbnail: {thumbnail_path}")

    except Exception as e:
        print(f"Failed to post URL {url}: {e}")


# Main function to post one URL
async def post_one_url():
    unposted_urls = get_unposted_urls()

    if unposted_urls:  # Check if there are any unposted URLs
        await post_url(unposted_urls[0])  # Post the first unposted URL


def schedule_posting():
    while True:
        current_hour = time.localtime().tm_hour

        # Define posting hour
        if current_hour in [9, 15, 18]:
            unposted_urls = get_unposted_urls()  # Get unposted URLs before posting
            if unposted_urls:  # Check if there are any unposted URLs
                # Filter unposted URLs to exclude already posted ones
                for url in unposted_urls:
                    if url not in posted_urls:
                        asyncio.run(post_url(url))  # Post the first unposted URL
                        posted_urls.add(url)  # Mark this URL as posted
                        print(f"Posted URL: {url} at hour: {current_hour}")
                        break  # Exit loop after posting one URL
                else:
                    print("No unposted URLs available.")
            else:
                print("No unposted URLs available.")
            time.sleep(3600)  # Wait for an hour before checking again
        else:
            time.sleep(1800)  # Check every 30 minutes if it's time to post


if __name__ == "__main__":
    print("Starting instagram poster...")
    #schedule_posting()
