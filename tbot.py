#!/usr/bin/env python3
import logging
import requests
import urllib.parse
import os
import io
import zipfile
import shutil
import math # For ceiling function

from typing import List, Dict

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# --- Start of API Code (Unchanged) ---
class MangaAPI:
    def __init__(self):
        self.base_url = "https://api.comick.io"
        self.cdn_url = "https://meo.comick.pictures"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Origin': 'https://comick.io',
            'Referer': 'https://comick.io/',
            'Sec-Ch-Ua': '"Brave";v="137", "Chromium";v="137", "Not/A)Brand";v="24"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-site',
        }
    def search_manga(self, query: str, limit: int = 10) -> List[Dict]:
        try:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"{self.base_url}/v1.0/search?q={encoded_query}&limit={limit}&t=true"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e: raise Exception(f"Search failed: {str(e)}")
    def get_chapters(self, hid: str, lang: str = "en", limit: int = 5000) -> List[Dict]:
        try:
            url = f"{self.base_url}/comic/{hid}/chapters?lang={lang}&limit={limit}"
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            chapters = data.get('chapters', [])
            chapters.sort(key=lambda x: float(x.get('chap', 0) or 0), reverse=False)
            return chapters
        except requests.RequestException as e: raise Exception(f"Failed to get chapters: {str(e)}")
    def get_chapter_pages(self, chapter_hid: str) -> List[Dict]:
        try:
            url = f"{self.base_url}/chapter/{chapter_hid}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data.get('chapter', {}).get('md_images', [])
        except requests.RequestException as e: raise Exception(f"Failed to get chapter pages: {str(e)}")
    def download_image(self, url: str) -> bytes:
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e: raise Exception(f"Failed to download image: {str(e)}")

# --- End of API Code ---

# --- Start of Telegram Bot Code ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# States and Constants
SEARCH, SELECT_MANGA, SELECT_CHAPTER = range(3)
CHAPTERS_PER_PAGE = 8
SAFE_LIMIT = 48 * 1024 * 1024 # 48 MB for safety
api = MangaAPI()

# --- Keyboard Generation Functions (Unchanged) ---
def build_chapter_keyboard(chapters: List[Dict], page: int = 0) -> InlineKeyboardMarkup:
    keyboard = []
    start_index = page * CHAPTERS_PER_PAGE
    end_index = start_index + CHAPTERS_PER_PAGE
    for chapter in chapters[start_index:end_index]:
        chap_num, title = chapter.get('chap', 'N/A'), f": {chapter['title']}" if chapter.get('title') else ""
        keyboard.append([InlineKeyboardButton(f"Ch. {chap_num}{title}"[:40], callback_data=f"dl_{chapter['hid']}")])
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("◀️", callback_data=f"page_{page-1}"))
    nav_row.append(InlineKeyboardButton("📥 Download ALL", callback_data="dl_all"))
    if end_index < len(chapters): nav_row.append(InlineKeyboardButton("▶️", callback_data=f"page_{page+1}"))
    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("« Back to Manga Search", callback_data="back_to_search")])
    return InlineKeyboardMarkup(keyboard)

# --- Conversation Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Hi! I am the Manga Downloader Bot.\n\nSend me the title of a manga to search for, or /cancel.')
    return SEARCH

async def search_manga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.message.text
    await update.message.reply_text(f'Searching for "{query}"...')
    try:
        results = api.search_manga(query)
        if not results:
            await update.message.reply_text("Sorry, couldn't find anything. Try another title or /cancel.")
            return SEARCH
        context.user_data['search_results'] = results
        keyboard = [[InlineKeyboardButton(f"{i+1}. {manga.get('title', 'N/A')}", callback_data=f'manga_{i}')] for i, manga in enumerate(results)]
        await update.message.reply_text('Here are the results. Please choose one:', reply_markup=InlineKeyboardMarkup(keyboard))
        return SELECT_MANGA
    except Exception as e:
        await update.message.reply_text(f'An error occurred: {e}')
        return ConversationHandler.END

async def select_manga(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    manga_index = int(query.data.split('_')[1])
    manga = context.user_data['search_results'][manga_index]
    context.user_data['selected_manga'] = manga
    await query.edit_message_text(text=f'Fetching chapters for "{manga["title"]}"...')
    try:
        chapters = api.get_chapters(manga['hid'])
        if not chapters:
            await query.edit_message_text(text=f'"{manga["title"]}" has no downloadable chapters.')
            return ConversationHandler.END
        context.user_data['chapters'] = chapters
        reply_markup = build_chapter_keyboard(chapters, page=0)
        await query.edit_message_text(text=f'You selected "{manga["title"]}". Choose a chapter or download all:', reply_markup=reply_markup)
        return SELECT_CHAPTER
    except Exception as e:
        await query.edit_message_text(f'An error occurred: {e}')
        return ConversationHandler.END

async def change_chapter_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    page = int(query.data.split('_')[-1])
    reply_markup = build_chapter_keyboard(context.user_data['chapters'], page)
    await query.edit_message_text(text="Choose a chapter or download all:", reply_markup=reply_markup)
    return SELECT_CHAPTER

async def back_to_search(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton(f"{i+1}. {m.get('title', 'N/A')}", callback_data=f'manga_{i}')] for i, m in enumerate(context.user_data['search_results'])]
    await query.edit_message_text('Here are the results again:', reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_MANGA

async def download_action(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    manga = context.user_data['selected_manga']
    all_chapters = context.user_data['chapters']
    chapters_to_download, archive_title = [], ""
    
    if query.data == 'dl_all':
        chapters_to_download, archive_title = all_chapters, manga['title']
        msg = await query.edit_message_text(f"Preparing to download all {len(chapters_to_download)} chapters...")
    else: # Single chapter
        chapter_hid = query.data.split('_')[1]
        chapter = next((ch for ch in all_chapters if ch['hid'] == chapter_hid), None)
        chapters_to_download.append(chapter)
        archive_title = f"{manga['title']}_Ch_{chapter.get('chap', 'N/A')}"
        msg = await query.edit_message_text(f"Preparing to download Chapter {chapter.get('chap', 'N/A')}...")
    
    context.job_queue.run_once(archive_worker, 0, chat_id=query.message.chat_id, data={'message_id': msg.message_id, 'archive_title': archive_title, 'chapters': chapters_to_download}, name=str(query.message.chat_id))
    return ConversationHandler.END

# --- archive_worker with improved progress reporting and auto-splitting ---
async def archive_worker(context: ContextTypes.DEFAULT_TYPE):
    job = context.job
    chat_id, message_id = job.chat_id, job.data['message_id']
    archive_title = job.data['archive_title']
    
    is_single_chapter_download = "_Ch_" in archive_title
    safe_title = "".join(c for c in archive_title if c.isalnum() or c in (' ', '_')).rstrip()
    temp_dir = f"./temp_{chat_id}"
    
    downloaded_page_paths = []
    total_pages_for_all_chapters = 0
    
    try:
        # First, pre-calculate total pages to improve progress reporting
        chapter_page_counts = {}
        for i, chapter in enumerate(job.data['chapters']):
            chapter_hid = chapter['hid']
            chapter_pages = api.get_chapter_pages(chapter_hid)
            chapter_page_counts[chapter_hid] = len(chapter_pages)
            total_pages_for_all_chapters += len(chapter_pages)
            
        if total_pages_for_all_chapters == 0:
            await context.bot.edit_message_text("Could not get page counts. Aborting.", chat_id=chat_id, message_id=message_id)
            await context.bot.send_message(chat_id=chat_id, text="Error retrieving page information. Please try again or /start a new search.")
            return

        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        current_page_global_index = 1 # For overall page progress
        
        for i, chapter in enumerate(job.data['chapters']):
            chapter_hid = chapter['hid']
            num_pages_in_chapter = chapter_page_counts[chapter_hid]
            
            for page_num_in_chapter in range(num_pages_in_chapter):
                # Update message with detailed progress
                progress_percentage_chapter = math.floor(((page_num_in_chapter + 1) / num_pages_in_chapter) * 100)
                progress_percentage_overall = math.floor((current_page_global_index / total_pages_for_all_chapters) * 100)
                
                status_text = (
                    f"Downloading Ch. {chapter.get('chap', 'N/A')} ({page_num_in_chapter + 1}/{num_pages_in_chapter} pages, {progress_percentage_chapter}%)\n"
                    f"Overall: {current_page_global_index}/{total_pages_for_all_chapters} pages, {progress_percentage_overall}%"
                )
                await context.bot.edit_message_text(text=status_text, chat_id=chat_id, message_id=message_id)
                
                pages = api.get_chapter_pages(chapter_hid) # Re-fetch just in case, or use cached if logic allows
                page = pages[page_num_in_chapter]
                
                if 'b2key' not in page or not page['b2key']: continue
                img_data = api.download_image(f"https://meo.comick.pictures/{page['b2key']}")
                img_path = os.path.join(temp_dir, f"{current_page_global_index:04d}.jpg") # Use global page index for sorting
                with open(img_path, 'wb') as f: f.write(img_data)
                downloaded_page_paths.append(img_path)
                current_page_global_index += 1
        
        if not downloaded_page_paths:
            await context.bot.edit_message_text("Could not download any images. Aborting.", chat_id=chat_id, message_id=message_id)
            await context.bot.send_message(chat_id=chat_id, text="No pages could be downloaded for this chapter/manga. Please try again or /start a new search.")
            return

        # --- AUTO-SPLITTING LOGIC WITH PROGRESS BAR FOR ARCHIVE CREATION ---
        part_num = 1
        page_index = 0
        
        while page_index < len(downloaded_page_paths):
            part_name = f"{safe_title}_Part_{part_num}" if not is_single_chapter_download else safe_title
            cbz_filename = f"{part_name}.cbz"
            
            # Progress for archive creation
            progress_percentage_archive = math.floor((page_index / len(downloaded_page_paths)) * 100)
            await context.bot.edit_message_text(f"Creating archive: {os.path.basename(cbz_filename)}... ({progress_percentage_archive}%)", chat_id=chat_id, message_id=message_id)

            with zipfile.ZipFile(cbz_filename, 'w') as zipf:
                pages_in_current_part = 0
                while page_index < len(downloaded_page_paths):
                    page_path = downloaded_page_paths[page_index]
                    zipf.write(page_path, arcname=os.path.basename(page_path))
                    
                    # Check size after adding each page
                    if os.path.getsize(cbz_filename) > SAFE_LIMIT and pages_in_current_part > 0: # Ensure at least one page added
                        page_index -= 1 # Revert to put this page in the next part
                        break
                    pages_in_current_part += 1
                    page_index += 1
            
            # Upload
            await context.bot.edit_message_text(f"Uploading: {os.path.basename(cbz_filename)}...", chat_id=chat_id, message_id=message_id)
            with open(cbz_filename, 'rb') as cbz_file:
                await context.bot.send_document(chat_id=chat_id, document=cbz_file, filename=cbz_filename, read_timeout=120, write_timeout=120)
            
            os.remove(cbz_filename)
            part_num += 1

        # Final message after all parts are sent
        final_message = f"Your download of '{archive_title}' is complete!"
        if part_num > 2 or (not is_single_chapter_download and part_num == 2):
            final_message += f" ({part_num-1} parts sent)."
        final_message += "\n\nTo search for another manga, please click /start."
        await context.bot.send_message(chat_id=chat_id, text=final_message)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id) # Delete status message last

    except Exception as e:
        logger.error(f"Error in archive worker: {e}", exc_info=True)
        await context.bot.edit_message_text(f"An unexpected error occurred: {e}", chat_id=chat_id, message_id=message_id)
        await context.bot.send_message(chat_id=chat_id, text="Please try again or /start a new search.")
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        for f in os.listdir('.'):
            if (f.endswith('.cbz') or f.endswith('.zip')) and f.startswith(safe_title):
                try: os.remove(f)
                except OSError: pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text('Okay, operation cancelled. To start a new search, click /start.')
    return ConversationHandler.END

async def post_init(application: Application):
    """Sets up bot commands after the bot has been initialized."""
    commands = [
        BotCommand("start", "Start a new manga search"),
        BotCommand("cancel", "Cancel current operation"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands set successfully!")

def main() -> None:
    application = Application.builder().token(os.environ.get("TELEGRAM_BOT_TOKEN")).post_init(post_init).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, search_manga)],
            SELECT_MANGA: [CallbackQueryHandler(select_manga, pattern='^manga_')],
            SELECT_CHAPTER: [
                CallbackQueryHandler(change_chapter_page, pattern='^page_'),
                CallbackQueryHandler(download_action, pattern='^dl_all$|^dl_'),
                CallbackQueryHandler(back_to_search, pattern='^back_to_search$'),
            ],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False
    )
    application.add_handler(conv_handler)
    application.run_polling()

if __name__ == '__main__':
    main()