import os
import asyncio
import threading
import time
import requests
from flask import Flask, send_from_directory
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# =========================================
# ১. বট কনফিগারেশন ও টোকেন সেটআপ
# =========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8806537084:AAGyUPFqBUY96NzRC8XRaYo_GBodldfVuIo")
APP_URL = os.environ.get("APP_URL", "https://python-hosting-m1nx11-1.onrender.com")

IS_MASTER_ONLINE = True

# =========================================
# ২. ওয়েবসাইট ও ওয়েলকাম পেজ (Direct index.html)
# =========================================
app = Flask(__name__, template_folder='.')

@app.route('/')
def home():
    # সরাসরি মূল ফোল্ডার থেকে index.html লোড করবে
    return send_from_directory('.', 'index.html')

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# =========================================
# ৩. ২৪/৭ বট অনলাইন রাখার জন্য Auto Self-Ping System
# =========================================
def keep_alive():
    while True:
        time.sleep(600)  # ১০ মিনিট পর পর পিং করবে
        try:
            if APP_URL:
                requests.get(APP_URL)
                print("[Keep-Alive] Server self-ping successfully executed.")
        except Exception as e:
            print(f"[Keep-Alive Error] {e}")

# =========================================
# ৪. সাব-বট / অন্যান্য প্রসেস ম্যানেজমেন্ট
# =========================================
def run_sub_bots():
    while True:
        if IS_MASTER_ONLINE:
            pass
        time.sleep(5)

# =========================================
# ৫. টেলিগ্রাম বট হ্যান্ডলারসমূহ
# =========================================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "<b>👋 Welcome to M1NX VIP Bot!</b>\n\n"
        "✨ <b>System Status:</b> Online 24/7\n"
        "⚡ <b>All Sub-bots:</b> Fully Activated\n\n"
        "আপনার সিস্টেম সফলভাবে চালু আছে এবং সব বট অ্যাক্টিভ করা হয়েছে।"
    )
    await update.message.reply_text(welcome_text, parse_mode='HTML')

# =========================================
# ৬. মেইন এক্সিকিউশন
# =========================================
if __name__ == '__main__':
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    keep_alive_thread = threading.Thread(target=keep_alive, daemon=True)
    keep_alive_thread.start()

    sub_bots_thread = threading.Thread(target=run_sub_bots, daemon=True)
    sub_bots_thread.start()

    application = ApplicationBuilder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))

    print("Master Bot and Web Server are running...")
    application.run_polling()
