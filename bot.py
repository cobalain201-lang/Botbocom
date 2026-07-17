import os
import re
import logging
import asyncio
import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode, ChatAction
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
    """Pesan sambutan yang lebih ramah dan profesional"""
    pesan = (
        "🏨 <b>Selamat datang di Booking Assistant Bot!</b>\n\n"
        "Saya dapat membantu Anda menemukan penginapan terbaik yang bisa dipesan <b>Tanpa Kartu Kredit</b>.\n\n"
        "👇 <b>Cara Penggunaan:</b>\n"
        "Ketikkan nama <b>Kota</b> atau <b>Negara</b> yang Anda tuju.\n"
        "<i>Contoh: Tokyo, Bali, Paris, Jakarta</i>"
    )
    await update.message.reply_text(pesan, parse_mode=ParseMode.HTML)

async def scrape_booking(location: str) -> dict:
    """Fungsi scraping yang mengembalikan dictionary berisi data dan tanggal"""
    besok = datetime.now() + timedelta(days=1)
    lusa = datetime.now() + timedelta(days=2)
    checkin = besok.strftime("%Y-%m-%d")
    checkout = lusa.strftime("%Y-%m-%d")
    
    target_url = f"https://www.booking.com/searchresults.id.html?ss={location}&checkin={checkin}&checkout={checkout}"
    
    scraper_api_url = "http://api.scraperapi.com"
    payload = {
        'api_key': SCRAPERAPI_KEY,
        'url': target_url,
        'render': 'true'
    }
    
    timeout = aiohttp.ClientTimeout(total=60)
    
    async with aiohttp.ClientSession(timeout=timeout) as session:
        for attempt in range(2): 
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
                            teks_card = prop.text.lower()
                            
                            # Filter Bahasa Indonesia dan Inggris
                            kata_kunci = ['tanpa kartu kredit', 'bebas kartu kredit', 'no credit card', 'without credit card']
                            if not any(kunci in teks_card for kunci in kata_kunci):
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
                        return {"results": results[:10], "checkin": checkin, "checkout": checkout}
            except Exception as e:
                logger.error(f"Attempt {attempt+1}: Error - {e}")
            await asyncio.sleep(2)
            
        return {"results": [], "checkin": checkin, "checkout": checkout}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani permintaan user dengan UI yang profesional"""
    if not SCRAPERAPI_KEY:
        await update.message.reply_text("⚠️ <i>Sistem belum dikonfigurasi sepenuhnya. SCRAPERAPI_KEY tidak ditemukan.</i>", parse_mode=ParseMode.HTML)
        return

    location = update.message.text.strip()
    if not location:
        return
        
    # 1. Kirim pesan loading awal
    loading_msg = await update.message.reply_text(
        f"🔍 <i>Sedang menganalisis ketersediaan kamar di <b>{location}</b>...\n(Mohon tunggu ± 30-60 detik)</i>", 
        parse_mode=ParseMode.HTML
    )
    
    # 2. Munculkan efek "sedang mengetik..." di Telegram user
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)
    
    # 3. Proses pencarian
    data = await scrape_booking(location)
    results = data.get("results", [])
    
    # 4. Jika gagal, edit pesan loading menjadi pesan error
    if not results:
        fail_msg = (
            f"❌ <b>Pencarian Gagal</b>\n\n"
            f"Maaf, kami tidak dapat menemukan akomodasi <i>Tanpa Kartu Kredit</i> di <b>{location}</b> saat ini.\n"
            f"Silakan coba masukkan wilayah atau kota lain."
        )
        await context.bot.edit_message_text(
            chat_id=update.effective_chat.id, 
            message_id=loading_msg.message_id, 
            text=fail_msg, 
            parse_mode=ParseMode.HTML
        )
        return
        
    # 5. Format tanggal untuk tampilan UI
    tgl_in = datetime.strptime(data['checkin'], "%Y-%m-%d").strftime("%d %b %Y")
    
    # 6. Format hasil pencarian menjadi list elegan
    final_msg = (
        f"🎯 <b>Rekomendasi Akomodasi Pilihan</b>\n"
        f"📍 <b>Lokasi:</b> {location.title()}\n"
        f"📅 <b>Check-in:</b> {tgl_in} (1 Malam)\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    for i, res in enumerate(results, 1):
        rating_display = f"⭐ {res['rating']}" if res['rating'] != "0.0" else "⭐ (Baru)"
        
        # Link disematkan ke dalam nama hotel agar tidak merusak pemandangan chat
        final_msg += f"<b>{i}. <a href='{res['link']}'>{res['title']}</a></b>\n"
        final_msg += f"└ {rating_display} | 💰 <b>{res['price']}</b>\n\n"
        
    final_msg += "<i>💡 Klik nama akomodasi di atas untuk melihat detail dan memesan (Bebas Kartu Kredit).</i>"
    
    # 7. Edit pesan loading menjadi hasil akhir yang rapi
    await context.bot.edit_message_text(
        chat_id=update.effective_chat.id, 
        message_id=loading_msg.message_id, 
        text=final_msg, 
        parse_mode=ParseMode.HTML, 
        disable_web_page_preview=True # Mematikan preview link otomatis yang membuat chat penuh
    )

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
