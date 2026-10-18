import asyncio
import sqlite3
import os
import sys
import time
import logging
import shutil
import signal
import subprocess
import re
import zipfile
from datetime import datetime
from typing import Optional, Tuple

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
)

# ==============================================================================
# 1. CONFIG (YOUR DETAILS ADDED)
# ==============================================================================
BOT_TOKEN     = "8747043885:AAF-kHjMWDh31tUsmBtg0OSk0IxbxkgzfDU"
BOT_USERNAME  = "M1ReactBot1_bot"
ADMIN_ID      = 8952615815

# ==============================================================================
# SYSTEM CONSTANTS
# ==============================================================================
HOST_COST_PER_BOT   = 10.0  # 10 Taka / Points per bot
SIGNUP_BONUS_POINTS = 10.0  # First time hosting bonus (10 Taka)
MIN_ADD_BALANCE     = 10.0

UPLOAD_DIR = "hosted_bots"
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
    'hosting':        '6161172706856282588',
    'server':         '6161449831031118974',
    'money_icon':     '5890848474563352982',
    'check_icon':     '6161241250239356403',
    'shield_icon':    '6086672466132865380',
    'point_down':     '6161302621027049305',
    'info_icon':      '6037421444789440735',
    'hosted_bot':     '6160968017304888311',
    'bkash':          '5350554349074391003',
    'nagad':          '6161437856662298090',
    'play':           '6161241250239356403',
    'stop':           '5877536313623711363',
    'refresh':        '6161302621027049305',
    'upload':         '5985630530111020079',
    'delete':         '5350554349074391003',
    'grid_id':        '5474625972751837256',
    'name':           '5215399540814781035',
    'admin':          '6129584162992034014',
    'check':          '6161241250239356403',
    'cross':          '5877536313623711363',
}

def em(slot: str) -> str:
    eid = EMOJI_IDS.get(slot, '')
    return f'<tg-emoji emoji-id="{eid}">✨</tg-emoji>' if eid else ""

def em_id(slot: str) -> Optional[str]:
    return EMOJI_IDS.get(slot)

def fmt(amount: float) -> str:
    return f"৳{amount:,.2f}"

def safe_float(v, default=0.0):
    try: return float(v)
    except (TypeError, ValueError): return default

def mask_number(num: str) -> str:
    """Beautifully masks numbers: 01712*****78 -> 01712***678"""
    if not num: return "N/A"
    if len(num) >= 8:
        return num[:5] + "***" + num[-3:]
    return num

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

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        first_name TEXT,
        username TEXT,
        balance REAL DEFAULT 0.0,
        total_hosted INTEGER DEFAULT 0,
        joined_date TEXT,
        is_banned INTEGER DEFAULT 0
    )''')

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

    c.execute('''CREATE TABLE IF NOT EXISTS bot_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bot_id INTEGER,
        filename TEXT,
        size_bytes INTEGER,
        uploaded_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount REAL,
        method TEXT,
        txn_id TEXT,
        sender_number TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT,
        reviewed_at TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS banned_txns (
        txn_id TEXT PRIMARY KEY,
        user_id INTEGER,
        reason TEXT,
        timestamp TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT,
        details TEXT,
        timestamp TEXT
    )''')

    conn.commit()
    conn.close()

    defaults = [
        ('bkash_number', ''),
        ('nagad_number', ''),
        ('support_telegram', 'https://t.me/YourSupport'),
        ('support_whatsapp', 'https://wa.me/YourNumber'),
        ('bot_status', 'ON'),
    ]
    for k, v in defaults:
        db_query("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

# ==============================================================================
# 3. MIDDLEWARE
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
                msg = "🚫 <b>ACCESS DENIED</b>\nYou have been banned from using this bot."
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer(msg, show_alert=True)
                return

            if get_setting("bot_status", "ON") == "OFF":
                msg = "⚠️ <b>Maintenance Mode</b>\n\nThe bot is currently offline. Please check back later!"
                if isinstance(event, Message): await event.answer(msg)
                elif isinstance(event, CallbackQuery): await event.answer("⚠️ Maintenance Mode.", show_alert=True)
                return

        return await handler(event, data)

dp.message.middleware(SecurityMiddleware())
dp.callback_query.middleware(SecurityMiddleware())

# ==============================================================================
# 4. FSM STATES
# ==============================================================================
class UserStates(StatesGroup):
    waiting_payment_amount = State()
    waiting_payment_txn = State()
    waiting_payment_sender = State()
    waiting_bot_name = State()
    waiting_bot_files = State()
    waiting_bot_main_file = State()
    waiting_file_replace = State()

class AdminStates(StatesGroup):
    waiting_bkash = State()
    waiting_nagad = State()
    waiting_user_lookup = State()
    waiting_add_money = State()
    waiting_minus_money = State()
    waiting_broadcast = State()

# ==============================================================================
# 5. KEYBOARDS
# ==============================================================================
def main_menu_kb(user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="My Hosted Bots", callback_data="menu_my_bots", icon_custom_emoji_id=em_id("hosted_bot"), style="primary")],
        [
            InlineKeyboardButton(text="Host New Bot", callback_data="menu_host_new", icon_custom_emoji_id=em_id("upload"), style="success"),
            InlineKeyboardButton(text="Wallet", callback_data="menu_wallet", icon_custom_emoji_id=em_id("wallet"), style="primary")
        ],
        [
            InlineKeyboardButton(text="Profile", callback_data="menu_profile", icon_custom_emoji_id=em_id("profile"), style="primary"),
            InlineKeyboardButton(text="Support", callback_data="menu_support", icon_custom_emoji_id=em_id("support"), style="danger")
        ],
    ])
    if user_id == ADMIN_ID:
        kb.inline_keyboard.append([InlineKeyboardButton(text="ADMIN PANEL", callback_data="admin_panel", icon_custom_emoji_id=em_id("admin"), style="danger")])
    return kb

def back_kb(callback: str = "back_main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Back", callback_data=callback, icon_custom_emoji_id=em_id("back"), style="danger")
    ]])

def admin_kb() -> InlineKeyboardMarkup:
    bot_status = get_setting("bot_status", "ON")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Statistics", callback_data="admin_stats", style="primary")],
        [InlineKeyboardButton(text="All Hosted Bots Status", callback_data="admin_all_bots", style="primary")],
        [InlineKeyboardButton(text="User Control", callback_data="admin_user_control", style="primary")],
        [InlineKeyboardButton(text="Pending Payments", callback_data="admin_pending_payments", style="success")],
        [InlineKeyboardButton(text="Set bKash Number", callback_data="admin_set_bkash", style="primary")],
        [InlineKeyboardButton(text="Set Nagad Number", callback_data="admin_set_nagad", style="primary")],
        [InlineKeyboardButton(text="Broadcast", callback_data="admin_broadcast", style="primary")],
        [InlineKeyboardButton(text=f"Bot Status: {bot_status}", callback_data="admin_toggle_bot", style="success" if bot_status == "ON" else "danger")],
    ])
    return kb

def admin_back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel", icon_custom_emoji_id=em_id("back"), style="danger")
    ]])

# ==============================================================================
# 6. BOT HOSTING ENGINE
# ==============================================================================
def bot_folder(bot_id: int) -> str:
    return os.path.join(UPLOAD_DIR, f"bot_{bot_id}")

def is_process_alive(pid: int) -> bool:
    if not pid or pid <= 0: return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False

def stop_bot_process(pid: int) -> bool:
    if not is_process_alive(pid): return True
    try:
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        if is_process_alive(pid): os.kill(pid, signal.SIGKILL)
        return True
    except Exception: return False

async def install_requirements(folder: str, main_file: str) -> Tuple[bool, str]:
    req_path = os.path.join(folder, "requirements.txt")
    if os.path.exists(req_path):
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "pip", "install", "-r", req_path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
            return True, "Installed from requirements.txt"
        except Exception as e:
            return False, str(e)
    elif main_file.endswith(".py"):
        try:
            with open(os.path.join(folder, main_file), 'r', encoding='utf-8') as f:
                code = f.read()
            imports = set(re.findall(r'^\s*(?:import|from)\s+([a-zA-Z0-9_]+)', code, re.MULTILINE))
            pkg_map = {'telebot': 'pyTelegramBotAPI', 'telegram': 'python-telegram-bot', 'cv2': 'opencv-python', 'PIL': 'Pillow', 'bs4': 'beautifulsoup4', 'dotenv': 'python-dotenv', 'yaml': 'PyYAML'}
            packages = []
            for imp in imports:
                if imp in sys.builtin_module_names or imp in ['os', 'sys', 'time', 'json', 'math', 're', 'random', 'asyncio', 'sqlite3', 'datetime', 'logging', 'subprocess', 'shutil']:
                    continue
                packages.append(pkg_map.get(imp, imp))
            if packages:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, "-m", "pip", "install", *packages,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
                )
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=180)
                return True, f"Auto-installed: {', '.join(packages)}"
            return True, "No external packages found."
        except Exception as e:
            return False, f"Auto-install failed: {e}"
    return True, "Skipped install."

def start_bot_process(bot_id: int, main_file: str) -> Tuple[bool, str, int]:
    folder = bot_folder(bot_id)
    filepath = os.path.join(folder, main_file)
    if not os.path.exists(filepath):
        return False, f"Main file '{main_file}' not found.", 0
    
    log_path = os.path.join(folder, "hosting.log")
    try:
        logfile = open(log_path, "ab")
        if main_file.endswith(".py"): cmd = [sys.executable, main_file]
        elif main_file.endswith(".php"): cmd = ["php", main_file]
        elif main_file.endswith(".js"): cmd = ["node", main_file]
        else: return False, "Unsupported file type.", 0

        proc = subprocess.Popen(cmd, cwd=folder, stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True)
        return True, "Started", proc.pid
    except Exception as e:
        return False, str(e), 0

def tail_log(bot_id: int, lines: int = 30) -> str:
    log_path = os.path.join(bot_folder(bot_id), "hosting.log")
    if not os.path.exists(log_path): return "No log yet."
    try:
        with open(log_path, "r", errors="ignore") as f:
            data = f.readlines()[-lines:]
        return "".join(data) if data else "Log empty."
    except Exception as e: return f"Log read error: {e}"

# ==============================================================================
# 7. START & MAIN MENU
# ==============================================================================
@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id

    user = db_query("SELECT * FROM users WHERE user_id=?", (uid,), fetchone=True)
    if not user:
        db_query("INSERT INTO users (user_id, first_name, username, balance, joined_date) VALUES (?, ?, ?, ?, ?)",
            (uid, message.from_user.first_name, message.from_user.username or "", 0.0, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    else:
        db_query("UPDATE users SET username=?, first_name=? WHERE user_id=?", (message.from_user.username or "", message.from_user.first_name, uid))

    text = (
        f"{em('welcome')} <b><u>PYTHON BOT HOSTING</u></b> {em('welcome')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('server')} <b>Host your bots 24/7!</b>\n"
        f"{em('hosting')} Hosting Cost: <b>{fmt(HOST_COST_PER_BOT)}</b> / bot\n"
        f"{em('money_icon')} First-time bonus: <b>{fmt(SIGNUP_BONUS_POINTS)}</b> free!\n"
        f"{em('check_icon')} Supports Python, PHP, JS & Auto-install\n\n"
        f"{em('point_down')} <b>Select an option below:</b>"
    )
    await message.answer(text, reply_markup=main_menu_kb(uid))

@dp.callback_query(F.data == "back_main")
async def back_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        f"{em('welcome')} <b><u>PYTHON BOT HOSTING</u></b> {em('welcome')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('server')} <b>Host your bots 24/7!</b>\n"
        f"{em('hosting')} Hosting Cost: <b>{fmt(HOST_COST_PER_BOT)}</b> / bot\n"
        f"{em('money_icon')} First-time bonus: <b>{fmt(SIGNUP_BONUS_POINTS)}</b> free!\n\n"
        f"{em('point_down')} <b>Select an option below:</b>"
    )
    await call.message.edit_text(text, reply_markup=main_menu_kb(call.from_user.id))

# ==============================================================================
# 8. WALLET & PAYMENT (bKash & Nagad)
# ==============================================================================
@dp.callback_query(F.data == "menu_wallet")
async def wallet_menu(call: CallbackQuery, state: FSMContext):
    u = db_query("SELECT balance, total_hosted FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    bal = safe_float(u[0]) if u else 0.0
    hosted = u[1] if u else 0

    text = (
        f"{em('wallet')} <b><u>MY WALLET</u></b> {em('wallet')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('money_icon')} <b>Balance:</b> {fmt(bal)}\n"
        f"{em('hosted_bot')} <b>Total Hosted:</b> {hosted} bots\n\n"
        f"{em('info_icon')} <b>Select a method to add balance:</b>\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add via bKash", callback_data="pay_method_bkash", icon_custom_emoji_id=em_id("bkash"), style="success")],
        [InlineKeyboardButton(text="Add via Nagad", callback_data="pay_method_nagad", icon_custom_emoji_id=em_id("nagad"), style="success")],
        [InlineKeyboardButton(text="Transaction History", callback_data="wallet_history", icon_custom_emoji_id=em_id("history"), style="primary")],
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=em_id("back"), style="danger")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("pay_method_"))
async def pay_method_select(call: CallbackQuery, state: FSMContext):
    method = call.data.split("_")[2]
    number = get_setting(f"{method}_number", "")
    
    if not number:
        await call.answer(f"⚠️ Admin has not configured {method.upper()} yet.", show_alert=True)
        return

    masked = mask_number(number)
    await state.update_data(pay_method=method)
    await state.set_state(UserStates.waiting_payment_amount)
    
    text = (
        f"{em(method)} <b><u>{method.upper()} Payment</u></b> {em(method)}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"📱 <b>Number:</b> <code>{number}</code>\n"
        f"<i>(Masked: {masked})</i>\n\n"
        f"{em('info_icon')} Send Money (Personal) to the number above.\n"
        f"Then enter the <b>Amount</b> you sent (e.g. 100):"
    )
    await call.message.edit_text(text, reply_markup=back_kb("menu_wallet"), parse_mode='HTML')

@dp.message(UserStates.waiting_payment_amount)
async def pay_amount_received(m: Message, state: FSMContext):
    try:
        amount = float(m.text)
        if amount < MIN_ADD_BALANCE:
            await m.answer(f"❌ Minimum deposit is {fmt(MIN_ADD_BALANCE)}.")
            return
    except ValueError:
        await m.answer("❌ Invalid amount.")
        return

    await state.update_data(pay_amount=amount)
    await state.set_state(UserStates.waiting_payment_txn)
    await m.answer(f"{em('check_icon')} Amount set: {fmt(amount)}\n\nNow enter the <b>Transaction ID (TrxID)</b>:")

@dp.message(UserStates.waiting_payment_txn)
async def pay_txn_received(m: Message, state: FSMContext):
    txn = m.text.strip().upper()
    if len(txn) < 5:
        await m.answer("❌ Invalid TrxID.")
        return
    
    if db_query("SELECT * FROM banned_txns WHERE txn_id=?", (txn,), fetchone=True):
        db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (m.from_user.id,))
        await m.answer("🚫 Fraud attempt detected. You have been banned.")
        await state.clear()
        return

    if db_query("SELECT * FROM payments WHERE txn_id=?", (txn,), fetchone=True):
        await m.answer("❌ This TrxID has already been submitted.")
        return

    await state.update_data(pay_txn=txn)
    await state.set_state(UserStates.waiting_payment_sender)
    await m.answer(f"{em('check_icon')} TrxID saved: <code>{txn}</code>\n\nFinally, enter your <b>Sender Number</b> (11 digits):")

@dp.message(UserStates.waiting_payment_sender)
async def pay_sender_received(m: Message, state: FSMContext):
    sender = m.text.strip()
    if not re.fullmatch(r"01\d{9}", sender):
        await m.answer("❌ Invalid number. Must be 11 digits starting with 01.")
        return

    data = await state.get_data()
    method = data['pay_method']
    amount = data['pay_amount']
    txn = data['pay_txn']
    uid = m.from_user.id

    db_query("INSERT INTO payments (user_id, amount, method, txn_id, sender_number, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
        (uid, amount, method, txn, sender, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    r = db_query("SELECT id FROM payments WHERE txn_id=? ORDER BY id DESC LIMIT 1", (txn,), fetchone=True)
    pid = r[0] if r else 0

    await state.clear()
    await m.answer(
        f"{em('check_icon')} <b>Payment Submitted!</b>\n\n"
        f"💵 Amount: {fmt(amount)}\n"
        f"📝 TrxID: <code>{txn}</code>\n"
        f"📱 Sender: {mask_number(sender)}\n"
        f"🆔 Payment ID: <b>#{pid}</b>\n\n"
        f"⏳ <b>Status: PENDING</b>\n"
        f"Admin will verify manually.",
        reply_markup=main_menu_kb(uid),
        parse_mode='HTML'
    )
    await notify_admin_payment(pid, uid, amount, method, txn, sender)

async def notify_admin_payment(pid: int, uid: int, amount: float, method: str, txn: str, sender: str):
    u = db_query("SELECT first_name, username FROM users WHERE user_id=?", (uid,), fetchone=True)
    name = u[0] if u else "Unknown"
    
    text = (
        f"{em('money_icon')} <b><u>NEW PAYMENT REQUEST</u></b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 <b>Payment ID:</b> #{pid}\n"
        f"👤 <b>User:</b> {name} (@{u[1] if u else 'None'})\n"
        f"🆔 <b>User ID:</b> <code>{uid}</code>\n\n"
        f"💵 <b>Amount:</b> {fmt(amount)}\n"
        f"💳 <b>Method:</b> {method.upper()}\n"
        f"📝 <b>TrxID:</b> <code>{txn}</code>\n"
        f"📱 <b>Sender:</b> {mask_number(sender)}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Approve", callback_data=f"pay_approve_{pid}", icon_custom_emoji_id=em_id("check_icon"), style="success"),
            InlineKeyboardButton(text="Reject", callback_data=f"pay_reject_{pid}", icon_custom_emoji_id=em_id("cross"), style="danger")
        ],
        [InlineKeyboardButton(text="Ban User (Fraud)", callback_data=f"pay_ban_{pid}", icon_custom_emoji_id=em_id("admin"), style="danger")]
    ])
    try:
        await bot.send_message(ADMIN_ID, text, reply_markup=kb, parse_mode='HTML')
    except Exception as e:
        logger.error(f"Admin notify error: {e}")

@dp.callback_query(F.data.startswith("pay_"))
async def admin_payment_action(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID:
        await call.answer("Unauthorized.", show_alert=True)
        return

    parts = call.data.split("_")
    action = parts[1]
    pid = int(parts[2])

    p = db_query("SELECT * FROM payments WHERE id=?", (pid,), fetchone=True)
    if not p or p[6] != "pending":
        await call.answer("Payment not found or already processed.", show_alert=True)
        return

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if action == "approve":
        db_query("UPDATE payments SET status='approved', reviewed_at=? WHERE id=?", (now, pid))
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (p[2], p[1]))
        await call.message.edit_text(f"✅ Payment #{pid} APPROVED.", reply_markup=admin_back_kb(), parse_mode='HTML')
        try: await bot.send_message(p[1], f"✅ <b>Payment Approved!</b>\nAmount: {fmt(p[2])}\nTrxID: {p[4]}\nYour balance has been updated.", parse_mode='HTML')
        except Exception: pass

    elif action == "reject":
        db_query("UPDATE payments SET status='rejected', reviewed_at=? WHERE id=?", (now, pid))
        await call.message.edit_text(f"❌ Payment #{pid} REJECTED.", reply_markup=admin_back_kb(), parse_mode='HTML')
        try: await bot.send_message(p[1], f"❌ <b>Payment Rejected</b>\nTrxID: {p[4]}\nPlease check the details and submit again.", parse_mode='HTML')
        except Exception: pass

    elif action == "ban":
        db_query("INSERT OR REPLACE INTO banned_txns (txn_id, user_id, reason, timestamp) VALUES (?, ?, ?, ?)", (p[4], p[1], "fraud", now))
        db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (p[1],))
        db_query("UPDATE payments SET status='rejected', reviewed_at=? WHERE id=?", (now, pid))
        await call.message.edit_text(f"🚫 User {p[1]} BANNED for fraud.", reply_markup=admin_back_kb(), parse_mode='HTML')
        try: await bot.send_message(p[1], "🚫 You have been BANNED for fraudulent payment activity.", parse_mode='HTML')
        except Exception: pass

@dp.callback_query(F.data == "wallet_history")
async def wallet_history(call: CallbackQuery):
    rows = db_query("SELECT id, amount, method, txn_id, status, created_at FROM payments WHERE user_id=? ORDER BY id DESC LIMIT 15", (call.from_user.id,), fetchall=True)
    if not rows:
        await call.message.edit_text("📜 No transactions found.", reply_markup=back_kb("menu_wallet"), parse_mode='HTML')
        return
    text = f"{em('history')} <b><u>TRANSACTION HISTORY</u></b>\n\n"
    for r in rows:
        ic = "✅" if r[4] == "approved" else "❌" if r[4] == "rejected" else "⏳"
        text += f"{ic} <b>#{r[0]}</b> • {fmt(r[1])} via {r[2].upper()}\n📝 <code>{r[3]}</code>\n📅 {r[5]}\n━━━━━━━━━━━━━━━━━━\n"
    await call.message.edit_text(text, reply_markup=back_kb("menu_wallet"), parse_mode='HTML')

# ==============================================================================
# 9. PROFILE / SUPPORT
# ==============================================================================
@dp.callback_query(F.data == "menu_profile")
async def show_profile(call: CallbackQuery):
    u = db_query("SELECT user_id, first_name, username, balance, total_hosted, joined_date, is_banned FROM users WHERE user_id=?", (call.from_user.id,), fetchone=True)
    if not u:
        await call.answer("Not found. /start again.")
        return
    status = "🔴 Banned" if u[6] else "🟢 Active"
    text = (
        f"{em('profile')} <b><u>MY PROFILE</u></b> {em('profile')}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"{em('grid_id')} <b>User ID:</b> <code>{u[0]}</code>\n"
        f"{em('name')} <b>Name:</b> {u[1]}\n"
        f"🔗 <b>Username:</b> @{u[2] or 'None'}\n\n"
        f"{em('wallet')} <b>Balance:</b> {fmt(safe_float(u[3]))}\n"
        f"{em('hosted_bot')} <b>Hosted Bots:</b> {u[4]}\n"
        f"📅 <b>Joined:</b> {u[5]}\n"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Add Balance", callback_data="menu_wallet", icon_custom_emoji_id=em_id("add_balance"), style="success")],
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=em_id("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "menu_support")
async def support_menu(call: CallbackQuery):
    tg = get_setting("support_telegram", "https://t.me/YourSupport")
    wa = get_setting("support_whatsapp", "https://wa.me/YourNumber")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Telegram Support", url=tg, style="primary")],
        [InlineKeyboardButton(text="WhatsApp Support", url=wa, style="primary")],
        [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=em_id("back"), style="danger")]
    ])
    await call.message.edit_text(f"{em('support')} <b><u>SUPPORT CENTER</u></b>\n\nContact us for help.", reply_markup=kb, parse_mode='HTML')

# ==============================================================================
# 10. MY BOTS & CONTROL
# ==============================================================================
@dp.callback_query(F.data == "menu_my_bots")
async def my_bots(call: CallbackQuery):
    rows = db_query("SELECT id, bot_name, status, pid FROM hosted_bots WHERE user_id=? ORDER BY id DESC", (call.from_user.id,), fetchall=True)
    if not rows:
        text = f"{em('hosted_bot')} <b>You haven't hosted any bots yet.</b>\n\nCost: {fmt(HOST_COST_PER_BOT)} per bot"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Host First Bot", callback_data="menu_host_new", icon_custom_emoji_id=em_id("upload"), style="success")],
            [InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=em_id("back"), style="danger")]
        ])
        await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in rows:
        alive = is_process_alive(r[3])
        dot = "🟢" if alive else "🔴"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{dot} {r[1]}", callback_data=f"mybot_{r[0]}", icon_custom_emoji_id=em_id("hosted_bot"), style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="BACK", callback_data="back_main", icon_custom_emoji_id=em_id("back"), style="danger")])
    await call.message.edit_text(f"{em('hosted_bot')} <b><u>MY HOSTED BOTS</u></b>\n\nSelect a bot to control:", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("mybot_"))
async def mybot_view(call: CallbackQuery):
    bid = int(call.data.split("_")[1])
    b = db_query("SELECT id, bot_name, main_file, status, pid, created_at FROM hosted_bots WHERE id=? AND user_id=?", (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Bot not found.", show_alert=True)
        return
    alive = is_process_alive(b[4])
    dot = "🟢 Running" if alive else "🔴 Stopped"
    
    # Get file list
    files = db_query("SELECT filename FROM bot_files WHERE bot_id=?", (bid,), fetchall=True)
    files_str = "\n".join([f"📄 {f[0]}" for f in files]) if files else "No files."

    text = (
        f"{em('hosted_bot')} <b><u>{b[1]}</u></b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 Bot ID: <code>{b[0]}</code>\n"
        f"📄 Main File: <code>{b[2]}</code>\n"
        f"📊 Status: <b>{dot}</b>\n"
        f"🆔 PID: <code>{b[4] if alive else '-'}</code>\n"
        f"📅 Created: {b[5]}\n\n"
        f"📁 <b>Files:</b>\n{files_str}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Start", callback_data=f"bot_start_{bid}", icon_custom_emoji_id=em_id("play"), style="success"),
            InlineKeyboardButton(text="Stop", callback_data=f"bot_stop_{bid}", icon_custom_emoji_id=em_id("stop"), style="danger"),
        ],
        [
            InlineKeyboardButton(text="Restart", callback_data=f"bot_restart_{bid}", icon_custom_emoji_id=em_id("refresh"), style="primary"),
            InlineKeyboardButton(text="Logs", callback_data=f"bot_logs_{bid}", icon_custom_emoji_id=em_id("info_icon"), style="primary"),
        ],
        [InlineKeyboardButton(text="Upload/Replace Files", callback_data=f"bot_files_{bid}", icon_custom_emoji_id=em_id("upload"), style="primary")],
        [InlineKeyboardButton(text="Delete Bot", callback_data=f"bot_delete_{bid}", icon_custom_emoji_id=em_id("delete"), style="danger")],
        [InlineKeyboardButton(text="BACK", callback_data="menu_my_bots", icon_custom_emoji_id=em_id("back"), style="danger")],
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("bot_start_"))
async def bot_start(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, main_file, pid FROM hosted_bots WHERE id=? AND user_id=?", (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if is_process_alive(b[2]):
        await call.answer("Already running.", show_alert=True)
        return
    await call.message.edit_text("⚡ <b>Starting bot...</b>", parse_mode='HTML')
    ok, msg, pid = start_bot_process(bid, b[1])
    if ok:
        db_query("UPDATE hosted_bots SET status='running', pid=?, last_run_at=? WHERE id=?", (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
        await call.message.edit_text(f"✅ <b>Started!</b>\nPID: <code>{pid}</code>", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')
    else:
        await call.message.edit_text(f"❌ <b>Failed:</b>\n<code>{msg}</code>", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')

@dp.callback_query(F.data.startswith("bot_stop_"))
async def bot_stop(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, pid FROM hosted_bots WHERE id=? AND user_id=?", (bid, call.from_user.id), fetchone=True)
    if not b or not is_process_alive(b[1]):
        await call.answer("Not running.", show_alert=True)
        return
    stop_bot_process(b[1])
    db_query("UPDATE hosted_bots SET status='stopped', pid=0 WHERE id=?", (bid,))
    await call.answer("⏹ Stopped.", show_alert=True)
    await mybot_view(call)

@dp.callback_query(F.data.startswith("bot_restart_"))
async def bot_restart(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, main_file, pid FROM hosted_bots WHERE id=? AND user_id=?", (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if is_process_alive(b[2]):
        stop_bot_process(b[2])
        await asyncio.sleep(1)
    ok, msg, pid = start_bot_process(bid, b[1])
    if ok:
        db_query("UPDATE hosted_bots SET status='running', pid=?, last_run_at=? WHERE id=?", (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
        await call.answer(f"✅ Restarted (PID {pid})", show_alert=True)
    else:
        await call.answer(f"❌ {msg}", show_alert=True)
    await mybot_view(call)

@dp.callback_query(F.data.startswith("bot_logs_"))
async def bot_logs(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    logs = tail_log(bid, 40)
    if len(logs) > 3500: logs = logs[-3500:]
    await call.message.edit_text(f"📋 <b>Last 40 lines:</b>\n<pre>{logs}</pre>", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')

@dp.callback_query(F.data.startswith("bot_delete_"))
async def bot_delete(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT id, pid FROM hosted_bots WHERE id=? AND user_id=?", (bid, call.from_user.id), fetchone=True)
    if not b:
        await call.answer("Not found.", show_alert=True)
        return
    if is_process_alive(b[1]): stop_bot_process(b[1])
    folder = bot_folder(bid)
    if os.path.exists(folder): shutil.rmtree(folder, ignore_errors=True)
    db_query("DELETE FROM hosted_bots WHERE id=?", (bid,))
    db_query("DELETE FROM bot_files WHERE bot_id=?", (bid,))
    await call.answer("🗑 Deleted.", show_alert=True)
    await my_bots(call)

# ==============================================================================
# 11. HOST NEW BOT (With 10 Taka Bonus Logic)
# ==============================================================================
@dp.callback_query(F.data == "menu_host_new")
async def host_new_start(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    u = db_query("SELECT balance, total_hosted FROM users WHERE user_id=?", (uid,), fetchone=True)
    bal = safe_float(u[0]) if u else 0
    hosted = u[1] if u else 0

    # 10 Taka Bonus logic for first time hosting
    if hosted == 0 and bal < HOST_COST_PER_BOT:
        db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (SIGNUP_BONUS_POINTS, uid))
        await call.answer(f"🎁 Welcome Bonus! {fmt(SIGNUP_BONUS_POINTS)} added to your wallet.", show_alert=True)
        u = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)
        bal = safe_float(u[0]) if u else 0

    if bal < HOST_COST_PER_BOT:
        await call.message.edit_text(f"❌ <b>Insufficient Balance</b>\nYou need {fmt(HOST_COST_PER_BOT)}.", reply_markup=back_kb("menu_wallet"), parse_mode='HTML')
        return

    await state.set_state(UserStates.waiting_bot_name)
    await call.message.edit_text(f"{em('upload')} <b>Step 1:</b> Enter a name for your bot:", reply_markup=back_kb("menu_host_new"), parse_mode='HTML')

@dp.message(UserStates.waiting_bot_name)
async def host_bot_name(m: Message, state: FSMContext):
    await state.update_data(bot_name=m.text.strip()[:60])
    await state.set_state(UserStates.waiting_bot_files)
    await m.answer(
        f"✅ Name saved.\n\n<b>Step 2:</b> Upload your bot files.\n\n"
        f"📦 You can upload a <b>.zip</b> file OR individual files (Python, PHP, JS, etc.).\n"
        f"⚙️ Python files will auto-install missing dependencies.\n\n"
        f"When done, send <b>/done</b>",
        reply_markup=back_kb("back_main"), parse_mode='HTML'
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
    fname = os.path.basename(doc.file_name or "file.bin")
    file_path = os.path.join(folder_tmp, fname)

    try:
        file = await bot.get_file(doc.file_id)
        await bot.download_file(file.file_path, file_path)
    except Exception as e:
        await m.answer(f"❌ Download failed: {e}")
        return

    if fname.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(file_path, 'r') as zf:
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(folder_tmp, member))
                    if not member_path.startswith(os.path.realpath(folder_tmp) + os.sep): continue
                    zf.extract(member, folder_tmp)
            os.remove(file_path)
            await m.answer(f"✅ ZIP extracted.")
        except Exception as e:
            await m.answer(f"❌ ZIP failed: {e}")
    else:
        await m.answer(f"📥 Saved: <code>{fname}</code>")

@dp.message(UserStates.waiting_bot_files, Command("done"))
async def host_bot_done(m: Message, state: FSMContext):
    data = await state.get_data()
    tmp = data.get("tmp_folder")
    bot_name = data.get("bot_name", "Unnamed")
    if not tmp or not os.path.isdir(tmp):
        await m.answer("❌ No files uploaded. Send files first or /cancel.", reply_markup=back_kb())
        return

    files = [f for f in os.listdir(tmp) if os.path.isfile(os.path.join(tmp, f))]
    if not files:
        await m.answer("❌ No files found.")
        return

    main_file = None
    for candidate in ["main.py", "bot.py", "app.py", "index.py", "index.php", "index.js"]:
        if candidate in files:
            main_file = candidate
            break

    if not main_file:
        py_files = [f for f in files if f.endswith((".py", ".php", ".js"))]
        if len(py_files) == 1:
            main_file = py_files[0]
        else:
            await state.update_data(pending_main_choice=True)
            await state.set_state(UserStates.waiting_bot_main_file)
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f, callback_data=f"mainfile_{f}", style="primary")] for f in py_files])
            await m.answer("📄 Multiple executable files found. Choose the MAIN file:", reply_markup=kb)
            return

    await _finalize_host(m, state, tmp, bot_name, main_file)

@dp.callback_query(F.data.startswith("mainfile_"), UserStates.waiting_bot_main_file)
async def host_mainfile_choose(call: CallbackQuery, state: FSMContext):
    main_file = call.data.split("mainfile_", 1)[1]
    data = await state.get_data()
    tmp = data.get("tmp_folder")
    bot_name = data.get("bot_name", "Unnamed")
    await call.message.edit_text(f"✅ Main: <code>{main_file}</code>\n\n⚡ Processing...", parse_mode='HTML')
    await _finalize_host(call.message, state, tmp, bot_name, main_file)

async def _finalize_host(m: Message, state: FSMContext, tmp: str, bot_name: str, main_file: str):
    uid = m.chat.id
    u = db_query("SELECT balance FROM users WHERE user_id=?", (uid,), fetchone=True)
    bal = safe_float(u[0]) if u else 0
    if bal < HOST_COST_PER_BOT:
        await m.answer(f"❌ Insufficient balance.")
        await state.clear()
        return

    db_query("INSERT INTO hosted_bots (user_id, bot_name, main_file, folder, status, pid, created_at) VALUES (?, ?, ?, '', 'stopped', 0, ?)", (uid, bot_name, main_file, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    r = db_query("SELECT id FROM hosted_bots WHERE user_id=? ORDER BY id DESC LIMIT 1", (uid,), fetchone=True)
    bid = r[0]
    final_folder = bot_folder(bid)
    
    if os.path.exists(final_folder): shutil.rmtree(final_folder)
    shutil.move(tmp, final_folder)
    db_query("UPDATE hosted_bots SET folder=? WHERE id=?", (final_folder, bid))

    for f in os.listdir(final_folder):
        fp = os.path.join(final_folder, f)
        if os.path.isfile(fp):
            db_query("INSERT INTO bot_files (bot_id, filename, size_bytes, uploaded_at) VALUES (?, ?, ?, ?)", (bid, f, os.path.getsize(fp), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    db_query("UPDATE users SET balance = balance - ?, total_hosted = total_hosted + 1 WHERE user_id=?", (HOST_COST_PER_BOT, uid))

    await m.answer("⚡ <b>Installing dependencies...</b>", parse_mode='HTML')
    ok, log = await install_requirements(final_folder, main_file)

    await m.answer("⚡ <b>Starting bot...</b>", parse_mode='HTML')
    s_ok, s_msg, pid = start_bot_process(bid, main_file)
    
    if s_ok:
        db_query("UPDATE hosted_bots SET status='running', pid=?, last_run_at=? WHERE id=?", (pid, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), bid))
        await m.answer(f"✅ <b>Hosted Successfully!</b>\nBot ID: <code>{bid}</code>\nPID: <code>{pid}</code>", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')
    else:
        await m.answer(f"❌ <b>Start failed:</b>\n<code>{s_msg}</code>", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')

    log_activity(uid, "BOT_HOSTED", f"bid={bid} main={main_file}")
    await state.clear()

# ==============================================================================
# 12. FILE REPLACE
# ==============================================================================
@dp.callback_query(F.data.startswith("bot_files_"))
async def bot_files_menu(call: CallbackQuery, state: FSMContext):
    bid = int(call.data.split("_")[2])
    await state.update_data(replace_bot_id=bid)
    await state.set_state(UserStates.waiting_file_replace)
    await call.message.edit_text(f"📤 <b>Upload Files</b> for Bot #{bid}\n\nSend files or .zip. Send /done when finished.", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')

@dp.message(UserStates.waiting_file_replace, F.document)
async def bot_files_receive(m: Message, state: FSMContext):
    data = await state.get_data()
    bid = data.get("replace_bot_id")
    b = db_query("SELECT folder FROM hosted_bots WHERE id=? AND user_id=?", (bid, m.from_user.id), fetchone=True)
    if not b: return
    
    folder = b[0]
    fname = os.path.basename(m.document.file_name or "file.bin")
    path = os.path.join(folder, fname)
    
    try:
        file = await bot.get_file(m.document.file_id)
        await bot.download_file(file.file_path, path)
    except Exception as e:
        await m.answer(f"❌ Failed: {e}")
        return

    if fname.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                for member in zf.namelist():
                    member_path = os.path.realpath(os.path.join(folder, member))
                    if not member_path.startswith(os.path.realpath(folder) + os.sep): continue
                    zf.extract(member, folder)
            os.remove(path)
            await m.answer("✅ ZIP extracted.")
        except Exception as e:
            await m.answer(f"❌ ZIP failed: {e}")
    else:
        await m.answer(f"✅ Saved: <code>{fname}</code>")

@dp.message(UserStates.waiting_file_replace, Command("done"))
async def bot_files_done(m: Message, state: FSMContext):
    data = await state.get_data()
    bid = data.get("replace_bot_id")
    await state.clear()
    await m.answer("✅ Files updated. You can restart the bot.", reply_markup=back_kb(f"mybot_{bid}"), parse_mode='HTML')

# ==============================================================================
# 13. ADMIN PANEL
# ==============================================================================
@dp.message(Command("admin"))
async def admin_panel_cmd(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.clear()
    await message.answer("⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_panel")
async def admin_panel_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.clear()
    await call.message.edit_text("⚙️ <b>ADMIN PANEL</b>", reply_markup=admin_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_toggle_bot")
async def admin_toggle_bot(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    cur = get_setting("bot_status", "ON")
    new = "OFF" if cur == "ON" else "ON"
    set_setting("bot_status", new)
    await call.message.edit_reply_markup(reply_markup=admin_kb())
    await call.answer(f"Bot status: {new}")

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    users = db_query("SELECT COUNT(*) FROM users", fetchone=True)[0]
    hosted = db_query("SELECT COUNT(*) FROM hosted_bots", fetchone=True)[0]
    pend = db_query("SELECT COUNT(*) FROM payments WHERE status='pending'", fetchone=True)[0]
    rev = db_query("SELECT COALESCE(SUM(amount),0) FROM payments WHERE status='approved'", fetchone=True)[0]
    text = f"📊 <b>STATISTICS</b>\n\n👥 Users: {users}\n🤖 Hosted Bots: {hosted}\n⏳ Pending Payments: {pend}\n💰 Revenue: {fmt(safe_float(rev))}"
    await call.message.edit_text(text, reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.callback_query(F.data == "admin_pending_payments")
async def admin_pending_payments(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    rows = db_query("SELECT id, user_id, amount, method, txn_id, sender_number, created_at FROM payments WHERE status='pending' ORDER BY id ASC", fetchall=True)
    if not rows:
        await call.message.edit_text("✅ No pending payments.", reply_markup=admin_back_kb(), parse_mode='HTML')
        return
    await call.message.edit_text(f"⏳ {len(rows)} pending payments:", reply_markup=admin_back_kb(), parse_mode='HTML')
    for r in rows[:10]:
        text = f"🆔 <b>Payment #{r[0]}</b>\n👤 <code>{r[1]}</code>\n💵 {fmt(r[2])} via {r[3].upper()}\n📝 <code>{r[4]}</code>\n📱 {mask_number(r[5])}"
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Approve", callback_data=f"pay_approve_{r[0]}", style="success"), InlineKeyboardButton(text="Reject", callback_data=f"pay_reject_{r[0]}", style="danger")], [InlineKeyboardButton(text="Ban", callback_data=f"pay_ban_{r[0]}", style="danger")]])
        await call.message.answer(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data == "admin_set_bkash")
async def admin_set_bkash(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    cur = get_setting("bkash_number", "Not set")
    await call.message.edit_text(f"💳 Current bKash: <code>{cur}</code>\n\nSend new bKash number:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.waiting_bkash)

@dp.message(AdminStates.waiting_bkash)
async def admin_save_bkash(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    set_setting("bkash_number", m.text.strip())
    await m.answer("✅ bKash number set.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_set_nagad")
async def admin_set_nagad(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    cur = get_setting("nagad_number", "Not set")
    await call.message.edit_text(f"💳 Current Nagad: <code>{cur}</code>\n\nSend new Nagad number:", reply_markup=admin_back_kb(), parse_mode='HTML')
    await state.set_state(AdminStates.waiting_nagad)

@dp.message(AdminStates.waiting_nagad)
async def admin_save_nagad(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    set_setting("nagad_number", m.text.strip())
    await m.answer("✅ Nagad number set.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_user_control")
async def admin_user_control(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.waiting_user_lookup)
    await call.message.edit_text("👥 Send User ID or @username to look up:", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.message(AdminStates.waiting_user_lookup)
async def admin_user_lookup(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID: return
    target = m.text.strip().lstrip("@")
    u = db_query("SELECT user_id, first_name, username, balance, total_hosted, is_banned FROM users WHERE user_id=? OR username=? COLLATE NOCASE", (target, target), fetchone=True)
    if not u:
        await m.answer("❌ Not found.", reply_markup=admin_back_kb())
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Money", callback_data=f"u_add_{u[0]}", style="success"), InlineKeyboardButton(text="➖ Minus Money", callback_data=f"u_minus_{u[0]}", style="danger")],
        [InlineKeyboardButton(text=("✅ Unban" if u[5] else "🚫 Ban"), callback_data=f"u_{'unban' if u[5] else 'ban'}_{u[0]}", style="danger")],
        [InlineKeyboardButton(text="Back to Admin", callback_data="admin_panel", icon_custom_emoji_id=em_id("back"), style="danger")]
    ])
    await m.answer(f"👤 <b>User #{u[0]}</b>\nName: {u[1]}\nUsername: @{u[2] or 'None'}\n💰 Balance: {fmt(u[3])}\n🤖 Hosted: {u[4]}", reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("u_ban_"))
async def admin_ban_user(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    db_query("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
    await call.answer("🚫 Banned.", show_alert=True)

@dp.callback_query(F.data.startswith("u_unban_"))
async def admin_unban_user(call: CallbackQuery):
    uid = int(call.data.split("_")[2])
    db_query("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
    await call.answer("✅ Unbanned.", show_alert=True)

@dp.callback_query(F.data.startswith("u_add_"))
async def admin_add_money_prompt(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split("_")[2])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminStates.waiting_add_money)
    await call.message.edit_text(f"➕ Enter amount to add:", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.message(AdminStates.waiting_add_money)
async def admin_add_money_do(m: Message, state: FSMContext):
    try: amt = float(m.text)
    except ValueError: return await m.answer("❌ Invalid.")
    uid = (await state.get_data())["target_uid"]
    db_query("UPDATE users SET balance = balance + ? WHERE user_id=?", (amt, uid))
    await m.answer(f"✅ Added {fmt(amt)}.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data.startswith("u_minus_"))
async def admin_minus_money_prompt(call: CallbackQuery, state: FSMContext):
    uid = int(call.data.split("_")[2])
    await state.update_data(target_uid=uid)
    await state.set_state(AdminStates.waiting_minus_money)
    await call.message.edit_text(f"➖ Enter amount to deduct:", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.message(AdminStates.waiting_minus_money)
async def admin_minus_money_do(m: Message, state: FSMContext):
    try: amt = float(m.text)
    except ValueError: return await m.answer("❌ Invalid.")
    uid = (await state.get_data())["target_uid"]
    db_query("UPDATE users SET balance = balance - ? WHERE user_id=?", (amt, uid))
    await m.answer(f"✅ Deducted {fmt(amt)}.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_start(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.waiting_broadcast)
    await call.message.edit_text("📢 Send the message to broadcast:", reply_markup=admin_back_kb(), parse_mode='HTML')

@dp.message(AdminStates.waiting_broadcast)
async def admin_broadcast_do(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    users = db_query("SELECT user_id FROM users", fetchall=True) or []
    status = await message.answer("⏳ Broadcasting...", parse_mode='HTML')
    sent = 0
    for u in users:
        try:
            await message.send_copy(chat_id=u[0])
            sent += 1
        except Exception: pass
        await asyncio.sleep(0.05)
    await status.edit_text(f"✅ Broadcast done to {sent} users.", reply_markup=admin_kb(), parse_mode='HTML')
    await state.clear()

@dp.callback_query(F.data == "admin_all_bots")
async def admin_all_bots(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return
    rows = db_query("SELECT id, user_id, bot_name, pid FROM hosted_bots ORDER BY id DESC", fetchall=True)
    if not rows:
        return await call.message.edit_text("No bots.", reply_markup=admin_back_kb())
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for r in rows:
        alive = is_process_alive(r[3])
        dot = "🟢" if alive else "🔴"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{dot} #{r[0]} {r[2]}", callback_data=f"admin_botview_{r[0]}", style="primary")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="Back", callback_data="admin_panel", icon_custom_emoji_id=em_id("back"), style="danger")])
    await call.message.edit_text("All Bots:", reply_markup=kb)

@dp.callback_query(F.data.startswith("admin_botview_"))
async def admin_botview(call: CallbackQuery):
    bid = int(call.data.split("_")[2])
    b = db_query("SELECT * FROM hosted_bots WHERE id=?", (bid,), fetchone=True)
    if not b: return
    alive = is_process_alive(b[6])
    
    files = db_query("SELECT filename FROM bot_files WHERE bot_id=?", (bid,), fetchall=True)
    files_str = "\n".join([f"📄 {f[0]}" for f in files]) if files else "No files."

    text = (
        f"🤖 <b>Bot ID:</b> <code>{b[0]}</code>\n"
        f"👤 <b>Owner:</b> <code>{b[1]}</code>\n"
        f"📛 <b>Name:</b> {b[2]}\n"
        f"📄 <b>Main File:</b> <code>{b[3]}</code>\n"
        f"📊 <b>Status:</b> {'🟢 Running' if alive else '🔴 Stopped'}\n"
        f"🆔 <b>PID:</b> <code>{b[6] if alive else '-'}</code>\n\n"
        f"📁 <b>Files:</b>\n{files_str}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Force Stop", callback_data=f"admin_force_stop_{bid}", icon_custom_emoji_id=em_id("stop"), style="danger")],
        [InlineKeyboardButton(text="Back", callback_data="admin_all_bots", icon_custom_emoji_id=em_id("back"), style="danger")]
    ])
    await call.message.edit_text(text, reply_markup=kb, parse_mode='HTML')

@dp.callback_query(F.data.startswith("admin_force_stop_"))
async def admin_force_stop(call: CallbackQuery):
    bid = int(call.data.split("_")[3])
    b = db_query("SELECT pid FROM hosted_bots WHERE id=?", (bid,), fetchone=True)
    if b and is_process_alive(b[0]):
        stop_bot_process(b[0])
        db_query("UPDATE hosted_bots SET status='stopped', pid=0 WHERE id=?", (bid,))
    await call.answer("⏹ Stopped.", show_alert=True)
    await admin_all_bots(call)

@dp.message(Command("cancel"))
async def cmd_cancel(m: Message, state: FSMContext):
    await state.clear()
    await m.answer("✅ Cancelled.", reply_markup=main_menu_kb(m.from_user.id))

# ==============================================================================
# 14. BOOT
# ==============================================================================
async def main():
    init_db()
    logger.info("DB initialized.")
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