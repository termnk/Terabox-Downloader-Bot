from aria2p import API as Aria2API, Client as Aria2Client
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import logging
import math
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import FloodWait
from pymongo import MongoClient
import time
import uuid
import urllib.parse
from urllib.parse import urlparse
import requests
from flask import Flask, render_template
from threading import Thread
import os
from bs4 import BeautifulSoup
import aiohttp

load_dotenv('config.env', override=True)
logging.basicConfig(
    level=logging.INFO,  
    format="[%(asctime)s - %(name)s - %(levelname)s] %(message)s - %(filename)s:%(lineno)d"
)

logger = logging.getLogger(__name__)

logging.getLogger("pyrogram.session").setLevel(logging.ERROR)
logging.getLogger("pyrogram.connection").setLevel(logging.ERROR)
logging.getLogger("pyrogram.dispatcher").setLevel(logging.ERROR)

aria2 = Aria2API(
    Aria2Client(
        host="http://localhost",
        port=6800,
        secret=""
    )
)
options = {
    "max-tries": "50",
    "retry-wait": "3",
    "continue": "true",
    "allow-overwrite": "true",
    "min-split-size": "4M",
    "split": "10"
}

aria2.set_global_options(options)

API_ID = os.environ.get('TELEGRAM_API', '')
if len(API_ID) == 0:
    logging.error("TELEGRAM_API variable is missing! Exiting now")
    exit(1)

API_HASH = os.environ.get('TELEGRAM_HASH', '')
if len(API_HASH) == 0:
    logging.error("TELEGRAM_HASH variable is missing! Exiting now")
    exit(1)
    
BOT_TOKEN = os.environ.get('BOT_TOKEN', '')
if len(BOT_TOKEN) == 0:
    logging.error("BOT_TOKEN variable is missing! Exiting now")
    exit(1)

DUMP_CHAT_ID = os.environ.get('DUMP_CHAT_ID', '')
if len(DUMP_CHAT_ID) == 0:
    logging.error("DUMP_CHAT_ID variable is missing! Exiting now")
    exit(1)
else:
    DUMP_CHAT_ID = int(DUMP_CHAT_ID)

FSUB_ID = os.environ.get('FSUB_ID', '')
if len(FSUB_ID) == 0:
    logging.error("FSUB_ID variable is missing! Exiting now")
    exit(1)
else:
    FSUB_ID = int(FSUB_ID)

LINK_DUMP = os.environ.get('LINK_DUMP', '')
if len(LINK_DUMP) == 0:
    logging.error("LINK_DUMP variable is missing! Exiting now")
    exit(1)
else:
    LINK_DUMP = int(LINK_DUMP)

DATABASE_URL = os.environ.get('DATABASE_URL', '')
if len(DATABASE_URL) == 0:
    logging.error("DATABASE_URL variable is missing! Exiting now")
    exit(1)

SHORTENER_API = os.environ.get('SHORTENER_API', '')
if len(SHORTENER_API) == 0:
    logging.info("SHORTENER_API variable is missing!")
    SHORTENER_API = None

USER_SESSION_STRING = os.environ.get('USER_SESSION_STRING', '')
if len(USER_SESSION_STRING) == 0:
    logging.info("USER_SESSION_STRING variable is missing! Bot will split Files in 2Gb...")
    USER_SESSION_STRING = None

DATABASE_NAME = "terabox"
COLLECTION_NAME = "user_requests"

client = MongoClient(DATABASE_URL)
db = client[DATABASE_NAME]
collection = db[COLLECTION_NAME]

app = Client("jetbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

user = None
SPLIT_SIZE = 2093796556
if USER_SESSION_STRING:
    user = Client("jetu", api_id=API_ID, api_hash=API_HASH, session_string=USER_SESSION_STRING)
    SPLIT_SIZE = 4241280205

VALID_DOMAINS = [
    'terabox.com', 'nephobox.com', '4funbox.com', 'mirrobox.com', 
    'momerybox.com', 'teraboxapp.com', '1024tera.com', '1024terabox.com', 'teraboxshare.com',
    'terabox.app', 'gibibox.com', 'goaibox.com', 'terasharelink.com', 
    'teraboxlink.com', 'terafileshare.com'
]
last_update_time = 0
ZERO_SPEED_TIMEOUT = 60  # 5 minutes in seconds

# Add these constants for thumbnail and watch URL
BASE_URL = "https://opabhik.serv00.net/Watch.php?url="
DOWNLOAD_BASE = "https://teradownloader.com/download?w=0&link="
FSubLink = "https://t.me/am_films"  # Replace with your actual channel link
START_IMAGE_URL = "https://envs.sh/rhi.jpg"  # Replace with your start image URL

async def fetch_thumbnail(url):
    """Fetch thumbnail URL from Terabox link"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                response.raise_for_status()
                page_content = await response.text()

        soup = BeautifulSoup(page_content, "html.parser")
        thumbnail = soup.find("meta", {"property": "og:image"})
        return thumbnail["content"] if thumbnail else None
    except Exception as e:
        logger.error(f"Error fetching thumbnail: {e}")
        return None

async def is_user_member(client, user_id):
    try:
        member = await client.get_chat_member(FSUB_ID, user_id)
        if member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
            return True
        else:
            return False
    except Exception as e:
        logging.error(f"Error checking membership status for user {user_id}: {e}")
        return False
    
def is_valid_url(url):
    parsed_url = urlparse(url)
    return any(parsed_url.netloc.endswith(domain) for domain in VALID_DOMAINS)

def format_size(size):
    if size < 1024:
        return f"{size} B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.2f} KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / (1024 * 1024):.2f} MB"
    else:
        return f"{size / (1024 * 1024 * 1024):.2f} GB"

@app.on_message(filters.command("start"))
async def start_command(client, message):
    sticker_message = await message.reply_sticker("CAACAgIAAxkBAAEMvrlm1JgGXbW1RXwvrdjbUqN_zltR_AACHxEAApQgCUrPlMAXIC3dCTUE")
    await asyncio.sleep(2)
    await sticker_message.delete()
    user_mention = message.from_user.mention
    
    # Check subscription
    is_member = await is_user_member(client, message.from_user.id)
    if not is_member:
        join_button = InlineKeyboardButton("✨ Join Channel", url=FSubLink)
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await message.reply_photo(
            photo=START_IMAGE_URL,
            caption="❌ You must join our channel to use this bot.\nClick the button below to join and then try again.",
            reply_markup=reply_markup,
        )
        return
    
    reply_message = f"ᴡᴇʟᴄᴏᴍᴇ, {user_mention}.\n\n🌟 ɪ ᴀᴍ ᴀ ᴛᴇʀᴀʙᴏx ᴅᴏᴡɴʟᴏᴀᴅᴇʀ ʙᴏᴛ. sᴇɴᴅ ᴍᴇ ᴀɴʏ ᴛᴇʀᴀʙᴏx ʟɪɴᴋ ɪ ᴡɪʟʟ ᴅᴏᴡɴʟᴏᴀᴅ ᴡɪᴛʜɪɴ ғᴇᴡ sᴇᴄᴏɴᴅs ᴀɴᴅ sᴇɴᴅ ɪᴛ ᴛᴏ ʏᴏᴜ ✨."
    join_button = InlineKeyboardButton("ᴊᴏɪɴ ❤️🚀", url="https://t.me/AM_FILMS")
    developer_button = InlineKeyboardButton("ᴅᴇᴠᴇʟᴏᴘᴇʀ ⚡️", url="https://t.me/GUARDIANff_bot")
    reply_markup = InlineKeyboardMarkup([[join_button, developer_button]])
    
    # Send the start message with image
    await message.reply_photo(
        photo=START_IMAGE_URL,
        caption=reply_message,
        reply_markup=reply_markup
    )

async def update_status_message(status_message, text, reply_markup=None):
    try:
        await status_message.edit_text(text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to update status message: {e}")

@app.on_message(filters.text)
async def handle_message(client: Client, message: Message):
    if message.text.startswith('/'):
        return
    if not message.from_user:
        return

    user_id = message.from_user.id
    is_member = await is_user_member(client, user_id)

    if not is_member:
        join_button = InlineKeyboardButton("✨ Join Channel", url=FSubLink)
        reply_markup = InlineKeyboardMarkup([[join_button]])
        await message.reply_photo(
            photo=START_IMAGE_URL,
            caption="❌ You must join our channel to use this bot.\nClick the button below to join and then try again.",
            reply_markup=reply_markup,
        )
        return
    
    url = None
    for word in message.text.split():
        if is_valid_url(word):
            url = word
            break

    if not url:
        await message.reply_text("Please provide a valid Terabox link.")
        return

    # Fetch thumbnail from the Terabox link
    thumbnail_url = await fetch_thumbnail(url)
    
    encoded_url = urllib.parse.quote(url)
    final_url = f"https://teradlrobot.cheemsbackup.workers.dev/?url={encoded_url}"
    watch_url = f"https://opabhik.serv00.net/Watch.php?url={encoded_url}"
    watch_button = InlineKeyboardButton("ᴡᴀᴛᴄʜ ɴᴏᴡ", url=watch_url)
    watch_markup = InlineKeyboardMarkup([[watch_button]])

    # Send user ID and encoded URL to LINK_DUMP channel with thumbnail
    log_message = (
        f"#Log\n"
        f"USER ID: tg://user?id={user_id}\n"
        f"URL: {encoded_url}"
    )
    
    if thumbnail_url:
        await client.send_photo(
            LINK_DUMP,
            photo=thumbnail_url,
            caption=log_message
        )
    else:
        await client.send_message(LINK_DUMP, log_message)

    download = aria2.add_uris([final_url])
    
    # Send initial message with thumbnail if available
    if thumbnail_url:
        status_message = await message.reply_photo(
            photo=thumbnail_url,
            caption="sᴇɴᴅɪɴɢ ʏᴏᴜ ᴛʜᴇ ᴍᴇᴅɪᴀ...🤤",
            reply_markup=watch_markup
        )
    else:
        status_message = await message.reply_text("sᴇɴᴅɪɴɢ ʏᴏᴜ ᴛʜᴇ ᴍᴇᴅɪᴀ...🤤", reply_markup=watch_markup)

    start_time = datetime.now()
    last_active_time = time.time()
    zero_speed_start = None

    while not download.is_complete:
        await asyncio.sleep(15)
        download.update()
        progress = download.progress

        # Check for zero speed condition
        current_speed = download.download_speed
        if current_speed == 0:
            if zero_speed_start is None:
                zero_speed_start = time.time()
            elif time.time() - zero_speed_start > ZERO_SPEED_TIMEOUT:
                await update_status_message(
                    status_message,
                    "❌ ᴛᴀꜱᴋ ꜱᴛᴏᴘᴘᴇᴅ ʙʏ ʙᴏᴛ: ɴᴏ ᴅᴏᴡɴʟᴏᴀᴅ ᴘʀᴏɢʀᴇꜱꜱ ꜰᴏʀ 1 ᴍɪɴᴜᴛᴇꜱ",
                    reply_markup=watch_markup
                )
                try:
                    download.remove()
                except:
                    pass
                return
        else:
            zero_speed_start = None

        elapsed_time = datetime.now() - start_time
        elapsed_minutes, elapsed_seconds = divmod(elapsed_time.seconds, 60)

        status_text = (
            f"┏ ғɪʟᴇɴᴀᴍᴇ: {download.name}\n"
            f"┠ [{'★' * int(progress / 10)}{'☆' * (10 - int(progress / 10))}] {progress:.2f}%\n"
            f"┠ ᴘʀᴏᴄᴇssᴇᴅ: {format_size(download.completed_length)} ᴏғ {format_size(download.total_length)}\n"
            f"┠ sᴛᴀᴛᴜs: 📥 Downloading\n"
            f"┠ ᴇɴɢɪɴᴇ: <b><u>Aria2c v1.37.0</u></b>\n"
            f"┠ sᴘᴇᴇᴅ: {format_size(download.download_speed)}/s\n"
            f"┠ ᴇᴛᴀ: {download.eta} | ᴇʟᴀᴘsᴇᴅ: {elapsed_minutes}m {elapsed_seconds}s\n"
            f"┖ ᴜsᴇʀ: <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a> | ɪᴅ: {user_id}\n"
        )
        while True:
            try:
                await update_status_message(status_message, status_text, reply_markup=watch_markup)
                break
            except FloodWait as e:
                logger.error(f"Flood wait detected! Sleeping for {e.value} seconds")
                await asyncio.sleep(e.value)

    file_path = download.files[0].path
    caption = (
        f"✨ {download.name}\n"
        f"👤 ʟᴇᴇᴄʜᴇᴅ ʙʏ : <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a>\n"
        f"📥 ᴜsᴇʀ ʟɪɴᴋ: tg://user?id={user_id}\n\n"
        "[ᴘᴏᴡᴇʀᴇᴅ ʙʏ AM_FILMS ❤️🚀](https://t.me/AM_FILMS)"
    )
    
    last_update_time = time.time()
    UPDATE_INTERVAL = 15

    async def update_status(message, text):
        nonlocal last_update_time
        current_time = time.time()
        if current_time - last_update_time >= UPDATE_INTERVAL:
            try:
                await message.edit_text(text, reply_markup=watch_markup)
                last_update_time = current_time
            except FloodWait as e:
                logger.warning(f"FloodWait: Sleeping for {e.value}s")
                await asyncio.sleep(e.value)
                await update_status(message, text)
            except Exception as e:
                logger.error(f"Error updating status: {e}")

    async def upload_progress(current, total):
        progress = (current / total) * 100
        elapsed_time = datetime.now() - start_time
        elapsed_minutes, elapsed_seconds = divmod(elapsed_time.seconds, 60)

        # Check for zero upload speed
        current_speed = current / elapsed_time.seconds if elapsed_time.seconds > 0 else 0
        if current_speed == 0:
            if elapsed_time.seconds > ZERO_SPEED_TIMEOUT:
                await update_status_message(
                    status_message,
                    "❌ ᴛᴀꜱᴋ ꜱᴛᴏᴘᴘᴇᴅ ʙʏ ʙᴏᴛ: ɴᴏ ᴅᴏᴡɴʟᴏᴀᴅ ᴘʀᴏɢʀᴇꜱꜱ ꜰᴏʀ 1 ᴍɪɴᴜᴛᴇꜱ",
                    reply_markup=watch_markup
                )
                return True  # Indicate we should stop
        return False  # Continue upload

        status_text = (
            f"┏ ғɪʟᴇɴᴀᴍᴇ: {download.name}\n"
            f"┠ [{'★' * int(progress / 10)}{'☆' * (10 - int(progress / 10))}] {progress:.2f}%\n"
            f"┠ ᴘʀᴏᴄᴇssᴇᴅ: {format_size(current)} ᴏғ {format_size(total)}\n"
            f"┠ sᴛᴀᴛᴜs: 📤 Uploading to Telegram\n"
            f"┠ ᴇɴɢɪɴᴇ: <b><u>PyroFork v2.2.11</u></b>\n"
            f"┠ sᴘᴇᴇᴅ: {format_size(current / elapsed_time.seconds if elapsed_time.seconds > 0 else 0)}/s\n"
            f"┠ ᴇʟᴀᴘsᴇᴅ: {elapsed_minutes}m {elapsed_seconds}s\n"
            f"┖ ᴜsᴇʀ: <a href='tg://user?id={user_id}'>{message.from_user.first_name}</a> | ɪᴅ: {user_id}\n"
        )
        
        await update_status(status_message, status_text)

    async def split_video_with_ffmpeg(input_path, output_prefix, split_size):
        try:
            original_ext = os.path.splitext(input_path)[1].lower() or '.mp4'
            start_time = datetime.now()
            last_progress_update = time.time()
            
            proc = await asyncio.create_subprocess_exec(
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1', input_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            total_duration = float(stdout.decode().strip())
            
            file_size = os.path.getsize(input_path)
            parts = math.ceil(file_size / split_size)
            
            if parts == 1:
                return [input_path]
            
            duration_per_part = total_duration / parts
            split_files = []
            
            for i in range(parts):
                current_time = time.time()
                if current_time - last_progress_update >= UPDATE_INTERVAL:
                    elapsed = datetime.now() - start_time
                    status_text = (
                        f"âœ‚ï¸� Splitting {os.path.basename(input_path)}\n"
                        f"Part {i+1}/{parts}\n"
                        f"Elapsed: {elapsed.seconds // 60}m {elapsed.seconds % 60}s"
                    )
                    await update_status(status_message, status_text)
                    last_progress_update = current_time
                
                output_path = f"{output_prefix}.{i+1:03d}{original_ext}"
                cmd = [
                    'xtra', '-y', '-ss', str(i * duration_per_part),
                    '-i', input_path, '-t', str(duration_per_part),
                    '-c', 'copy', '-map', '0',
                    '-avoid_negative_ts', 'make_zero',
                    output_path
                ]
                
                proc = await asyncio.create_subprocess_exec(*cmd)
                await proc.wait()
                split_files.append(output_path)
            
            return split_files
        except Exception as e:
            logger.error(f"Split error: {e}")
            raise

    async def handle_upload():
        file_size = os.path.getsize(file_path)
        
        if file_size > SPLIT_SIZE:
            await update_status(
                status_message,
                f"âœ‚ï¸� Splitting {download.name} ({format_size(file_size)})",
                reply_markup=watch_markup
            )
            
            split_files = await split_video_with_ffmpeg(
                file_path,
                os.path.splitext(file_path)[0],
                SPLIT_SIZE
            )
            
            try:
                for i, part in enumerate(split_files):
                    part_caption = f"{caption}\n\nPart {i+1}/{len(split_files)}"
                    await update_status(
                        status_message,
                        f"ðŸ“¤ Uploading part {i+1}/{len(split_files)}\n"
                        f"{os.path.basename(part)}",
                        reply_markup=watch_markup
                    )
                    
                    if USER_SESSION_STRING:
                        sent = await user.send_video(
                            DUMP_CHAT_ID, part, 
                            caption=part_caption,
                            progress=upload_progress,
                            reply_markup=watch_markup
                        )
                        await app.copy_message(
                            message.chat.id, DUMP_CHAT_ID, sent.id,
                            reply_markup=watch_markup
                        )
                    else:
                        sent = await client.send_video(
                            DUMP_CHAT_ID, part,
                            caption=part_caption,
                            progress=upload_progress,
                            reply_markup=watch_markup
                        )
                        await client.send_video(
                            message.chat.id, sent.video.file_id,
                            caption=part_caption,
                            reply_markup=watch_markup
                        )
                    os.remove(part)
            finally:
                for part in split_files:
                    try: os.remove(part)
                    except: pass
        else:
            await update_status(
                status_message,
                f"ðŸ“¤ Uploading {download.name}\n"
                f"Size: {format_size(file_size)}",
                reply_markup=watch_markup
            )
            
            if USER_SESSION_STRING:
                sent = await user.send_video(
                    DUMP_CHAT_ID, file_path,
                    caption=caption,
                    progress=upload_progress,
                    reply_markup=watch_markup
                )
                await app.copy_message(
                    message.chat.id, DUMP_CHAT_ID, sent.id,
                    reply_markup=watch_markup
                )
            else:
                sent = await client.send_video(
                    DUMP_CHAT_ID, file_path,
                    caption=caption,
                    progress=upload_progress,
                    reply_markup=watch_markup
                )
                await client.send_video(
                    message.chat.id, sent.video.file_id,
                    caption=caption,
                    reply_markup=watch_markup
                )
        if os.path.exists(file_path):
            os.remove(file_path)

    start_time = datetime.now()
    await handle_upload()

    try:
        await status_message.delete()
        await message.delete()
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

flask_app = Flask(__name__)

@flask_app.route('/')
def home():
    return render_template("index.html")

def run_flask():
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

def keep_alive():
    Thread(target=run_flask).start()

async def start_user_client():
    if user:
        await user.start()
        logger.info("User client started.")

def run_user():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(start_user_client())

if __name__ == "__main__":
    keep_alive()

    if user:
        logger.info("Starting user client...")
        Thread(target=run_user).start()

    logger.info("Starting bot client...")
    app.run()
