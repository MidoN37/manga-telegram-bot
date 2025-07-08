#!/usr/bin/env python3
"""
Manga Reader App - A standalone Python application for reading manga from comick.io
Based on the comick.io Intelligence Briefing API documentation
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import requests
import json
import threading
from PIL import Image, ImageTk
import io
import urllib.parse
from typing import List, Dict, Optional, Tuple
import os
from PIL import Image
import sys
import zipfile

class MangaAPI:
    """Handles all API interactions with comick.io"""
    
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
    
    def search_manga(self, query: str, limit: int = 20) -> List[Dict]:
        """Search for manga by title"""
        try:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"{self.base_url}/v1.0/search?q={encoded_query}&limit={limit}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Search failed: {str(e)}")
    
    def get_manga_details(self, slug: str) -> Dict:
        """Get manga details from slug"""
        try:
            url = f"{self.base_url}/comic/{slug}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            return response.json()
        except requests.RequestException as e:
            raise Exception(f"Failed to get manga details: {str(e)}")
    
    def get_chapters(self, hid: str, lang: str = "en", limit: int = 10000) -> List[Dict]:
        """Get chapter list for a manga"""
        try:
            url = f"{self.base_url}/comic/{hid}/chapters?lang={lang}&limit={limit}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data.get('chapters', [])
        except requests.RequestException as e:
            raise Exception(f"Failed to get chapters: {str(e)}")
    
    def get_chapter_pages(self, chapter_hid: str) -> List[Dict]:
        """Get page images for a chapter"""
        try:
            url = f"{self.base_url}/chapter/{chapter_hid}"
            response = requests.get(url, headers=self.headers, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return data.get('chapter', {}).get('md_images', [])
        except requests.RequestException as e:
            raise Exception(f"Failed to get chapter pages: {str(e)}")
    
    def get_cover_url(self, b2key: str) -> str:
        """Construct cover image URL"""
        return f"{self.cdn_url}/{b2key}"
    
    def get_page_url(self, b2key: str) -> str:
        """Construct page image URL"""
        return f"{self.cdn_url}/{b2key}"
    
    def download_image(self, url: str) -> bytes:
        """Download image data"""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            return response.content
        except requests.RequestException as e:
            raise Exception(f"Failed to download image: {str(e)}")

class MangaReader:
    """Main application class"""
    
    def __init__(self):
        self.save_dir = "/Users/user/Desktop/Manga"
        os.makedirs(self.save_dir, exist_ok=True)
        self.root = tk.Tk()
        self.root.title("Manga Reader")
        self.root.geometry("1200x800")
        
        self.api = MangaAPI()
        self.current_manga = None
        self.current_chapters = []
        self.current_chapter_pages = []
        self.current_page_index = 0
        
        self.setup_ui()
        
    def setup_ui(self):
        """Setup the user interface"""
        # Main notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Search tab
        self.search_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.search_frame, text="Search")
        self.setup_search_tab()
        
        # Manga details tab
        self.details_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.details_frame, text="Manga Details")
        self.setup_details_tab()
        
        # Reader tab
        self.reader_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.reader_frame, text="Reader")
        self.setup_reader_tab()
    
    def setup_search_tab(self):
        """Setup the search interface"""
        # Search controls
        search_controls = ttk.Frame(self.search_frame)
        search_controls.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(search_controls, text="Search:").pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_controls, textvariable=self.search_var, width=40)
        self.search_entry.pack(side=tk.LEFT, padx=(5, 0))
        self.search_entry.bind('<Return>', lambda e: self.search_manga())
        
        self.search_button = ttk.Button(search_controls, text="Search", command=self.search_manga)
        self.search_button.pack(side=tk.LEFT, padx=(5, 0))
        
        # Results listbox
        results_frame = ttk.Frame(self.search_frame)
        results_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.results_listbox = tk.Listbox(results_frame, height=15)
        self.results_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.results_listbox.bind('<Double-1>', self.on_manga_select)
        
        results_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.results_listbox.yview)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.results_listbox.config(yscrollcommand=results_scrollbar.set)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_var.set("Ready")
        status_bar = ttk.Label(self.search_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        self.search_results = []
    
    def setup_details_tab(self):
        """Setup the manga details interface"""
        # Manga info
        info_frame = ttk.Frame(self.details_frame)
        info_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.manga_title_var = tk.StringVar()
        title_label = ttk.Label(info_frame, textvariable=self.manga_title_var, font=('Arial', 16, 'bold'))
        title_label.pack(anchor=tk.W)
        
        self.manga_desc_text = scrolledtext.ScrolledText(info_frame, height=5, wrap=tk.WORD)
        self.manga_desc_text.pack(fill=tk.X, pady=(5, 0))
        
        # Chapters list
        chapters_frame = ttk.Frame(self.details_frame)
        chapters_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        ttk.Label(chapters_frame, text="Chapters:", font=('Arial', 12, 'bold')).pack(anchor=tk.W)
        
        chapters_list_frame = ttk.Frame(chapters_frame)
        chapters_list_frame.pack(fill=tk.BOTH, expand=True)
        
        self.chapters_listbox = tk.Listbox(chapters_list_frame, height=10)
        self.chapters_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.chapters_listbox.bind('<Double-1>', self.on_chapter_select)
        
        chapters_scrollbar = ttk.Scrollbar(chapters_list_frame, orient=tk.VERTICAL, command=self.chapters_listbox.yview)
        chapters_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.chapters_listbox.config(yscrollcommand=chapters_scrollbar.set)
        
        # Load chapter button
        load_button = ttk.Button(chapters_frame, text="Read Selected Chapter", command=self.load_chapter)
        load_button.pack(pady=5)

        # Download manga as PDF button
        download_button = ttk.Button(chapters_frame, text="Download Manga as PDF", command=self.download_manga)
        download_button.pack(pady=5)
    
    def setup_reader_tab(self):
        """Setup the manga reader interface"""
        # Reader controls
        controls_frame = ttk.Frame(self.reader_frame)
        controls_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.prev_button = ttk.Button(controls_frame, text="← Previous", command=self.prev_page)
        self.prev_button.pack(side=tk.LEFT)
        
        self.next_button = ttk.Button(controls_frame, text="Next →", command=self.next_page)
        self.next_button.pack(side=tk.LEFT, padx=(5, 0))
        
        self.page_info_var = tk.StringVar()
        self.page_info_var.set("No chapter loaded")
        page_info_label = ttk.Label(controls_frame, textvariable=self.page_info_var)
        page_info_label.pack(side=tk.LEFT, padx=(20, 0))
        
        # Image display
        self.image_frame = ttk.Frame(self.reader_frame)
        self.image_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.image_label = ttk.Label(self.image_frame, text="No image loaded")
        self.image_label.pack(expand=True)
        
        # Bind keyboard shortcuts
        self.root.bind('<Left>', lambda e: self.prev_page())
        self.root.bind('<Right>', lambda e: self.next_page())
        self.root.focus_set()
    
    def search_manga(self):
        """Search for manga"""
        query = self.search_var.get().strip()
        if not query:
            messagebox.showwarning("Warning", "Please enter a search term")
            return
        
        self.status_var.set("Searching...")
        self.search_button.config(state=tk.DISABLED)
        
        def search_thread():
            try:
                results = self.api.search_manga(query)
                self.root.after(0, self.display_search_results, results)
            except Exception as e:
                self.root.after(0, self.show_error, f"Search error: {str(e)}")
            finally:
                self.root.after(0, lambda: self.search_button.config(state=tk.NORMAL))
        
        threading.Thread(target=search_thread, daemon=True).start()
    
    def display_search_results(self, results):
        """Display search results"""
        self.search_results = results
        self.results_listbox.delete(0, tk.END)
        
        for manga in results:
            title = manga.get('title', 'Unknown Title')
            self.results_listbox.insert(tk.END, title)
        
        self.status_var.set(f"Found {len(results)} results")
    
    def on_manga_select(self, event):
        """Handle manga selection from search results"""
        selection = self.results_listbox.curselection()
        if not selection:
            return
        
        index = selection[0]
        if index < len(self.search_results):
            manga = self.search_results[index]
            self.load_manga_details(manga)
    
    def load_manga_details(self, manga):
        """Load detailed manga information"""
        self.status_var.set("Loading manga details...")
        
        def load_thread():
            try:
                slug = manga.get('slug', '')
                if not slug:
                    raise Exception("No slug found for manga")
                
                details = self.api.get_manga_details(slug)
                comic_info = details.get('comic', {})
                hid = comic_info.get('hid', '')
                
                if not hid:
                    raise Exception("No HID found for manga")
                
                chapters = self.api.get_chapters(hid)
                
                self.root.after(0, self.display_manga_details, comic_info, chapters)
            except Exception as e:
                self.root.after(0, self.show_error, f"Failed to load manga: {str(e)}")
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def display_manga_details(self, comic_info, chapters):
        """Display manga details and chapters"""
        self.current_manga = comic_info
        self.current_chapters = chapters
        
        # Update manga info
        title = comic_info.get('title', 'Unknown Title')
        self.manga_title_var.set(title)
        
        desc = comic_info.get('desc', 'No description available')
        self.manga_desc_text.delete(1.0, tk.END)
        self.manga_desc_text.insert(1.0, desc)
        
        # Update chapters list
        self.chapters_listbox.delete(0, tk.END)
        for chapter in chapters:
            chap_num = chapter.get('chap', 'Unknown')
            title = chapter.get('title', '')
            display_text = f"Chapter {chap_num}"
            if title:
                display_text += f": {title}"
            self.chapters_listbox.insert(tk.END, display_text)
        
        # Switch to details tab
        self.notebook.select(self.details_frame)
        self.status_var.set(f"Loaded {len(chapters)} chapters")
    
    def on_chapter_select(self, event):
        """Handle chapter selection"""
        self.load_chapter()
    
    def load_chapter(self):
        """Load selected chapter for reading"""
        selection = self.chapters_listbox.curselection()
        if not selection:
            messagebox.showwarning("Warning", "Please select a chapter")
            return
        
        index = selection[0]
        if index >= len(self.current_chapters):
            return
        
        chapter = self.current_chapters[index]
        chapter_hid = chapter.get('hid', '')
        
        if not chapter_hid:
            messagebox.showerror("Error", "Chapter HID not found")
            return
        
        self.status_var.set("Loading chapter pages...")
        
        def load_thread():
            try:
                pages = self.api.get_chapter_pages(chapter_hid)
                self.root.after(0, self.display_chapter, pages, chapter)
            except Exception as e:
                self.root.after(0, self.show_error, f"Failed to load chapter: {str(e)}")
        
        threading.Thread(target=load_thread, daemon=True).start()
    
    def display_chapter(self, pages, chapter):
        """Display chapter in reader"""
        self.current_chapter_pages = pages
        self.current_page_index = 0
        
        chap_num = chapter.get('chap', 'Unknown')
        self.status_var.set(f"Loaded Chapter {chap_num} - {len(pages)} pages")
        
        # Switch to reader tab
        self.notebook.select(self.reader_frame)
        
        # Load first page
        if pages:
            self.load_page(0)
    
    def load_page(self, page_index):
        """Load and display a specific page"""
        if not self.current_chapter_pages or page_index < 0 or page_index >= len(self.current_chapter_pages):
            return
        
        self.current_page_index = page_index
        page = self.current_chapter_pages[page_index]
        
        self.page_info_var.set(f"Page {page_index + 1} of {len(self.current_chapter_pages)}")
        self.image_label.config(text="Loading image...")
        
        def load_image_thread():
            try:
                b2key = page.get('b2key', '')
                if not b2key:
                    raise Exception("No image key found")
                
                url = self.api.get_page_url(b2key)
                image_data = self.api.download_image(url)
                
                self.root.after(0, self.display_image, image_data)
            except Exception as e:
                self.root.after(0, self.show_error, f"Failed to load page: {str(e)}")
        
        threading.Thread(target=load_image_thread, daemon=True).start()
        self.save_progress()
    
    def display_image(self, image_data):
        """Display the loaded image"""
        try:
            # Open image with PIL
            img = Image.open(io.BytesIO(image_data))
            
            # Get display area size
            self.image_frame.update()
            frame_width = self.image_frame.winfo_width()
            frame_height = self.image_frame.winfo_height()
            
            # Calculate scaling to fit frame while maintaining aspect ratio
            img_width, img_height = img.size
            scale_w = frame_width / img_width
            scale_h = frame_height / img_height
            scale = min(scale_w, scale_h, 1.0)  # Don't scale up
            
            new_width = int(img_width * scale)
            new_height = int(img_height * scale)
            
            # Resize image
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Convert to PhotoImage
            photo = ImageTk.PhotoImage(img)
            
            # Update label
            self.image_label.config(image=photo, text="")
            self.image_label.image = photo  # Keep reference
            
        except Exception as e:
            self.show_error(f"Failed to display image: {str(e)}")
    
    def prev_page(self):
        """Go to previous page"""
        if self.current_page_index > 0:
            self.load_page(self.current_page_index - 1)
    
    def next_page(self):
        """Go to next page"""
        if self.current_page_index < len(self.current_chapter_pages) - 1:
            self.load_page(self.current_page_index + 1)
    
    def download_manga(self):
        """Download all chapters and create a PDF file"""
        if not self.current_manga or not self.current_chapters:
            messagebox.showwarning("Warning", "No manga loaded")
            return

        title = self.current_manga.get('title', 'manga').replace(' ', '_')
        pdf_filename = os.path.join(self.save_dir, f"{title}.pdf")
        self.status_var.set("Downloading manga...")

        def download_thread():
            try:
                image_list = []
                for chapter in self.current_chapters:
                    chapter_hid = chapter.get('hid', '')
                    if not chapter_hid:
                        continue
                    pages = self.api.get_chapter_pages(chapter_hid)
                    for page in pages:
                        b2key = page.get('b2key', '')
                        if not b2key:
                            continue
                        url = self.api.get_page_url(b2key)
                        img_data = self.api.download_image(url)
                        try:
                            img = Image.open(io.BytesIO(img_data)).convert("RGB")
                            image_list.append(img)
                        except Exception:
                            pass
                # Save PDF if images were downloaded
                if image_list:
                    image_list[0].save(
                        pdf_filename,
                        save_all=True,
                        append_images=image_list[1:],
                        resolution=100.0,
                        quality=95
                    )
                self.root.after(0, lambda: self.status_var.set(f"Downloaded as {pdf_filename}"))
                self.root.after(0, lambda: messagebox.showinfo("Download Complete", f"Saved as {pdf_filename}"))
            except Exception as e:
                self.root.after(0, lambda: self.show_error(f"Download failed: {str(e)}"))

        threading.Thread(target=download_thread, daemon=True).start()

    def save_progress(self):
        """Save current reading progress to a file"""
        progress = {
            "manga_hid": self.current_manga.get('hid') if self.current_manga else None,
            "chapter_hid": self.current_chapter_pages[self.current_page_index].get('chapter_hid') if self.current_chapter_pages else None,
            "page_index": self.current_page_index
        }
        progress_path = os.path.join(self.save_dir, "progress.json")
        with open(progress_path, "w") as f:
            json.dump(progress, f)

    def load_progress(self):
        """Load reading progress from file"""
        progress_path = os.path.join(self.save_dir, "progress.json")
        try:
            with open(progress_path, "r") as f:
                progress = json.load(f)
            return progress
        except Exception:
            return None
    
    def show_error(self, message):
        """Show error message"""
        messagebox.showerror("Error", message)
        self.status_var.set("Error occurred")
    
    def run(self):
        """Start the application"""
        progress = self.load_progress()
        if progress:
            # Optionally, auto-load manga/chapter/page here
            pass
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        self.save_progress()
        self.root.destroy()

def main():
    """Main function"""
    try:
        app = MangaReader()
        app.run()
    except Exception as e:
        print(f"Failed to start application: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()