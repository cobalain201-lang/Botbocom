import os
import re
import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from datetime import datetime, timedelta # <-- TAMBAHAN BARU

# Load Environment Variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

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
    # --- TAMBAHAN BARU: Set tanggal check-in besok dan check-out lusa ---
    besok = datetime.now() + timedelta(days=1)
    lusa = datetime.now() + timedelta(days=2)
    checkin = besok.strftime("%Y-%m-%d")
    checkout = lusa.strftime("%Y-%m-%d")
    
    # URL ditambahkan parameter checkin dan checkout
    url = f"https://www.booking.com/searchresults.id.html?ss={location}&lang=id&checkin={checkin}&checkout={checkout}"
    # ------------------------------------------------------------------

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Cache-Control": "max-age=0"
    }
    
    timeout = aiohttp.ClientTimeout(total=20)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(3): 
            try:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        logger.warning(f"Attempt {attempt+1}: HTTP {response.status}")
                        await asyncio.sleep(3)
                        continue
                    
                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")
                    properties = soup.find_all('div', {'data-testid': 'property-card'})
                    
                    if not properties:
                        logger.warning(f"Attempt {attempt+1}: Halaman ter-load tapi tidak ada hotel.")
                    
                    results = []
                    for prop in properties:
                        try:
                            # Pencarian teks diperluas
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
                        results.sort(key=lambda x: float(x['rating']) if x['rating'] != "N/A" else 0.0, reverse=True)
                        return results[:10]
            except Exception as e:
                logger.error(f"Attempt {attempt+1}: Error - {e}")
            await asyncio.sleep(2)
        return []

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    location = update.message.text.strip()
    if not location:
        return
        
    await update.message.reply_text(f"🔍 Sedang mencari akomodasi **Tanpa Kartu Kredit** di {location}...\nMohon tunggu sebentar.", parse_mode="Markdown")
    results = await scrape_booking(location)
    
    if not results:
        await update.message.reply_text(f"❌ Tidak ditemukan akomodasi yang bisa dipesan tanpa kartu kredit di wilayah tersebut saat ini.\n*(Coba wilayah lain, atau mungkin pencarian diblokir oleh sistem)*", parse_mode="Markdown")
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
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
