import os
import random
from pathlib import Path
from dotenv import load_dotenv
from instagrapi import Client
from instagrapi.exceptions import LoginRequired
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.fx.crop import crop
from moviepy.video.fx.resize import resize
import time
from moviepy.video.fx.colorx import colorx
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout
from moviepy.video.fx.colorx import colorx
from moviepy.video.fx.fadein import fadein
from moviepy.video.fx.fadeout import fadeout
from moviepy.video.compositing.CompositeVideoClip import CompositeVideoClip
from moviepy.video.VideoClip import ColorClip

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
    descriptions = [
        "At Baleal, we believe fashion should empower, not restrict. Inspired by the freedom of the ocean and the spirit of adventure, we're here to revolutionize women’s clothing. No more compromising between style and practicality—our designs come with pockets that actually fit your essentials! 🌊👖 Follow us to join the #PocketRevolution and experience a new kind of freedom in fashion.",
        "Tired of clothes that look great but lack functionality? So were we. Baleal was born to bring real, practical pockets to women’s clothing without sacrificing style. Every detail is designed to fit seamlessly into your life, from the beach to the city. Follow us to stay updated on our journey to redefine women’s fashion!",
        "Imagine clothing that’s as practical as it is beautiful. At Baleal, we’re making it a reality. Inspired by adventure and crafted with care, our pieces give you style without sacrificing functionality. Join us and discover the joy of fashion that fits your life! Follow for more updates!",
        "Why choose between beauty and utility? With Baleal, you don’t have to. We’re on a mission to create stylish, high-quality women’s clothing that empowers, not restricts. Inspired by our travels and designed for the everyday, our pieces are made for real women who need real pockets. Follow us and join the movement!",
        "Fashion should work as hard as you do. That’s why Baleal is here to bring you beautiful clothing with the functionality you’ve always wanted. Inspired by the waves of Portugal and made for women everywhere, our designs combine style with practical pockets that fit your needs. Follow us to be part of our journey!",
        "More than just clothes—Baleal is a movement towards practical, stylish fashion for women. From the beaches of Portugal to the streets of your city, we’re here to make a change, one pocket at a time. Follow us and stay tuned as we redefine what it means to dress with purpose!",
        "Say goodbye to tiny pockets and hello to functional fashion! Baleal is here to make sure your essentials have a place in your wardrobe. Designed for the adventurous and inspired by the ocean, our pieces blend beauty with practicality. Follow us to see how we’re transforming women’s fashion!",
        "Baleal isn’t just a clothing brand; it’s a new perspective on women’s fashion. Our mission is simple: bring you stylish, functional clothing with pockets that actually work. Designed for women who live life to the fullest. Follow us to join the movement!",
        "From the beaches of Portugal to women around the world, Baleal is here to redefine women’s fashion. We’re bringing functional pockets and stylish designs to your wardrobe, giving you the freedom to carry what you need with ease. Follow us to stay updated on our journey to make fashion functional!",
        "Inspired by adventure and crafted for everyday life, Baleal brings you women’s clothing that’s both stylish and practical. No more sacrificing functionality for fashion. Follow us and join our mission to create a new kind of wardrobe—one that fits your life and your essentials!",
        "Redefine what your clothing can do for you with Baleal. Born from a need for better pockets and inspired by freedom, our pieces give you style and substance. Discover fashion that truly fits your lifestyle—follow us for updates on the #PocketRevolution.",
        "Why compromise on functionality for style? At Baleal, we’re on a mission to make clothing that looks great and works even better. Say goodbye to tiny pockets and hello to functional fashion. Follow us for updates on our journey to redefine women’s wardrobes!",
        "Baleal was born from a simple idea: women deserve clothes that work as hard as they do. Inspired by the ocean, crafted with purpose, our pieces blend style and functionality for real women. Follow us to be part of a movement that’s redefining fashion!",
        "It’s time to expect more from your wardrobe. Baleal is bringing you stylish women’s clothing with pockets that actually fit your life. No more compromises—follow us to see how we’re changing women’s fashion, one pocket at a time!",
        "At Baleal, we believe that pockets shouldn’t be an afterthought. Our designs prioritize functionality and style, giving you the best of both worlds. Follow us for updates on our journey to create fashion that supports, empowers, and inspires!",
        "Not just fashion—Baleal is a movement. We’re here to bring you clothing with real pockets, real style, and real function. Follow us to join a new era in women’s fashion, where you don’t have to choose between beauty and practicality.",
        "From beachside inspiration to everyday fashion, Baleal is here to create clothing that empowers. Our mission is simple: beautiful clothing with functional pockets. Follow us to be part of our journey and see how we’re transforming women’s fashion!",
        "Inspired by adventure and made with purpose, Baleal brings you clothing that doesn’t compromise. Our designs fit your style and your essentials, giving you freedom without sacrificing function. Follow us to see what’s next on our journey!",
        "Why settle for less when you can have more? Baleal is here to bring you functional, stylish clothing that works with your life. Join us as we redefine women’s fashion, one pocket at a time. Follow us for updates on our mission!",
        "Join the movement to bring function back to women’s fashion. Baleal is here to create stylish, functional clothing that keeps up with your life. Follow us to stay updated on how we’re transforming women’s wardrobes!"
    ]

    hashtags = [
        "#fashion", "#pants", "#women", "#outfit", "#baleal"
    ]

    return f"{random.choice(descriptions)}\n\nCredits: @{creator_username}\n\n{' '.join(hashtags)}"


def post_url(url: str):
    """ URL is a link to a insta reel and post it to our channel """
    print(f"Getting info about of {url}")
    media_pk = cl.media_pk_from_url(url)
    media_info = cl.media_info(media_pk)
    creator_username = media_info.user.username
    print("downloading...")
    media_path = cl.video_download(int(media_pk), Path("./sessions"))
    caption = get_caption(creator_username)
    print(f"downloaded video {url}")
    time.sleep(5)
    # crop the video to modify the hash
    cropped_media_path = crop_video(str(media_path))
    print("cropped video done")

    # Upload to Instagram
    cl.video_upload(Path(cropped_media_path), caption=caption)
    print(f"Successfully uploaded: {url}")

    # Clean up downloaded media
    if os.path.exists(media_path):
        os.remove(media_path)
    if os.path.exists(cropped_media_path):
        os.remove(cropped_media_path)

    thumbnail_path = Path(str(media_path) + ".jpg")
    if os.path.exists(thumbnail_path):
        os.remove(thumbnail_path)
        print(f"Deleted thumbnail: {thumbnail_path}")


def crop_video(media_path: str) -> str:
    """
    Apply a filter to a video.

    Args:
        media_path (str): Path to the input video.

    Returns:
        str: Path to the filtered video.
    """
    output_path = Path(media_path).with_name("filtered_" + Path(media_path).name)
    with VideoFileClip(media_path) as clip:
        # Example: Adjust color intensity (e.g., make it more vibrant)
        filtered_clip = colorx(clip, 1.1)  # Increase brightness/colors

        # Example: Add a semi-transparent overlay for a tint effect
        #overlay = ColorClip(clip.size, color=(128, 0, 128), duration=clip.duration).set_opacity(0.2)
        #final_clip = CompositeVideoClip([filtered_clip, overlay])

        # Optional: Add fade-in/out effects
        #final_clip = fadein(final_clip, duration=1)

        # Write the output file
        filtered_clip.write_videofile(str(output_path), codec="libx264", audio_codec="aac")

    return str(output_path)


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
