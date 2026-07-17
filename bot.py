import os
import re
import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load Environment Variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk command /start"""
    pesan = (
        "Halo 👋 Masukkan nama negara yang ingin dicari.\n"
        "Contoh:\nIndonesia\nThailand\nMalaysia\nJepang"
    )
    await update.message.reply_text(pesan)

async def scrape_booking(country: str) -> list:
    """Fungsi asynchronous untuk scraping data Booking.com dengan header yang ditingkatkan"""
    # Menggunakan URL bahasa Indonesia agar format teks seragam
    url = f"https://www.booking.com/searchresults.id.html?ss={country}&lang=id"
    
    # Header yang lebih lengkap untuk menyamar sebagai browser asli (Mac/Chrome)
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0"
    }
    
    timeout = aiohttp.ClientTimeout(total=20)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(3): 
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Attempt {attempt+1}: Diblokir Booking.com (Status {response.status})")
                        await asyncio.sleep(3)
                        continue
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    properties = soup.find_all('div', {'data-testid': 'property-card'})
                    
                    # Jika tidak ada property-card, kemungkinan terkena CAPTCHA
                    if not properties:
                        logger.warning(f"Attempt {attempt+1}: Halaman ter-load tapi tidak ada hotel (kemungkinan CAPTCHA)")
                    
                    results = []
                    
                    for prop in properties:
                        try:
                            title_elem = prop.find('div', {'data-testid': 'title'})
                            title = title_elem.text.strip() if title_elem else "Hotel Tanpa Nama"
                            
                            link_elem = prop.find('a', {'data-testid': 'title-link'})
                            link = link_elem['href'] if link_elem else ""
                            if link and link.startswith('/'):
                                link = f"https://www.booking.com{link}"
                            link = link.split('?')[0] 
                                
                            rating_elem = prop.find('div', {'data-testid': 'review-score'})
                            rating = "N/A"
                            if rating_elem:
                                match = re.search(r'(\d+[.,]\d+)', rating_elem.text)
                                if match:
                                    rating = match.group(1).replace(',', '.')
                                    
                            price_elem = prop.find('span', {'data-testid': 'price-and-discounted-price'})
                            price = price_elem.text.strip() if price_elem else "Harga tidak tersedia"
                            
                            # Melonggarkan filter Reward
                            reward_value = 0
                            # Cari elemen yang mengandung teks promo/reward
                            badges = prop.find_all(string=re.compile(r'%|Diskon|Reward|Promo|Penawaran', re.IGNORECASE))
                            
                            for text in badges:
                                # Cari angka persentase jika ada
                                val_match = re.search(r'(\d+)\s*%', text)
                                if val_match:
                                    reward_value = int(val_match.group(1))
                                    break
                                else:
                                    # Jika ada kata promo tapi tidak ada persentase, beri nilai default agar tetap masuk
                                    reward_value = 1 
                                    
                            # Hanya ambil yang memiliki indikasi reward/promo
                            if reward_value > 0:
                                results.append({
                                    "title": title,
                                    "rating": rating,
                                    "price": price,
                                    "link": link,
                                    "reward_value": reward_value if reward_value > 1 else "Spesial"
                                })
                                
                        except Exception as e:
                            continue
                            
                    if results:
                        # Urutkan jika nilainya berupa angka (persentase)
                        results.sort(key=lambda x: x['reward_value'] if isinstance(x['reward_value'], int) else 0, reverse=True)
                        return results[:10]
                    
            except Exception as e:
                logger.error(f"Attempt {attempt+1}: Error - {e}")
                
            await asyncio.sleep(2)
            
        return []

    }
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(3): # Retry logic (maks 3 kali percobaan)
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Attempt {attempt+1}: Status Code {response.status}")
                        await asyncio.sleep(2)
                        continue
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    # Targetkan elemen property-card Booking.com
                    properties = soup.find_all('div', {'data-testid': 'property-card'})
                    results = []
                    
                    for prop in properties:
                        try:
                            # Safe parsing: Title
                            title_elem = prop.find('div', {'data-testid': 'title'})
                            title = title_elem.text.strip() if title_elem else "Hotel Tanpa Nama"
                            
                            # Safe parsing: Link
                            link_elem = prop.find('a', {'data-testid': 'title-link'})
                            link = link_elem['href'] if link_elem else ""
                            if link and link.startswith('/'):
                                link = f"https://www.booking.com{link}"
                            link = link.split('?')[0] # Bersihkan parameter URL yang panjang
                                
                            # Safe parsing: Rating
                            rating_elem = prop.find('div', {'data-testid': 'review-score'})
                            rating = "N/A"
                            if rating_elem:
                                match = re.search(r'(\d+[.,]\d+)', rating_elem.text)
                                if match:
                                    rating = match.group(1).replace(',', '.')
                                    
                            # Safe parsing: Harga
                            price_elem = prop.find('span', {'data-testid': 'price-and-discounted-price'})
                            price = price_elem.text.strip() if price_elem else "Harga tidak tersedia"
                            
                            # Safe parsing: Travel Reward (Mencari teks diskon/reward persentase)
                            reward_value = 0
                            # Memeriksa semua badge/teks promo di card tersebut
                            badges = prop.find_all(string=re.compile(r'%|Diskon|Reward', re.IGNORECASE))
                            for text in badges:
                                val_match = re.search(r'(\d+)\s*%', text)
                                if val_match:
                                    reward_value = int(val_match.group(1))
                                    break
                                    
                            # Filter: Hanya ambil yang memiliki Reward
                            if reward_value > 0:
                                results.append({
                                    "title": title,
                                    "rating": rating,
                                    "price": price,
                                    "link": link,
                                    "reward_value": reward_value
                                })
                                
                        except Exception as e:
                            logger.error(f"Error parsing satu akomodasi: {e}")
                            continue
                            
                    # Jika data didapatkan, hentikan retry loop
                    if results:
                        # Urutkan berdasarkan reward terbesar
                        results.sort(key=lambda x: x['reward_value'], reverse=True)
                        return results[:10] # Ambil maksimal 10
                    
            except asyncio.TimeoutError:
                logger.error(f"Attempt {attempt+1}: Timeout")
            except Exception as e:
                logger.error(f"Attempt {attempt+1}: Error fetch/parse data: {e}")
                
            await asyncio.sleep(2) # Delay sebelum retry
            
        return []

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler untuk menangani input nama negara dari user"""
    country = update.message.text.strip()
    
    if not country:
        return
        
    await update.message.reply_text(f"🔍 Sedang mencari akomodasi dengan Travel Reward di {country}...\nMohon tunggu sebentar.")
    
    # Proses pencarian
    results = await scrape_booking(country)
    
    # Jika tidak ada hasil
    if not results:
        await update.message.reply_text("❌ Tidak ditemukan akomodasi dengan Travel Reward di negara tersebut.")
        return
        
    # Format hasil sesuai request
    msg = f"🏨 Top {len(results)} Travel Reward\nNegara: {country}\n\n"
    for i, res in enumerate(results, 1):
        msg += f"{i}. {res['title']}\n"
        msg += f"⭐ {res['rating']} 💰 {res['price']} 🎁 Travel Reward {res['reward_value']}%\n"
        msg += f"{res['link']}\n\n"
        
    await update.message.reply_text(msg, disable_web_page_preview=True)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN tidak ditemukan. Pastikan variabel lingkungan sudah diatur.")
        return
        
    # Inisialisasi Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Daftarkan Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Jalankan bot
    logger.info("Bot sedang berjalan...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
