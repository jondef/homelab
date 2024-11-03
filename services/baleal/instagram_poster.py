import os
from pathlib import Path
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired

load_dotenv()
USERNAME = os.getenv("INSTAGRAM_USERNAME")
PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
verification_code = os.getenv("INSTAGRAM_2FA_CODE")

# WARNING: MAKE SURE DOCKER USER HAS PERMISSIONS ON THIS FOLDER
URL_FILE = "./sessions/waiting_posts.txt"
POSTED_FILE = "./sessions/posted_urls.txt"

cl = Client()
cl.delay_range = [1, 3]  # adds a random delay between 1 and 3 seconds after each request to mimic user


def login_user(session_path: str = "./sessions/instagram_session.json"):
    """
    Attempts to login to Instagram using either the provided session information
    or the provided username and password.
    """
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
                cl.dump_settings(session_path)
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


login_user()


def get_caption(creator_username: str):
    return f"Check out this amazing post!\n\nCredits: @{creator_username}"


def post_url(url: str):
    """ URL is a link to a insta reel and post it to our channel """
    media_pk = cl.media_pk_from_url(url)
    media_info = cl.media_info(media_pk)
    creator_username = media_info.user.username
    media_path = cl.video_download(media_pk, "./sessions")
    caption = get_caption(creator_username)

    # Upload to Instagram
    cl.video_upload(media_path, caption=caption)
    print(f"Successfully posted: {url}")


    # Clean up downloaded media
    if os.path.exists(media_path):
        os.remove(media_path)

    thumbnail_path = Path(str(media_path) + ".jpg")
    if os.path.exists(thumbnail_path):
        os.remove(thumbnail_path)
        print(f"Deleted thumbnail: {thumbnail_path}")


def get_oldest_link_from_waiting_list(filename: str = URL_FILE):
    # Read the links from the file
    with open(filename, 'r') as file:
        links = [line.strip() for line in file.readlines() if line.strip()]

    # Pop the first item from the inverted list
    if links:
        popped_link = links.pop(0)
    else:
        return None  # Return None if the list is empty

    # Write the remaining links back to the file
    with open(filename, 'w') as file:
        for link in links:  # Re-reverse to maintain original order except for the removed item
            file.write(link + '\n')

    return popped_link


def save_posted_link(link):
    if link is None:
        return
    # Open the file in append mode and write the link to it
    with open(POSTED_FILE, 'a+') as file:
        file.write(link + '\n')


def add_back_to_waiting_list(link: str):
    # This function appends the failed link back to waiting_url.txt
    with open(URL_FILE, 'a+') as file:
        file.write(link + '\n')
