import asyncio
import sqlite3
import os
import sys
import time
import json
import logging
import shutil
import signal
import subprocess
import re
from datetime import datetime
from typing import Optional, List, Tuple, Dict, Any

import aiohttp
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message,
    BufferedInputFile
)

# ==============================================================================
# 1. CONFIG — শুধু এই ৩টি ফিল্ড পূরণ করুন
# ==============================================================================
BOT_TOKEN     = "8747043885:AAF-kHjMWDh31tUsmBtg0OSk0IxbxkgzfDU"        # ← এখানে আপনার বট টোকেন
BOT_USERNAME  = "M1ReactBot1_bot"      # ← এখানে আপনার বটের username (@ ছাড়া)
ADMIN_ID      = 8952615815                # ← এখানে আপনার Telegram user ID

# ==============================================================================
# SYSTEM CONSTANTS
# ==============================================================================
HOST_COST_PER_BOT   = 10.0     # প্রতি বট হোস্টিং = ১০ টাকা
SIGNUP_BONUS_POINTS = 20.0     # প্রথমবার বট দিলে ২০ টাকা/পয়েন্ট ফ্রি
MIN_ADD_BALANCE     = 10.0

UPLOAD_DIR   = "hosted_bots"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ==============================================================================
# PREMIUM EMOJIS
# ==============================================================================
EMOJI_IDS = {
    'welcome':        '5994502837327892086',
    'profile':        '5258011929993026890',
    'wallet':         '6210859306602995217',
    'add_balance':    '5985630530111020079',
    'history':        '6032594876506312598',
    'support':        '5967280668885913944',
    'back':           '5877536313623711363',
    'product_store':  '6163205892834598715',
    'reseller':       '5886505193180239900',
    'vip':            '5206607081334906820',
    'grid_id':        '5474625972751837256',
    'name':           '5215399540814781035',
    'account_level':  '6129584162992034014',
    'regular_user':   '5904630315946611415',
    'current_balance':'5316711376876485361',
    'global_stats':   '6161437856662298090',
    'total_orders':   '6160968017304888311',
    'total_spent':    '5197503331215361533',
    'joined_grid':    '5433614043006903194',
    'info_icon':      '6037421444789440735',
    'check_icon':     '6161241250239356403',
    'shield_icon':    '6086672466132865380',
    'money_icon':     '5890848474563352982',
    'point_down':     '6161302621027049305',
    'telegram':       '5875465628285931233',
    'whatsapp':       '5954224165874569584',
    'upi':            '5807750375033278838',
    'bkash':          '5350554349074391003',
    'hosting':        '6161172706856282588',
    'server':         '6161449831031118974',
    'rocket':         '6005986106703613755',
    'play':           '6161241250239356403',
    'stop':           '5877536313623711363',
    'refresh':        '6161302621027049305',
    'upload':         '5985630530111020079',
    'bot':            '6037421444789440735',
    'delete':         '5350554349074391003',
    'key':            '5890848474563352982',
    'admin':          '6129584162992034014',
}

def em(slot: str) -> str:
    eid = EMOJI_IDS.get(slot, '')
    if not eid:
        return "✨"
    return f'<tg-emoji emoji-id="{eid}">✨</tg-emoji>'

def em_id(slot: str) -> Optional[str]:
    return EMOJI_IDS.get(slot)

def fmt(amount: float) -> str:
    return f"₹{amount:,.2f}"

def safe_float(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

# ==============================================================================
# LOGGING
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_activity.log"), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp  = Dispatcher()

# ==============================================================================
# 2. DATABASE
# ==============================================================================
DB = 'Cuibcc.db'

def db_query(q: str, p: tuple = (), fetchone=False, fetchall=False, commit=True):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    try:
        c.execute(q, p)
        if fetchone:  res = c.fetchone()
        elif fetchall: res = c.fetchall()
        else:          res = None
        if commit: conn.commit()
        return res
    except Exception as e:
        logger.error(f"DB Error: {e} | {q} | {p}")
        if commit: conn.rollback()
        return None
    finally:
        conn.close()

def get_setting(key: str, default: str = "") -> str:
    r = db_query("SELECT value FROM settings WHERE key=?", (key,), fetchone=True)
    return r[0] if r and r[0] else default

def set_setting(key: str, value: str):
    db_query("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))

def log_activity(user_id: int, action: str, details: str = ""):
    try:
        db_query(
            "INSERT INTO activity_logs (user_id, action, details, timestamp) VALUES (?, ?, ?, ?)",
            (user_id, action, details, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    except Exception: pass

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # users
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        balance REAL DEFAULT 0.0,
        total_hosted INTEGER DEFAULT 0,
        joined_date TEXT,
        is_banned INTEGER DEFAULT 0,
        is_admin INTEGER DEFAULT 0
    )''')

    # hosted bots
    c.execute('''CREATE TABLE IF NOT EXISTS hosted_bots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        bot_name TEXT,
        main_file TEXT,
        folder TEXT,
        status TEXT DEFAULT 'stopped',
        pid INTEGER DEFAULT 0,
        created_at TEXT,
        last_run_at TEXT
    )''')

    # bot files (each uploaded file)
    c.execute('''CREATE TABLE IF NOT EXISTS bot_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        filename TEXT,
        size_bytes INTEGER,
        uploaded_at TEXT
    )''')

    # payments (bKash manual)
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        txn_id TEXT,
        sender_number TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        reviewed_at TEXT,
        admin_note TEXT
    )''')

    # banned txn ids
    c.execute('''CREATE TABLE IF NOT EXISTS banned_txns (
        txn_id TEXT PRIMARY KEY,
        user_id INTEGER,
        reason TEXT,
        timestamp TEXT
    )''')

    # settings
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    # activity
    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        details TEXT,
        timestamp TEXT
    )''')

    conn.commit()
    conn.close()

    # defaults
    defaults = [
        ('bkash_number', ''),
        ('support_telegram', 'https://t.me/YourSupport'),
        ('support_whatsapp', 'https://wa.me/YourNumber'),
        ('bot_status', 'ON'),
        ('welcome_sticker', ''),
        ('tutorial_video', 'None'),
    ]
    for k, v in defaults:
        db_query("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

# ==============================================================================
# 3. MIDDLEWARE — Ban + Maintenance check
# ==============================================================================
class SecurityMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()
        self.last_times = {}

    async def __call__(self, handler, event, data):
        uid = event.from_user.id
        now = time.time()
        if uid in self.last_times and now - self.last_times[uid] < 0.3:
            return
        self.last_times[uid] = now

        if uid != ADMIN_ID:
            u = db_query("SELECT is_banned FROM users WHERE user_id=?", (uid,), fetchone=True)
            if u and u[0] == 1:
                msg = "🚫 <b>ACCESS DENIED</b>\nYou have been banned from using this bot.\nContact support if you think this is a mistake."
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer(msg, show_alert=True)
                return

            if get_setting("bot_status", "ON") == "OFF":
                msg = "⚠️ <b>Maintenance Mode</b>\n\nThe bot is currently offline for updates. Please check back later!"
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer("⚠️ Bot is currently OFF for Maintenance.", show_alert=True)
                return

        return await handler(event, data)

dp.message.middleware(SecurityMiddleware())
dp.callback_query.middleware(SecurityMiddleware())

# ==============================================================================
# 4. FSM STATES
# ==============================================================================
class UserStates(StatesGroup):
    waiting_payment_txn   = State()
    waiting_payment_sender = State()
    waiting_add_balance   = State()
    waiting_bot_name      = State()
    waiting_bot_main_file = State()
    waiting_bot_files     = State()
    waiting_file_replace  = State()

class AdminStates(StatesGroup):
    waiting_bkash_number   = State()
    waiting_support_telegram = State()
    waiting_support_whatsapp = State()
    waiting_tutorial_video = State()
    waiting_broadcast      = State()
    waiting_user_lookup    = State()
    waiting_add_money      = State()
    waiting_minus_money    = State()
    waiting_ban_confirm    = State()
    waiting_bot_owner_ban  = State()

# ==============================================================================
# 5. KEYBOARDS
# ==============================================================================
def main_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🤖 My Hosted Bots",
            callback_data="menu_my_bots",
            icon_custom_emoji_id=em_id("hosting"),
            style="primary"
        )],
        [
            InlineKeyboardButton(
                text="➕ Host New Bot",
                callback_data="menu_host_new",
                icon_custom_emoji_id=em_id("upload"),
                style="success"
            ),
            InlineKeyboardButton(
                text="💰 Wallet",
                callback_data="menu_wallet",
                icon_custom_emoji_id=em_id("wallet"),
                style="primary"
            )
        ],
        [
            InlineKeyboardButton(
                text="👤 Profile",
                callback_data="menu_profile",
                icon_custom_emoji_id=em_id("profile"),
                style="primary"
            ),
            InlineKeyboardButton(
                text="📞 Support",
                callback_data="menu_support",
                icon_custom_emoji_id=em_id("support"),
                style="danger"
            )
        ],
        [InlineKeyboardButton(
            text="📹 Tutorial",
            callback_data="menu_tutorial",
            icon_custom_emoji_id=em_id("info_icon"),
            style="primary"
        )],
    ])
    if user_id == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton(
            text="⚙️ ADMIN PANEL",
            callback_data="admin_panel",
            icon_custom_emoji_id=em_id("admin"),
            style="danger"
        )])
    return kb

def back_kb(callback: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="BACK", callback_data=callback,
            icon_custom_emoji_id=em_id("back"),
            style="danger"
        )
    ]])

def admin_kb() -> InlineKeyboardMarkup:
    bot_status = get_setting("bot_status", "ON")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Statistics", callback_data="admin_stats", style="primary")],
        [InlineKeyboardButton(text="👥 User Control", callback_data="admin_user_control", style="primary")],
        [InlineKeyboardButton(text="💳 Pending Payments", callback_data="admin_pending_payments", style="success")],
        [InlineKeyboardButton(text="🤖 All Hosted Bots", callback_data="admin_all_bots", style="primary")],
        [InlineKeyboardButton(text="🚫 Banned Transactions", callback_data="admin_banned_txns", style="danger")],
        [InlineKeyboardButton(text="💳 Set bKash Number", callback_data="admin_set_bkash", style="primary")],
        [InlineKeyboardButton(text="📞 Support Links", callback_data="admin_support_links", style="primary")],
        [InlineKeyboardButton(text="📹 Tutorial Video", callback_data="admin_set_tutorial", style="primary")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast", style="primary")],
        [
            InlineKeyboardButton(
                text=f"Bot Status: {bot_status} {'🟢' if bot_status == 'ON' else '🔴'}",
                callback_data="admin_toggle_bot",
                style="success" if bot_status == "ON" else "danger"
            )
        ],
    ])
    return kb

def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="Back to Admin", callback_data="admin_panel",
            icon_custom_emoji_id=em_id("back"),
            style="danger"
        )
    ]])

def confirm_payment_kb(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Approve",
            callback_data=f"pay_approve_{payment_id}",
            icon_custom_emoji_id=em_id("check_icon"),
            style="success"
        )],
        [InlineKeyboardButton(
            text="❌ Reject & Warn",
            callback_data=f"pay_reject_{payment_id}",
            style="danger"
        )],
        [InlineKeyboardButton(
            text="🚫 Ban User (Fraud)",
            callback_data=f"pay_ban_{payment_id}",
            style="danger"
        )],
    ])

# ==============================================================================
# 6. BOT HOSTING ENGINE
# ==============================================================================
def bot_folder(bot_id: int) -> str:
    return os.path.join(UPLOAD_DIR, f"bot_{bot_id}")

def is_process_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False

def stop_bot_process(pid: int) -> bool:
    if not is_process_alive(pid):
        return True
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        if is_process_alive(pid):
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception as e:
        logger.error(f"Stop process error: {e}")
        return False

async def install_requirements(folder: str) -> Tuple[bool, str]:
    req = os.path.join(folder, "requirements.txt")
    if not os.path.exists(req):
        return True, "No requirements.txt (skipping install)"
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "pip", "install", "-r", req,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
        text = out.decode(errors="ignore")
        if proc.returncode == 0:
            return True, text[-1500:]
        else:
            return False, text[-1500:]
    except asyncio.TimeoutError:
        return False, "Installation timed out (180s)."
    except Exception as e:
        return False, str(e)

def start_bot_process(bot_id: int, main_file: str) -> Tuple[bool, str, int]:
    folder = bot_folder(bot_id)
    filepath = os.path.join(folder, main_file)
    if not os.path.exists(filepath):
        return False, f"Main file '{main_file}' not found.", 0
    log_path = os.path.join(folder, "hosting.log")
    try:
        logfile = open(log_path, "ab")
        proc = subprocess.Popen(
            [sys.executable, main_file],
            cwd=folder,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            start_new_session=True
        )
        return True, "Bot started", proc.pid
    except Exception as e:
        return False, str(e), 0

def tail_log(bot_id: int, lines: int = 30) -> str:
    log_path = os.path.join(bot_folder(bot_id), "hosting.log")
    if not os.path.exists(log_path):
        return "No log yet."
    try:
        with open(log_path, "r", errors="ignore") as f:
            data = f.readlines()[-lines:]
        return "".join(data) if data else "Log empty."
    except Exception as e:
        return f"Log read error: {e}"

# ==============================================================================
# 7. START & MAIN MENU
# ==============================================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    user = db_query("SELECT * FROM users WHERE user_id=?", (uid,), fetchone=True)
    if not user:
        db_query(
            "INSERT INTO users (user_id, first_name, username, balance, joined_date) VALUES (?, ?, ?, ?, ?)",
            (uid, message.from_user.first_name, message.from_user.username or "",
             0.0, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        log_activity(uid, "ACCOUNT_CREATED")
    else:
        db_query("UPDATE users SET username=?, first_name=? WHERE user_id=?",
                 (message.from_user.username or "", message.from_user.first_name, uid))

    # check if came from payment verify link
    args = message.text.split()
    if len(args) > 1 and args[1].startswith("v_"):
        try:
            pid = int(args[1].split("v_")[1])
            p = db_query("SELECT * FROM payments WHERE id=? AND user_id=?", (pid, uid), fetchone=True)
            if p:
                await message.answer(
                    f"🧾 <b>Payment #{p[0]}</b>\n"
                    f"💵 Amount: {fmt(p[2])}\n"
                    f"📝 Txn ID: <code>{p[3]}</code>\n"
                    f"📊 Status: <b>{p[4].upper()}</b>\n\n"
                    f"<i>Admin will verify manually.</i>",
                    reply_markup=back_kb()
                )
                return
        except Exception:
            pass

    text = (
        f"{em('welcome')} <b><u>PYTHON BOT HOSTING</u></b> {em('welcome')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('server')} <b>Host your Python bots 24/7!</b>\n"
        f"{em('hosting')} হোস্টিং চার্জ: <b>{fmt(HOST_COST_PER_BOT)}</b> / বট\n"
        f"{em('money_icon')} প্রথমবার বট হোস্টে <b>{fmt(SIGNUP_BONUS_POINTS)}</b> ফ্রি!\n"
        f"{em('check_icon')} অটো ইনস্টল • রান • স্টপ • রিফ্রেশ\n\n"
        f"{em('point_down')} <b>নিচের মেনু থেকে শুরু করুন:</b>"
    )
    sticker = get_setting("welcome_sticker", "")
    if sticker:
        try: await message.answer_sticker(sticker)
        except Exception: pass
    await message.answer(text, reply_markup=main_menu_kb(uid))

@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        f"{em('welcome')} <b><u>PYTHON BOT HOSTING</u></b> {em('welcome')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('server')} <b>Host your Python bots 24/7!</b>\n"
        f"{em('hosting')} হোস্টিং চার্জ: <b>{fmt(HOST_COST_PER_BOT)}</b> / বট\n"
        f"{em('money_icon')} প্রথমবার বট হোস্টে <b>{fmt(SIGNUP_BONUS_POINTS)}</b> ফ্রি!\n\n"
        f"{em('point_down')} <b>মেনু থেকে শুরু করুন:</b>"
    )
    await call.message.edit_text(text, reply_markup=main_menu_kb(call.from_user.id))

# ==============================================================================
# 8. WALLET (bKash manual topup)
# ==============================================================================
@dp.callback_query(F.data == "menu_wallet")
async def wallet_menu(call: CallbackQuery, state: FSMContext):
    u = db_query("SELECT balance, total_hosted FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    bal = safe_float(u[0]) if u else 0.0
    hosted = u[1] if u else 0

    text = (
        f"{em('wallet')} <b><u>MY WALLET</u></b> {em('wallet')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('current_balance')} <b>Balance:</b> {fmt(bal)}\n"
        f"{em('hosting')} <b>Total Hosted:</b> {hosted} bots\n\n"
        f"{em('bkash')} <b>Add Balance (bKash):</b>\n"
        f"• Send money to admin bKash number\n"
        f"• Then submit Txn ID + Sender number\n"
        f"• Admin will verify manually\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="➕ Add Balance (bKash)",
            callback_data="wallet_add_start",
            icon_custom_emoji_id=em_id("bkash"),
            style="success"
        )],
        [InlineKeyboardButton(
            text="📜 Transaction History",
            callback_data="wallet_history",
            icon_custom_emoji_id=em_id("history"),
            style="primary"
        )],
        [InlineKeyboardButton(
            text="BACK", callback_data="back_main",
            icon_custom_emoji_id=em_id("back"),
            style="danger"
        )],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "wallet_add_start")
async def wallet_add_start(call: CallbackQuery, state: FSMContext):
    bkash = get_setting("bkash_number", "")
    if not bkash:
        await call.answer("⚠️ Admin has not configured bKash yet.", show_alert=True)
        return

    await state.set_state(UserStates.waiting_add_balance)
    text = (
        f"{em('bkash')} <b><u>bKash Send Money</u></b> {em('bkash')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('money_icon')} <b>bKash Number:</b>\n"
        f"<code>{bkash}</code>\n\n"
        f"{em('info_icon')} Send money (Personal) then send me:\n"
        f"<code>AMOUNT|TXN_ID|SENDER_NUMBER</code>\n\n"
        f"<b>Example:</b>\n"
        f"<code>100|TXN123ABC|01712345678</code>\n\n"
        f"{em('check_icon')} Admin will approve manually."
    )
    await call.message.edit_text(text, reply_markup=back_kb("menu_wallet"), parse_mode='HTML')

@dp.message(UserStates.waiting_add_balance)
async def wallet_receive_txn(m: Message, state: FSMContext):
    raw = m.text.strip()
    parts = raw.split("|")
    if len(parts) != 3:
        await m.answer("❌ Format: <code>AMOUNT|TXN_ID|SENDER_NUMBER</code>", parse_mode='HTML')
        return
    amount, txn, sender = parts
    try:
        amount = float(amount)
    except ValueError:
        await m.answer("❌ Amount must be a number.")
        return
    if amount < MIN_ADD_BALANCE:
        await m.answer(f"❌ Minimum deposit: {fmt(MIN_ADD_BALANCE)}")
        return
    if len(txn) < 4:
        await m.answer("❌ Txn ID too short.")
        return
    if not re.fullmatch(r"\d{11}", sender):
        await m.answer("❌ Sender number must be 11 digits (BD).")
        return

    # Check banned txn
    b = db_query("SELECT * FROM banned_txns WHERE txn_id=?", (txn,), fetchone=True)
    if b:
        db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (m.from_user.id,))
        await m.answer("🚫 Fraud attempt detected. You have been banned.")
        await state.clear()
        try:
            await bot.send_message(
                ADMIN_ID,
                f"🚨 <b>FRAUD TARGET BANNED</b>\nUser: <code>{m.from_user.id}</code>\n"
                f"Tried banned Txn: <code>{txn}</code>",
                parse_mode='HTML'
            )
        except Exception: pass
        return

    # Check duplicate pending
    dup = db_query("SELECT * FROM payments WHERE txn_id=?", (txn,), fetchone=True)
    if dup:
        await m.answer("❌ This Txn ID has already been submitted.")
        return

    pid = db_query(
        "INSERT INTO payments (user_id, amount, txn_id, sender_number, status, created_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?)",
        (m.from_user.id, amount, txn, sender, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    r = db_query("SELECT id FROM payments WHERE txn_id=? ORDER BY id DESC LIMIT 1", (txn,), fetchone=True)
    pid = r[0] if r else 0

    await state.clear()
    await m.answer(
        f"{em('check_icon')} <b>Payment Submitted!</b>\n\n"
        f"💵 Amount: {fmt(amount)}\n"
        f"📝 Txn: <code>{txn}</code>\n"
        f"📱 Sender: <code>{sender}</code>\n"
        f"🆔 Payment ID: <b>#{pid}</b>\n\n"
        f"⏳ <b>Status: PENDING</b>\n"
        f"Admin will verify manually soon.",
        reply_markup=main_menu_kb(m.from_user.id),
        parse_mode='HTML'
    )

    await _notify_admin_payment(pid, m.from_user.id, amount, txn, sender)
    log_activity(m.from_user.id, "PAYMENT_SUBMITTED", f"pid={pid} amt={amount} txn={txn}")

async def _notify_admin_payment(pid: int, uid: int, amount: float, txn: str, sender: str):
    u = db_query("SELECT first_name, username FROM users WHERE user_id=?", (uid,), fetchone=True)
    name = u[0] if u else "Unknown"
    uname = f"@{u[1]}" if u and u[1] else "None"
    msg = (
        f"{em('money_icon')} <b><u>NEW PAYMENT REQUEST</u></b> {em('money_icon')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>Payment ID:</b> #{pid}\n"
        f"👤 <b>User:</b> {name}\n"
        f"🔗 <b>Username:</b> {uname}\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n\n"
        f"💵 <b>Amount:</b> {fmt(amount)}\n"
        f"📝 <b>Txn ID:</b> <code>{txn}</code>\n"
        f"📱 <b>Sender:</b> <code>{sender}</code>\n"
        f"📅 {datetime.now().strftime('%d-%m-%Y %I:%M %p')}"
    )
    try:
        await bot.send_message(ADMIN_ID, msg, reply_markup=confirm_payment_kb(pid), parse_mode='HTML')
    except Exception as e:
        logger.error(f"admin notify: {e}")

@dp.callback_query(F.data == "wallet_history")
async def wallet_history(call: CallbackQuery):
    rows = db_query(
        "SELECT id, amount, txn_id, status, created_at FROM payments "
        "WHERE user_id=? ORDER BY id DESC LIMIT 15",
        (call.from_user.id,), fetchall=True
    )
    if not rows:
        await call.message.edit_text("📜 No transactions yet.", reply_markup=back_kb("menu_wallet"), parse_mode='HTML')
        return
    text = f"{em('history')} <b><u>TRANSACTION HISTORY</u></b>\n\n"
    icons = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
    for r in rows:
        ic = icons.get(r[3], "❓")
        text += (
            f"{ic} <b>#{r[0]}</b> • {fmt(r[1])}\n"
            f"📝 <code>{r[2]}</code>\n"
            f"📅 {r[4]}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
    await call.message.edit_text(text, reply_markup=back_kb("menu_wallet"), parse_mode='HTML')

# ==============================================================================
# 9. PROFILE
# ==============================================================================
@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    u = db_query(
        "SELECT user_id, first_name, username, balance, total_hosted, joined_date, is_banned "
        "FROM users WHERE user_id=?",
        (call.from_user.id,), fetchone=True
    )
    if not u:
        await call.answer("Profile not found. Send /start again.", show_alert=True)
        return
    status = "🔴 BANNED" if u[6] else "🟢 Active"
    text = (
        f"{em('grid_id')} <b><u>MY PROFILE</u></b> {em('grid_id')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('grid_id')} <b>User ID:</b> <code>{u[0]}</code>\n"
        f"{em('name')} <b>Name:</b> {u[1]}\n"
        f"🔗 <b>Username:</b> @{u[2] or 'None'}\n\n"
        f"{em('current_balance')} <b>Balance:</b> {fmt(safe_float(u[3]))}\n"
        f"{em('hosting')} <b>Total Hosted:</b> {u[4]} bots\n\n"
        f"{em('shield_icon')} <b>Status:</b> {status}\n"
        f"{em('joined_grid')} <b>Joined:</b> {u[5]}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="💰 Add Balance", callback_data="wallet_add_start",
            icon_custom_emoji_id=em_id("add_balance"), style="success"
        )],
        [InlineKeyboardButton(
            text="BACK", callback_data="back_main",
            icon_custom_emoji_id=em_id("back"), style="danger"
        )],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 10. SUPPORT / TUTORIAL
# ==============================================================================
@dp.callback_query(F.data == "menu_support")
async def support_menu(call: CallbackQuery):
    tg = get_setting("support_telegram", "https://t.me/YourSupport")
    wa = get_setting("support_whatsapp", "https://wa.me/YourNumber")
    text = (
        f"{em('support')} <b><u>SUPPORT CENTER</u></b> {em('support')}\n\n"
        f"Contact us via Telegram or WhatsApp for help."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="Telegram", url=tg,
            icon_custom_emoji_id=em_id("telegram"), style="primary"
        )],
        [InlineKeyboardButton(
            text="WhatsApp", url=wa,
            icon_custom_emoji_id=em_id("whatsapp"), style="primary"
        )],
        [InlineKeyboardButton(
            text="BACK", callback_data="back_main",
            icon_custom_emoji_id=em_id("back"), style="danger"
        )],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "menu_tutorial")
async def tutorial_menu(call: CallbackQuery):
    vid = get_setting("tutorial_video", "None")
    text = (
        f"{em('info_icon')} <b><u>TUTORIAL</u></b> {em('info_icon')}\n\n"
        f"<b>How to host a bot:</b>\n"
        f"1️⃣ Add balance via bKash\n"
        f"2️⃣ Click \"Host New Bot\"\n"
        f"3️⃣ Upload bot files (zip)\n"
        f"4️⃣ Bot auto-installs & runs\n"
        f"5️⃣ Control: Start / Stop / Restart / Refresh\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    if vid and vid.startswith("http"):
        kb.inline_keyboard.append([InlineKeyboardButton(
            text="📹 Watch Video", url=vid,
            icon_custom_emoji_id=em_id("info_icon"), style="primary"
        )])
    kb.inline_keyboard.append([InlineKeyboardButton(
        text="BACK", callback_data="back_main",
        icon_custom_emoji_id=em_id("back"), style="danger"
    )])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 11. MY BOTS
# ==============================================================================
@dp.callback_query(F.data == "menu_my_bots")
async def my_bots(call: CallbackQuery):
    rows = db_query(
        "SELECT id, bot_name, status, pid FROM hosted_bots WHERE user_id=? ORDER BY id DESC",
        (call.from_user.id,), fetchall=True
    )
    if not rows:
        text = (
            f"{em('hosting')} <b>You haven't hosted any bots yet.</b>\n\n"
            f"{em('money_icon')} Hosting cost: {fmt(HOST_COST_PER_BOT)} per bot"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="➕ Host First Bot",
                callback_data="menu_host_new",
                icon_custom_emoji_id=em_id("upload"), style="success"
            )],
            [InlineKeyboardButton(
                text="BACK", callback_data="back_main",
                icon_custom_emoji_id=em_id("back"), style="danger"
            )],
        ])
        await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in rows:
        alive = is_process_alive(r[3])
        dot = "🟢" if alive else "🔴"
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"{dot} {r[1]}",
            callback_data=f"mybot_{r[0]}",
            icon_custom_emoji_id=em_id("bot"), style="primary"
        )])
    kb.inline_keyboard.append([InlineKeyboardButton(
        text="BACK", callback_data="back_main",
        icon_custom_emoji_id=em_id("back"), style="danger"
    )])
    await call.message.edit_text(
        f"{em('hosting')} <b><u>MY HOSTED BOTS</u></b> {em('hosting')}\n\n"
        f"Select a bot to control it:",
        reply_markup=kb, parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("mybot_"))
async def mybot_view(call: CallbackQuery):
    bid = int(call.data.split("_")[1])
    b = db_query(
        "SELECT id, bot_name, main_file, status, pid, created_at, last_run_at "
        "FROM hosted_bots WHERE id=? AND user_id=?",
        (bid, call.from_user.id), fetchone=True
    )
    if not b:
        await call.answer("Bot not found.", show_alert=True)
        return
    alive = is_process_alive(b[4])
    dot = "🟢 Running" if alive else "🔴 Stopped"
    files = db_query("SELECT filename, size_bytes FROM bot_files WHERE bot_id=?", (bid,), fetchall=True) or []
    files_txt = "\n".join([f"  • <code>{f[0]}</code> ({f[1]} bytes)" for f in files]) or "  (no files)"
    text = (
        f"{em('bot')} <b><u>{b[1]}</u></b> {em('bot')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Bot ID: <code>{b[0]}</code>\n"
        f"📄 Main: <code>{b[2]}</code>\n"
        f"📊 Status: <b>{dot}</b>\n"
        f"🆔 PID: <code>{b[4] if alive else '-'}</code>\n"
        f"📅 Created: {b[5]}\n"
        f"📅 Last Run: {b[6] or 'Never'}\n\n"
        f"📁 <b>Files:</b>\n{files_txt}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="▶️ Start", callback_data=f"bot_start_{bid}",
                icon_custom_emoji_id=em_id("play"), style="success"
            ),
            InlineKeyboardButton(
                text="⏹ Stop", callback_data=f"bot_stop_{bid}",
                icon_custom_emoji_id=em_id("stop"), style="danger"
            ),
        ],
        [
            InlineKeyboardButton(
                text="🔄 Restart", callback_data=f"bot_restart_{bid}",
                icon_custom_emoji_id=em_id("refresh"), style="primary"
            ),
            InlineKeyboardButton(
                text="📋 Logs", callback_data=f"bot_logs_{bid}",
                icon_custom_emoji_id=em_id("info_icon"), style="primary"
            ),
        ],
        [InlineKeyboardButton(
            text="📤 Upload / Replace Files",
            callback_data=f"bot_files_{bid}",
            icon_custom_emoji_id=em_id("upload"), style="primary"
        )],
        [InlineKeyboardButton(
            text="🗑 Delete Bot", callback_data=f"bot_delete_{bid}",
            icon_custom_emoji_id=em_id("delete"), style="danger"
        )],
        [InlineKeyboardButton(
            text="BACK", callback_data="menu_my_bots",
            icon_custom_emoji_id=em_id("back"), style="danger"
        )],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("bot_start_"))
async def bot_start(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, bot_name, main_file, pid FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if is_process_alive(b[3]):
        await call.answer("Already running.", show_alert=True)
        return
    await call.message.edit_text("⚡ <b>Starting bot...</b>", parse_mode='HTML')
    ok, msg, pid = start_bot_process(bid, b[2])
    if ok:
        db_query("UPDATE hosted_bots SET status='running', pid=?, last_run_at=? WHERE id=?",
                 (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
        await call.message.edit_text(
            f"✅ <b>Bot started!</b>\n🆔 PID: <code>{pid}</code>\n\n{msg}",
            reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
        )
    else:
        await call.message.edit_text(
            f"❌ <b>Failed to start</b>\n<code>{msg}</code>",
            reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
        )

@dp.callback_query(F.data.startswith("bot_stop_"))
async def bot_stop(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, pid FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if not is_process_alive(b[1]):
        await call.answer("Bot is not running.", show_alert=True)
        return
    stop_bot_process(b[1])
    db_query("UPDATE hosted_bots SET status='stopped', pid=0 WHERE id=?", (bid,))
    await call.answer("⏹ Bot stopped.", show_alert=True)
    await mybot_view(call)

@dp.callback_query(F.data.startswith("bot_restart_"))
async def bot_restart(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, main_file, pid FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if is_process_alive(b[2]):
        stop_bot_process(b[2])
        await asyncio.sleep(1)
    ok, msg, pid = start_bot_process(bid, b[1])
    if ok:
        db_query("UPDATE hosted_bots SET status='running', pid=?, last_run_at=? WHERE id=?",
                 (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
        await call.answer(f"✅ Restarted (PID {pid})", show_alert=True)
    else:
        await call.answer(f"❌ {msg}", show_alert=True)
    await mybot_view(call)

@dp.callback_query(F.data.startswith("bot_logs_"))
async def bot_logs(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    logs = tail_log(bid, 40)
    if len(logs) > 3500:
        logs = logs[-3500:]
    await call.message.edit_text(
        f"📋 <b>Last 40 log lines:</b>\n<pre>{logs}</pre>",
        reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
    )

@dp.callback_query(F.data.startswith("bot_delete_"))
async def bot_delete(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, pid FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if is_process_alive(b[1]):
        stop_bot_process(b[1])
    folder = bot_folder(bid)
    if os.path.exists(folder):
        try: shutil.rmtree(folder)
        except Exception: pass
    db_query("DELETE FROM hosted_bots WHERE id=?", (bid,))
    db_query("DELETE FROM bot_files WHERE bot_id=?", (bid,))
    await call.answer("🗑 Bot deleted.", show_alert=True)
    await my_bots(call)

# ==============================================================================
# 12. HOST NEW BOT FLOW
# ==============================================================================
@dp.callback_query(F.data == "menu_host_new")
async def host_new_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    u = db_query("SELECT balance, total_hosted FROM users WHERE user_id=?", (uid,), fetchone=True)
    bal = safe_float(u[0]) if u else 0
    hosted = u[1] if u else 0

    # first-time bonus
    if hosted == 0 and bal < HOST_COST_PER_BOT:
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?",
                 (SIGNUP_BONUS_POINTS, uid))
        await call.answer(f"🎁 First-time bonus! {fmt(SIGNUP_BONUS_POINTS)} added.", show_alert=True)
        u = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)
        bal = safe_float(u[0]) if u else 0

    if bal < HOST_COST_PER_BOT:
        await call.message.edit_text(
            f"❌ <b>Insufficient Balance</b>\n\n"
            f"💰 Your balance: {fmt(bal)}\n"
            f"💵 Hosting cost: {fmt(HOST_COST_PER_BOT)}\n\n"
            f"Please add balance first.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="💰 Add Balance", callback_data="wallet_add_start",
                    icon_custom_emoji_id=em_id("add_balance"), style="success"
                )],
                [InlineKeyboardButton(
                    text="BACK", callback_data="back_main",
                    icon_custom_emoji_id=em_id("back"), style="danger"
                )],
            ]),
            parse_mode='HTML'
        )
        return

    await state.set_state(UserStates.waiting_bot_name)
    await call.message.edit_text(
        f"{em('upload')} <b><u>HOST NEW BOT</u></b> {em('upload')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💰 Cost: <b>{fmt(HOST_COST_PER_BOT)}</b> (deducted on upload)\n\n"
        f"<b>Step 1:</b> Enter a name for this bot:\n"
        f"<i>(e.g. My First Bot)</i>",
        reply_markup=back_kb("menu_host_new"), parse_mode='HTML'
    )

@dp.message(UserStates.waiting_bot_name)
async def host_bot_name(m: Message, state: FSMContext):
    name = m.text.strip()[:60]
    await state.update_data(bot_name=name)
    await state.set_state(UserStates.waiting_bot_files)
    await m.answer(
        f"✅ Name: <b>{name}</b>\n\n"
        f"<b>Step 2:</b> Upload your bot files.\n\n"
        f"📦 Upload a <b>.zip</b> file containing all bot files, OR upload individual files one by one.\n\n"
        f"⚠️ Include <code>requirements.txt</code> if needed (auto-install).\n\n"
        f"When done uploading, send <b>/done</b>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text="Cancel", callback_data="back_main",
                icon_custom_emoji_id=em_id("back"), style="danger"
            )
        ]]),
        parse_mode='HTML'
    )

@dp.message(UserStates.waiting_bot_files, F.document)
async def host_bot_file_receive(m: Message, state: FSMContext):
    data = await state.get_data()
    folder_tmp = data.get("tmp_folder")
    if not folder_tmp:
        folder_tmp = os.path.join(UPLOAD_DIR, f"tmp_{m.from_user.id}_{int(time.time())}")
        os.makedirs(folder_tmp, exist_ok=True)
        await state.update_data(tmp_folder=folder_tmp)

    doc = m.document
    fname = doc.file_name or "file.bin"
    # prevent path traversal
    fname = os.path.basename(fname)
    file_path = os.path.join(folder_tmp, fname)

    try:
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, file_path)
    except Exception as e:
        await m.answer(f"❌ Download failed: {e}")
        return

    # if zip, unzip
    if fname.lower().endswith(".zip"):
        try:
            import zipfile
            with zipfile.ZipFile(file_path, 'r') as zf:
                # security: prevent path traversal inside zip
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(folder_tmp, member))
                    if not member_path.startswith(os.path.realpath(folder_tmp) + os.sep):
                        continue
                    zf.extract(member, folder_tmp)
            os.remove(file_path)
            await m.answer("✅ ZIP extracted.")
        except Exception as e:
            await m.answer(f"❌ ZIP extraction failed: {e}")

    await m.answer(f"📥 Saved: <code>{fname}</code>")

@dp.message(UserStates.waiting_bot_files, Command("done"))
async def host_bot_done(m: Message, state: FSMContext):
    data = await state.get_data()
    tmp = data.get("tmp_folder")
    bot_name = data.get("bot_name", "Unnamed")
    if not tmp or not os.path.isdir(tmp):
        await m.answer("❌ No files uploaded. Send files first, or /cancel.", reply_markup=back_kb())
        return

    files = [f for f in os.listdir(tmp) if os.path.isfile(os.path.join(tmp, f))]
    if not files:
        await m.answer("❌ No files found. Please upload at least one file.")
        return

    # detect main file
    main_file = None
    for candidate in ["main.py", "bot.py", "app.py", "index.py"]:
        if candidate in files:
            main_file = candidate
            break
    if not main_file:
        py_files = [f for f in files if f.endswith(".py")]
        if len(py_files) == 1:
            main_file = py_files[0]
        else:
            await state.update_data(pending_main_choice=True)
            await state.set_state(UserStates.waiting_bot_main_file)
            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f, callback_data=f"mainfile_{f}", style="primary")]
                for f in py_files
            ])
            await m.answer("📄 Multiple .py files detected. Choose the MAIN file:", reply_markup=kb)
            return

    await _finalize_host(m, state, tmp, bot_name, main_file)

@dp.callback_query(F.data.startswith("mainfile_"), UserStates.waiting_bot_main_file)
async def host_mainfile_choose(call: CallbackQuery, state: FSMContext):
    main_file = call.data.split("mainfile_", 1)[1]
    data = await state.get_data()
    tmp = data.get("tmp_folder")
    bot_name = data.get("bot_name", "Unnamed")
    if not tmp:
        await call.answer("Session expired. /start again.", show_alert=True)
        await state.clear()
        return
    await call.message.edit_text(f"✅ Main: <code>{main_file}</code>\n\n⚡ Processing...", parse_mode='HTML')
    await _finalize_host(call.message, state, tmp, bot_name, main_file)

async def _finalize_host(m: Message, state: FSMContext, tmp: str, bot_name: str, main_file: str):
    uid = m.from_user.id if isinstance(m, Message) else m.chat.id
    # Deduct cost
    u = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)
    bal = safe_float(u[0]) if u else 0
    if bal < HOST_COST_PER_BOT:
        await m.answer(f"❌ Insufficient balance. You need {fmt(HOST_COST_PER_BOT)}.")
        await state.clear()
        return

    # Create bot record
    db_query(
        "INSERT INTO hosted_bots (user_id, bot_name, main_file, folder, status, pid, created_at) "
        "VALUES (?, ?, ?, '', 'stopped', 0, ?)",
        (uid, bot_name, main_file, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    r = db_query("SELECT id FROM hosted_bots WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,), fetchone=True)
    bid = r[0]
    final_folder = bot_folder(bid)
    try:
        if os.path.exists(final_folder):
            shutil.rmtree(final_folder)
        shutil.move(tmp, final_folder)
    except Exception as e:
        await m.answer(f"❌ Move failed: {e}")
        await state.clear()
        return

    db_query("UPDATE hosted_bots SET folder=? WHERE id=?", (final_folder, bid))
    # record files
    for f in os.listdir(final_folder):
        fp = os.path.join(final_folder, f)
        if os.path.isfile(fp):
            try:
                sz = os.path.getsize(fp)
            except Exception:
                sz = 0
            db_query(
                "INSERT INTO bot_files (bot_id, filename, size_bytes, uploaded_at) VALUES (?, ?, ?, ?)",
                (bid, f, sz, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            )

    # Deduct balance
    db_query("UPDATE users SET balance = balance - ?, total_hosted = total_hosted + 1 WHERE user_id=?",
             (HOST_COST_PER_BOT, uid))

    # Install requirements
    await m.answer("⚡ <b>Installing requirements...</b>\n<i>(this may take a minute)</i>", parse_mode='HTML')
    ok, log = await install_requirements(final_folder)

    if not ok:
        await m.answer(
            f"⚠️ <b>Requirements install failed</b>\n<pre>{log[:1500]}</pre>\n\n"
            f"You can still try to start the bot.",
            reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
        )
    else:
        # Start bot
        await m.answer("⚡ <b>Starting bot...</b>", parse_mode='HTML')
        s_ok, s_msg, pid = start_bot_process(bid, main_file)
        if s_ok:
            db_query("UPDATE hosted_bots SET status='running', pid=?, last_run_at=? WHERE id=?",
                     (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
            await m.answer(
                f"{em('check_icon')} <b>Bot hosted successfully!</b>\n\n"
                f"🤖 Name: <b>{bot_name}</b>\n"
                f"🆔 Bot ID: <code>{bid}</code>\n"
                f"📄 Main: <code>{main_file}</code>\n"
                f"🟢 PID: <code>{pid}</code>",
                reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
            )
        else:
            await m.answer(
                f"❌ <b>Bot started failed</b>\n<code>{s_msg}</code>",
                reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
            )

    log_activity(uid, "BOT_HOSTED", f"bid={bid} main={main_file}")
    await state.clear()

@dp.message(UserStates.waiting_bot_files)
async def host_bot_files_other(m: Message, state: FSMContext):
    await m.answer("📤 Please upload files (as document), or send /done when finished, or /cancel to abort.")

# ==============================================================================
# 13. ADMIN — PAYMENT APPROVAL
# ==============================================================================
@dp.callback_query(F.data.startswith("pay_"))
async def admin_payment_action(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized.", show_alert=True)
        return

    parts = call.data.split("_")
    action = parts[1]
    pid = int(parts[2])

    p = db_query("SELECT * FROM payments WHERE id=?", (pid,), fetchone=True)
    if not p:
        await call.answer("Payment not found.", show_alert=True)
        return
    if p[5] != "pending":
        await call.answer(f"Already {p[5]}.", show_alert=True)
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "approve":
        db_query("UPDATE payments SET status='approved', reviewed_at=? WHERE id=?", (now, pid))
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (p[2], p[1]))
        await call.message.edit_text(
            call.message.html_text + "\n\n✅ <b>APPROVED</b>",
            reply_markup=admin_back_kb(), parse_mode='HTML'
        )
        try:
            await bot.send_message(
                p[1],
                f"✅ <b>Payment Approved!</b>\n\n"
                f"💵 Amount: {fmt(p[2])}\n"
                f"📝 Txn: <code>{p[3]}</code>\n\n"
                f"💰 Balance updated!",
                parse_mode='HTML'
            )
        except Exception: pass
        log_activity(p[1], "PAYMENT_APPROVED", f"pid={pid}")

    elif action == "reject":
        db_query("UPDATE payments SET status='rejected', reviewed_at=? WHERE id=?", (now, pid))
        await call.message.edit_text(
            call.message.html_text + "\n\n❌ <b>REJECTED</b>",
            reply_markup=admin_back_kb(), parse_mode='HTML'
        )
        try:
            await bot.send_message(
                p[1],
                f"❌ <b>Payment Rejected</b>\n\n"
                f"💵 Amount: {fmt(p[2])}\n"
                f"📝 Txn: <code>{p[3]}</code>\n\n"
                f"⚠️ Please double-check and resubmit correctly.",
                parse_mode='HTML'
            )
        except Exception: pass
        log_activity(p[1], "PAYMENT_REJECTED", f"pid={pid}")

    elif action == "ban":
        db_query("INSERT OR REPLACE INTO banned_txns (txn_id, user_id, reason, timestamp) VALUES (?, ?, ?, ?)",
                 (p[3], p[1], "fraud payment", now))
        db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (p[1],))
        db_query("UPDATE payments SET status='rejected', reviewed_at=? WHERE id=?", (now, pid))
        await call.message.edit_text(
            call.message.html_text + "\n\n🚫 <b>USER BANNED</b>",
            reply_markup=admin_back_kb(), parse_mode='HTML'
        )
        try:
            await bot.send_message(
                p[1],
                "🚫 <b>You have been BANNED</b>\nReason: fraud payment attempt.",
                parse_mode='HTML'
            )
        except Exception: pass
        log_activity(p[1], "BANNED_FRAUD", f"pid={pid} txn={p[3]}")

    await call.answer("Done.")

@dp.callback_query(F.data == "admin_pending_payments")
async def admin_pending_payments(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    rows = db_query(
        "SELECT id, user_id, amount, txn_id, sender_number, created_at "
        "FROM payments WHERE status='pending' ORDER BY id ASC",
        fetchall=True
    )
    if not rows:
        await call.message.edit_text("✅ No pending payments.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    # send each as separate message with buttons
    await call.message.edit_text(f"⏳ {len(rows)} pending payments:", reply_markup=admin_back_kb(), parse_mode='HTML')
    for r in rows[:10]:
        text = (
            f"🆔 <b>Payment #{r[0]}</b>\n"
            f"👤 User: <code>{r[1]}</code>\n"
            f"💵 Amount: {fmt(r[2])}\n"
            f"📝 Txn: <code>{r[3]}</code>\n"
            f"📱 Sender: <code>{r[4]}</code>\n"
            f"📅 {r[5]}"
        )
        await call.message.answer(text, reply_markup=confirm_payment_kb(r[0]), parse_mode='HTML')

@dp.callback_query(F.data == "admin_banned_txns")
async def admin_banned_txns(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    rows = db_query("SELECT txn_id, user_id, reason, timestamp FROM banned_txns ORDER BY timestamp DESC LIMIT 20", fetchall=True)
    if not rows:
        await call.message.edit_text("✅ No banned transactions.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    text = "🚫 <b>Banned Transactions</b>\n\n"
    for r in rows:
        text += f"📝 <code>{r[0]}</code>\n👤 {r[1]}\n📅 {r[3]}\n━━━━━━━━━━━━\n"
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')

# ==============================================================================
# 14. ADMIN — PANEL & STATS
# ==============================================================================
@dp.message(Command("admin"))
async def admin_panel_cmd(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ Unauthorized.")
        return
    await state.clear()
    await message.answer(
        "⚙️ <b>ADMIN PANEL</b>\n<i>Authorized.</i>",
        reply_markup=admin_kb(), parse_mode='HTML'
    )

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized.", show_alert=True)
        return
    await state.clear()
    await call.message.edit_text(
        "⚙️ <b>ADMIN PANEL</b>\n<i>Authorized.</i>",
        reply_markup=admin_kb(), parse_mode='HTML'
    )

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    hosted = db_query("SELECT COUNT(*) FROM hosted_bots", fetchone=True)[0]
    running = 0
    for b in db_query("SELECT pid FROM hosted_bots", fetchall=True) or []:
        if is_process_alive(b[0]): running += 1
    pend = db_query("SELECT COUNT(*) FROM payments WHERE status='pending'", fetchone=True)[0]
    appr = db_query("SELECT COUNT(*) FROM payments WHERE status='approved'", fetchone=True)[0]
    total_rev = db_query("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'", fetchone=True)[0]
    banned = db_query("SELECT COUNT(*) FROM users WHERE is_banned=1", fetchone=True)[0]
    text = (
        f"📊 <b><u>STATISTICS</u></b> 📊\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 Users: <b>{users}</b>\n"
        f"🚫 Banned: <b>{banned}</b>\n\n"
        f"🤖 Hosted Bots: <b>{hosted}</b>\n"
        f"🟢 Running: <b>{running}</b>\n\n"
        f"⏳ Pending Payments: <b>{pend}</b>\n"
        f"✅ Approved: <b>{appr}</b>\n"
        f"💰 Total Revenue: <b>{fmt(safe_float(total_rev))}</b>\n"
    )
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_all_bots")
async def admin_all_bots(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    rows = db_query(
        "SELECT id, user_id, bot_name, status, pid FROM hosted_bots ORDER BY id DESC",
        fetchall=True
    )
    if not rows:
        await call.message.edit_text("No bots hosted yet.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in rows:
        alive = is_process_alive(r[4])
        dot = "🟢" if alive else "🔴"
        kb.inline_keyboard.append([InlineKeyboardButton(
            text=f"{dot} #{r[0]} {r[2]} (user {r[1]})",
            callback_data=f"admin_botview_{r[0]}", style="primary"
        )])
    kb.inline_keyboard.append([InlineKeyboardButton(
        text="Back to Admin", callback_data="admin_panel",
        icon_custom_emoji_id=em_id("back"), style="danger"
    )])
    await call.message.edit_text("🤖 <b>All Hosted Bots</b>\nSelect one:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_botview_"))
async def admin_botview(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT * FROM hosted_bots WHERE id=?", (bid,), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    alive = is_process_alive(b[6])
    text = (
        f"🤖 <b>Bot #{b[0]}</b>\n"
        f"👤 Owner: <code>{b[1]}</code>\n"
        f"📛 Name: {b[2]}\n"
        f"📄 Main: <code>{b[3]}</code>\n"
        f"📊 Status: {'🟢 Running' if alive else '🔴 Stopped'}\n"
        f"🆔 PID: <code>{b[6] if alive else '-'}</code>\n"
        f"📅 Created: {b[7]}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="⏹ Force Stop", callback_data=f"admin_force_stop_{bid}",
            icon_custom_emoji_id=em_id("stop"), style="danger"
        )],
        [InlineKeyboardButton(
            text="Back to Admin", callback_data="admin_panel",
            icon_custom_emoji_id=em_id("back"), style="danger"
        )],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_force_stop_"))
async def admin_force_stop(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    bid = int(call.data.split("_")[3])
    b = db_query("SELECT pid FROM hosted_bots WHERE id=?", (bid,), fetchone=True)
    if b and is_process_alive(b[0]):
        stop_bot_process(b[0])
        db_query("UPDATE hosted_bots SET status='stopped', pid=0 WHERE id=?", (bid,))
    await call.answer("⏹ Stopped.", show_alert=True)
    await admin_all_bots(call)

@dp.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    cur = get_setting("bot_status", "ON")
    new = "OFF" if cur == "ON" else "ON"
    set_setting("bot_status", new)
    await call.message.edit_reply_markup(reply_markup=admin_kb())
    await call.answer(f"Bot status: {new}", show_alert=True)

# ==============================================================================
# 15. ADMIN — USER CONTROL
# ==============================================================================
@dp.callback_query(F.data == "admin_user_control")
async def admin_user_control(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.waiting_user_lookup)
    await call.message.edit_text(
        "👥 <b>User Control</b>\n\nSend a User ID or @username to look up:",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )

@dp.message(AdminStates.waiting_user_lookup)
async def admin_user_lookup(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    target = m.text.strip().lstrip("@")
    u = db_query(
        "SELECT user_id, first_name, username, balance, total_hosted, is_banned, joined_date "
        "FROM users WHERE user_id=? OR username=? COLLATE NOCASE",
        (target, target), fetchone=True
    )
    if not u:
        await m.answer("❌ User not found.", reply_markup=admin_back_kb())
        return
    await state.update_data(target_uid=u[0])
    text = (
        f"👤 <b>User #{u[0]}</b>\n\n"
        f"Name: {u[1]}\n"
        f"Username: @{u[2] or 'None'}\n"
        f"💰 Balance: {fmt(safe_float(u[3]))}\n"
        f"🤖 Hosted: {u[4]}\n"
        f"🚫 Banned: {'YES' if u[5] else 'NO'}\n"
        f"📅 Joined: {u[6]}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➕ Add Money", callback_data=f"u_add_{u[0]}", style="success"),
            InlineKeyboardButton(text="➖ Minus Money", callback_data=f"u_minus_{u[0]}", style="danger"),
        ],
        [InlineKeyboardButton(
            text=("✅ Unban" if u[5] else "🚫 Ban User"),
            callback_data=f"u_{'unban' if u[5] else 'ban'}_{u[0]}",
            style="danger"
        )],
        [InlineKeyboardButton(
            text="Back to Admin", callback_data="admin_panel",
            icon_custom_emoji_id=em_id("back"), style="danger"
        )],
    ])
    await m.answer(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("u_ban_"))
async def admin_ban_user(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.split("_")[2])
    db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
    await call.answer("🚫 User banned.", show_alert=True)
    try: await bot.send_message(uid, "🚫 You have been banned by admin.")
    except Exception: pass

@dp.callback_query(F.data.startswith("u_unban_"))
async def admin_unban_user(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.split("_")[2])
    db_query("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
    await call.answer("✅ User unbanned.", show_alert=True)
    try: await bot.send_message(uid, "✅ You have been unbanned.")
    except Exception: pass

@dp.callback_query(F.data.startswith("u_add_"))
async def admin_add_money_prompt(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.split("_")[2])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminStates.waiting_add_money)
    await call.message.edit_text(f"➕ Enter amount to ADD to user {uid}:", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.message(AdminStates.waiting_add_money)
async def admin_add_money_do(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    try:
        amt = float(m.text)
    except ValueError:
        await m.answer("❌ Invalid number.")
        return
    uid = data["target_uid"]
    db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    await m.answer(f"✅ Added {fmt(amt)} to {uid}.", reply_markup=admin_kb(), parse_mode='HTML')
    try: await bot.send_message(uid, f"💰 Admin added {fmt(amt)} to your wallet.", parse_mode='HTML')
    except Exception: pass
    await state.clear()

@dp.callback_query(F.data.startswith("u_minus_"))
async def admin_minus_money_prompt(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    uid = int(call.data.split("_")[2])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminStates.waiting_minus_money)
    await call.message.edit_text(f"➖ Enter amount to DEDUCT from user {uid}:", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.message(AdminStates.waiting_minus_money)
async def admin_minus_money_do(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    data = await state.get_data()
    try:
        amt = float(m.text)
    except ValueError:
        await m.answer("❌ Invalid number.")
        return
    uid = data["target_uid"]
    db_query("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, uid))
    await m.answer(f"✅ Deducted {fmt(amt)} from {uid}.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

# ==============================================================================
# 16. ADMIN — SETTINGS (bKash, support, tutorial, broadcast)
# ==============================================================================
@dp.callback_query(F.data == "admin_set_bkash")
async def admin_set_bkash(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    cur = get_setting("bkash_number", "Not set")
    await call.message.edit_text(
        f"💳 Current bKash: <code>{cur}</code>\n\nSend new bKash number:",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.waiting_bkash_number)

@dp.message(AdminStates.waiting_bkash_number)
async def admin_save_bkash(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    num = m.text.strip()
    if not re.fullmatch(r"\+?\d{10,15}", num):
        await m.answer("❌ Invalid number. Use 11-15 digits.")
        return
    set_setting("bkash_number", num)
    await m.answer(f"✅ bKash number set: <code>{num}</code>", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_support_links")
async def admin_support_links(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    tg = get_setting("support_telegram", "Not set")
    wa = get_setting("support_whatsapp", "Not set")
    await call.message.edit_text(
        f"📞 <b>Support Links</b>\n\n"
        f"Telegram: {tg}\n"
        f"WhatsApp: {wa}\n\n"
        f"Send new <b>Telegram link</b> (or /skip):",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.waiting_support_telegram)

@dp.message(AdminStates.waiting_support_telegram)
async def admin_save_tg(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    if m.text != "/skip":
        set_setting("support_telegram", m.text.strip())
    await m.answer("Now send <b>WhatsApp link</b> (or /skip):", parse_mode='HTML')
    await state.set_state(AdminStates.waiting_support_whatsapp)

@dp.message(AdminStates.waiting_support_whatsapp)
async def admin_save_wa(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    if m.text != "/skip":
        set_setting("support_whatsapp", m.text.strip())
    await m.answer("✅ Support links updated.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_tutorial")
async def admin_set_tutorial(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    cur = get_setting("tutorial_video", "None")
    await call.message.edit_text(
        f"📹 Current tutorial: <code>{cur}</code>\n\nSend new video URL (or /clear):",
        reply_markup=admin_back_kb(), parse_mode='HTML'
    )
    await state.set_state(AdminStates.waiting_tutorial_video)

@dp.message(AdminStates.waiting_tutorial_video)
async def admin_save_tutorial(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    v = m.text.strip()
    if v == "/clear":
        v = "None"
    set_setting("tutorial_video", v)
    await m.answer("✅ Tutorial updated.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await call.message.edit_text("📢 Send the message to broadcast to all users:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.waiting_broadcast)

@dp.message(AdminStates.waiting_broadcast)
async def admin_broadcast_do(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    users = db_query("SELECT user_id FROM users", fetchall=True) or []
    sent, failed = 0, 0
    status = await message.answer("⏳ Broadcasting...", parse_mode='HTML')
    for u in users:
        try:
            await message.send_copy(chat_id=u[0])
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.06)
    await status.edit_text(
        f"✅ <b>Broadcast done</b>\n🟢 Sent: {sent}\n🔴 Failed: {failed}",
        reply_markup=admin_kb(), parse_mode='HTML'
    )
    await state.clear()

# ==============================================================================
# 17. ADMIN — FILE REPLACE
# ==============================================================================
@dp.callback_query(F.data.startswith("bot_files_"))
async def bot_files_menu(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, user_id FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    await state.update_data(replace_bot_id=bid)
    await state.set_state(UserStates.waiting_file_replace)
    await call.message.edit_text(
        f"📤 <b>Upload / Replace Files</b> for Bot #{bid}\n\n"
        f"Send a file (or .zip) to add/replace. Existing file with the same name will be overwritten.\n\n"
        f"When done, send /done.",
        reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML'
    )

@dp.message(UserStates.waiting_file_replace, F.document)
async def bot_files_receive(m: Message, state: FSMContext):
    data = await state.get_data()
    bid = data.get("replace_bot_id")
    if not bid:
        await m.answer("Session expired.")
        await state.clear()
        return
    b = db_query("SELECT folder FROM hosted_bots WHERE id=? AND user_id=?",
                 (bid, m.from_user.id), fetchone=True)
    if not b:
        await m.answer("Not found.")
        await state.clear()
        return
    folder = b[0]
    os.makedirs(folder, exist_ok=True)
    fname = os.path.basename(m.document.file_name or "file.bin")
    path = os.path.join(folder, fname)
    try:
        file = await bot.get_file(m.document.file_id)
        await bot.download_file(file.file_path, path)
    except Exception as e:
        await m.answer(f"❌ Download failed: {e}")
        return

    if fname.lower().endswith(".zip"):
        try:
            import zipfile
            with zipfile.ZipFile(path, 'r') as zf:
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(folder, member))
                    if not member_path.startswith(os.path.realpath(folder) + os.sep):
                        continue
                    zf.extract(member, folder)
            os.remove(path)
            await m.answer("✅ ZIP extracted & files replaced.")
        except Exception as e:
            await m.answer(f"❌ ZIP failed: {e}")
    else:
        # upsert in DB
        if db_query("SELECT id FROM bot_files WHERE bot_id=? AND filename=?", (bid, fname), fetchone=True):
            db_query("UPDATE bot_files SET size_bytes=?, uploaded_at=? WHERE bot_id=? AND filename=?",
                     (m.document.file_size, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid, fname))
        else:
            db_query("INSERT INTO bot_files (bot_id, filename, size_bytes, uploaded_at) VALUES (?, ?, ?, ?)",
                     (bid, fname, m.document.file_size, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        await m.answer(f"✅ Saved: <code>{fname}</code>\nSend /done when finished.")

@dp.message(UserStates.waiting_file_replace, Command("done"))
async def bot_files_done(m: Message, state: FSMContext):
    data = await state.get_data()
    bid = data.get("replace_bot_id")
    await state.clear()
    if bid:
        await m.answer("✅ Files updated. You can restart the bot from its menu.",
                       reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')
    else:
        await m.answer("Session expired.", reply_markup=back_kb())

# ==============================================================================
# 18. CANCEL & FALLBACK
# ==============================================================================
@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("✅ Cancelled.", reply_markup=main_menu_kb(m.from_user.id))

@dp.callback_query(F.data == "ignore")
async def ignore_cb(call: CallbackQuery):
    await call.answer()

# ==============================================================================
# 19. BOOT
# ==============================================================================
async def cleanup_dead_bots_on_startup():
    """mark any running bots as stopped if their process died"""
    rows = db_query("SELECT id, pid FROM hosted_bots WHERE status='running'", fetchall=True) or []
    for r in rows:
        if not is_process_alive(r[1]):
            db_query("UPDATE hosted_bots SET status='stopped', pid=0 WHERE id=?", (r[0],))

async def main():
    init_db()
    logger.info("DB initialized.")
    await cleanup_dead_bots_on_startup()
    logger.info("Startup cleanup done.")
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    logger.info("🚀 Bot is starting...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Polling error: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Goodbye.")