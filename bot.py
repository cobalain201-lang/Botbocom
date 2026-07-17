import os
import re
import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta

# Load Environment Variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY")

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pesan = (
        "Halo 👋 Masukkan nama negara atau kota yang ingin dicari.\n"
        "Bot akan mencarikan akomodasi yang bisa dipesan **Tanpa Kartu Kredit**.\n\n"
        "Contoh:\nIndonesia\nTokyo\nBali\nJerman"
    )
    await update.message.reply_text(pesan, parse_mode="Markdown")

async def scrape_booking(location: str) -> list:
    # Set tanggal check-in besok dan check-out lusa agar Booking.com mau memunculkan data
    besok = datetime.now() + timedelta(days=1)
    lusa = datetime.now() + timedelta(days=2)
    checkin = besok.strftime("%Y-%m-%d")
    checkout = lusa.strftime("%Y-%m-%d")
    
    # URL Target Asli Booking.com
    target_url = f"https://www.booking.com/searchresults.id.html?ss={location}&lang=id&checkin={checkin}&checkout={checkout}"
    
    # Menggunakan ScraperAPI untuk menembus blokir
    scraper_api_url = "http://api.scraperapi.com"
    payload = {
        'api_key': SCRAPERAPI_KEY,
        'url': target_url,
        'render': 'true' # Memaksa sistem merender JavaScript Booking.com
    }
    
    # Timeout diperpanjang karena proses proxy/rendering butuh waktu ekstra
    timeout = aiohttp.ClientTimeout(total=45)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(2): # 2 kali percobaan sudah cukup untuk API
            try:
                async with session.get(scraper_api_url, params=payload) as response:
                    if response.status != 200:
                        logger.warning(f"Attempt {attempt+1}: HTTP {response.status}")
                        await asyncio.sleep(3)
                        continue
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    properties = soup.find_all('div', {'data-testid': 'property-card'})
                    
                    results = []
                    for prop in properties:
                        try:
                            # Filter: Hanya ambil jika ada teks tanpa kartu kredit
                            if not re.search(r'(tanpa kartu kredit|bebas kartu kredit)', prop.text, re.IGNORECASE):
                                continue 
                            
                            title_elem = prop.find('div', {'data-testid': 'title'})
                            title = title_elem.text.strip() if title_elem else "Hotel Tanpa Nama"
                            
                            link_elem = prop.find('a', {'data-testid': 'title-link'})
                            link = link_elem['href'] if link_elem else ""
                            if link and link.startswith('/'):
                                link = f"https://www.booking.com{link}"
                            link = link.split('?')[0] 
                                
                            rating_elem = prop.find('div', {'data-testid': 'review-score'})
                            rating = "0.0"
                            if rating_elem:
                                match = re.search(r'(\d+[.,]\d+)', rating_elem.text)
                                if match:
                                    rating = match.group(1).replace(',', '.')
                                    
                            price_elem = prop.find('span', {'data-testid': 'price-and-discounted-price'})
                            price = price_elem.text.strip() if price_elem else "Harga tidak tersedia"
                            
                            results.append({
                                "title": title,
                                "rating": rating,
                                "price": price,
                                "link": link
                            })
                        except Exception as e:
                            continue
                            
                    if results:
                        # Urutkan berdasarkan rating tertinggi ke terendah
                        results.sort(key=lambda x: float(x['rating']) if x['rating'] != "N/A" else 0.0, reverse=True)
                        return results[:10]
            except asyncio.TimeoutError:
                logger.error(f"Attempt {attempt+1}: Timeout saat mengambil data dari API")
            except Exception as e:
                logger.error(f"Attempt {attempt+1}: Error - {e}")
            await asyncio.sleep(2)
        return []

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not SCRAPERAPI_KEY:
        await update.message.reply_text("⚠️ Sistem belum dikonfigurasi sepenuhnya. `SCRAPERAPI_KEY` tidak ditemukan.", parse_mode="Markdown")
        return

    location = update.message.text.strip()
    if not location:
        return
        
    await update.message.reply_text(f"🔍 Sedang mencari akomodasi **Tanpa Kartu Kredit** di {location}...\n*(Proses ini mungkin memakan waktu hingga 30 detik untuk menembus proteksi)*", parse_mode="Markdown")
    results = await scrape_booking(location)
    
    if not results:
        await update.message.reply_text(f"❌ Tidak ditemukan akomodasi yang bisa dipesan tanpa kartu kredit di wilayah tersebut saat ini.", parse_mode="Markdown")
        return
        
    msg = f"🏨 Top {len(results)} Akomodasi Tanpa Kartu Kredit\nLokasi: {location}\n\n"
    for i, res in enumerate(results, 1):
        msg += f"{i}. {res['title']}\n"
        rating_display = f"⭐ {res['rating']}" if res['rating'] != "0.0" else "⭐ Baru/Belum ada rating"
        msg += f"{rating_display} 💰 {res['price']}\n"
        msg += f"✅ Bebas Kartu Kredit\n"
        msg += f"{res['link']}\n\n"
        
    await update.message.reply_text(msg, disable_web_page_preview=True)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN tidak ditemukan.")
        return
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    logger.info("Bot sedang berjalan...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
