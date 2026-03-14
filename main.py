import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler
)
from datetime import datetime, timedelta
import sqlite3
import qrcode
from io import BytesIO
import random
import string
import os

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== CONFIG ====================
BOT_TOKEN = "8717905432:AAF2tELENa6j-Iu-rqIhxfggZM1iDECvFYI"
ADMIN_IDS = [6480827931]
ADMIN_USERNAME = "onlinesoonhai"
DEFAULT_QR = "https://vipxofficial.in/payqr.jpg"
DEFAULT_UPI = "h9641729-1@okaxis"

MENU_BUTTONS = {"🛒 Products", "👤 Profile", "💳 Add Balance", "🔑 My Keys",
                "📜 History", "🗣️ Referral", "📞 Support", "💰 Reseller", "👑 Admin Panel"}

# ==================== DATABASE ====================
def init_db():
    conn = sqlite3.connect('bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY, username TEXT DEFAULT '', first_name TEXT DEFAULT '',
        balance INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0, is_reseller INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0, referred_by INTEGER DEFAULT 0,
        referral_earnings INTEGER DEFAULT 0, total_referrals INTEGER DEFAULT 0,
        joined_date TEXT, last_active TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS mods (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, platform TEXT,
        price_1d INTEGER DEFAULT 0, price_3d INTEGER DEFAULT 0,
        price_7d INTEGER DEFAULT 0, price_30d INTEGER DEFAULT 0,
        reseller_price_1d INTEGER DEFAULT 0, reseller_price_3d INTEGER DEFAULT 0,
        reseller_price_7d INTEGER DEFAULT 0, reseller_price_30d INTEGER DEFAULT 0,
        apk_file_id TEXT, description TEXT DEFAULT '', is_active INTEGER DEFAULT 1)''')
    c.execute('''CREATE TABLE IF NOT EXISTS keys (
        id INTEGER PRIMARY KEY AUTOINCREMENT, mod_id INTEGER, key_value TEXT,
        duration TEXT, max_uses INTEGER DEFAULT 1, current_uses INTEGER DEFAULT 0,
        created_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT UNIQUE, user_id INTEGER,
        mod_id INTEGER, key_id INTEGER, duration TEXT, amount INTEGER,
        screenshot_file_id TEXT, status TEXT DEFAULT 'pending',
        order_date TEXT, expiry_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT, deposit_id TEXT UNIQUE, user_id INTEGER,
        amount INTEGER, screenshot_file_id TEXT, status TEXT DEFAULT 'pending',
        deposit_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS reseller_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
        screenshot_file_id TEXT, status TEXT DEFAULT 'pending', request_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS qr_settings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, qr_url TEXT, upi_id TEXT, instructions TEXT)''')
    for k, v in {'reseller_fee': '500', 'referral_reward': '10'}.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    c.execute("SELECT COUNT(*) FROM qr_settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO qr_settings (qr_url, upi_id, instructions) VALUES (?, ?, ?)",
                  (DEFAULT_QR, DEFAULT_UPI, "Pay exact amount and send screenshot"))
    for aid in ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO users (user_id, is_admin, joined_date) VALUES (?, 1, ?)",
                  (aid, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (aid,))
    conn.commit()
    conn.close()

def gdb():
    return sqlite3.connect('bot.db')

def gsetting(key):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key=?", (key,))
    r = c.fetchone()
    conn.close()
    return r[0] if r else None

def ssetting(key, val):
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(val)))
    conn.commit()
    conn.close()

def gqr():
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT qr_url, upi_id, instructions FROM qr_settings ORDER BY id DESC LIMIT 1")
    r = c.fetchone()
    conn.close()
    return r or (DEFAULT_QR, DEFAULT_UPI, "Pay and send screenshot")

def gid(p='ORD'):
    return f'{p}-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def ibanned(uid):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT is_banned FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    conn.close()
    return r and r[0] == 1

def ireseller(uid):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT is_reseller FROM users WHERE user_id=?", (uid,))
    r = c.fetchone()
    conn.close()
    return r and r[0] == 1

DM = {'1d': '1 Day', '3d': '3 Days', '7d': '7 Days', '30d': '30 Days'}
DD = {'1d': 1, '3d': 3, '7d': 7, '30d': 30}

# ==================== KEYBOARDS ====================
def main_kb(uid):
    kb = [
        [KeyboardButton("🛒 Products"), KeyboardButton("👤 Profile")],
        [KeyboardButton("💳 Add Balance"), KeyboardButton("🔑 My Keys")],
        [KeyboardButton("📜 History"), KeyboardButton("🗣️ Referral")],
        [KeyboardButton("📞 Support"), KeyboardButton("💰 Reseller")],
    ]
    if uid in ADMIN_IDS:
        kb.append([KeyboardButton("👑 Admin Panel")])
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

def admin_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Product", callback_data="a_addmod"),
         InlineKeyboardButton("✏️ Edit Product", callback_data="a_editprod")],
        [InlineKeyboardButton("💰 Edit Price", callback_data="a_editprice"),
         InlineKeyboardButton("➖ Remove Product", callback_data="a_delmod")],
        [InlineKeyboardButton("🔑 Single Key", callback_data="a_skey"),
         InlineKeyboardButton("🔑 Bulk Key", callback_data="a_bkey")],
        [InlineKeyboardButton("🗑️ Remove Key", callback_data="a_delkey"),
         InlineKeyboardButton("📢 Broadcast", callback_data="a_bcast")],
        [InlineKeyboardButton("⏳ Orders", callback_data="a_orders"),
         InlineKeyboardButton("💳 Deposits", callback_data="a_deposits")],
        [InlineKeyboardButton("💰 Add Balance", callback_data="a_addbal"),
         InlineKeyboardButton("👥 Stats", callback_data="a_stats")],
        [InlineKeyboardButton("🚫 Ban", callback_data="a_ban"),
         InlineKeyboardButton("✅ Unban", callback_data="a_unban")],
        [InlineKeyboardButton("💎 Reseller Mgmt", callback_data="a_resmgmt"),
         InlineKeyboardButton("💎 Reseller Prices", callback_data="a_resprice")],
        [InlineKeyboardButton("📊 All Price Edit", callback_data="a_allprice"),
         InlineKeyboardButton("🔄 Change QR", callback_data="a_qr")],
        [InlineKeyboardButton("🔍 Check User", callback_data="a_check"),
         InlineKeyboardButton("💾 Backup", callback_data="a_backup")],
        [InlineKeyboardButton("💰 Reseller Fee", callback_data="a_setresfee"),
         InlineKeyboardButton("🗣️ Referral Pts", callback_data="a_setrefpts")],
        [InlineKeyboardButton("📁 Product Files", callback_data="a_files")],
    ])

# ==================== STATES ====================
(MAIN_MENU, PLATFORM, GAME, MOD_SELECT, DURATION, PAYMENT, SCREENSHOT,
 ADMIN_MENU, DEP_AMT, DEP_SS, RESELLER_SS,
 ADD_MOD_NAME, ADD_MOD_PLAT, ADD_MOD_P1, ADD_MOD_P3, ADD_MOD_P7, ADD_MOD_P30,
 ADD_MOD_DESC, ADD_MOD_APK,
 SK_MOD, SK_DUR, SK_VAL,
 BK_MOD, BK_DUR, BK_COUNT, BK_VAL,
 EP_SEL, EP_FIELD, EP_VAL,
 EPRICE_SEL, EPRICE_DUR, EPRICE_VAL,
 DEL_MOD, DEL_KEY,
 BAN_ID, UNBAN_ID, AB_USER, AB_AMT,
 BCAST, QR_URL_S, QR_UPI_S, QR_INST_S,
 CHECK_UID, RP_SEL, RP_DUR, RP_VAL,
 AP_PCT, SET_RESFEE, SET_REFPTS) = range(49)


# ==================== APPROVE / REJECT (works from any state) ====================
async def do_approve_order(order_id, context):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT user_id, mod_id, duration, amount FROM orders WHERE order_id=? AND status='pending'", (order_id,))
    order = c.fetchone()
    if not order:
        conn.close()
        return False, "Already processed"
    uid, mid, dur, amt = order
    c.execute("SELECT id, key_value FROM keys WHERE mod_id=? AND duration=? AND current_uses<max_uses LIMIT 1", (mid, dur))
    key = c.fetchone()
    if not key:
        conn.close()
        return False, "No keys available"
    kid, kval = key
    expiry = (datetime.now() + timedelta(days=DD[dur])).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE keys SET current_uses=current_uses+1 WHERE id=?", (kid,))
    c.execute("UPDATE orders SET status='approved', key_id=?, expiry_date=? WHERE order_id=?", (kid, expiry, order_id))
    conn.commit()
    conn.close()
    try:
        await context.bot.send_message(uid,
            f"✅ *Order Approved!*\n━━━━━━━━━━━━━━━━━━\n📦 `{order_id}`\n🔑 *Key:* `{kval}`\n⏱️ Expires: {expiry}\n━━━━━━━━━━━━━━━━━━",
            parse_mode='Markdown')
    except:
        pass
    return True, f"✅ Approved\nKey: `{kval}`"

async def do_reject_order(order_id, context):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT user_id FROM orders WHERE order_id=?", (order_id,))
    r = c.fetchone()
    if r:
        c.execute("UPDATE orders SET status='rejected' WHERE order_id=?", (order_id,))
        conn.commit()
        try:
            await context.bot.send_message(r[0], f"❌ *Order Rejected!*\n`{order_id}`\nContact @{ADMIN_USERNAME}", parse_mode='Markdown')
        except:
            pass
    conn.close()
    return True, f"❌ Rejected `{order_id}`"

async def do_approve_deposit(dep_id, context):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT user_id, amount FROM deposits WHERE deposit_id=? AND status='pending'", (dep_id,))
    r = c.fetchone()
    if not r:
        conn.close()
        return False, "Already processed"
    c.execute("UPDATE deposits SET status='approved' WHERE deposit_id=?", (dep_id,))
    c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (r[1], r[0]))
    conn.commit()
    conn.close()
    try:
        await context.bot.send_message(r[0], f"✅ *Deposit Approved!*\n💰 ₹{r[1]} added!", parse_mode='Markdown')
    except:
        pass
    return True, f"✅ Deposit approved ₹{r[1]}"

async def do_reject_deposit(dep_id, context):
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT user_id FROM deposits WHERE deposit_id=?", (dep_id,))
    r = c.fetchone()
    if r:
        c.execute("UPDATE deposits SET status='rejected' WHERE deposit_id=?", (dep_id,))
        conn.commit()
        try:
            await context.bot.send_message(r[0], f"❌ *Deposit Rejected!* Contact @{ADMIN_USERNAME}", parse_mode='Markdown')
        except:
            pass
    conn.close()
    return True, f"❌ Deposit rejected"

async def do_approve_reseller(uid, context):
    conn = gdb()
    c = conn.cursor()
    c.execute("UPDATE users SET is_reseller=1 WHERE user_id=?", (uid,))
    c.execute("UPDATE reseller_requests SET status='approved' WHERE user_id=? AND status='pending'", (uid,))
    conn.commit()
    conn.close()
    try:
        await context.bot.send_message(uid, "💎 *Congratulations! You are now a Reseller!*", parse_mode='Markdown')
    except:
        pass
    return True, f"✅ Reseller approved `{uid}`"

async def do_reject_reseller(uid, context):
    conn = gdb()
    c = conn.cursor()
    c.execute("UPDATE reseller_requests SET status='rejected' WHERE user_id=? AND status='pending'", (uid,))
    conn.commit()
    conn.close()
    try:
        await context.bot.send_message(uid, "❌ Reseller request rejected.")
    except:
        pass
    return True, f"❌ Reseller rejected `{uid}`"


# Fallback handler for approve/reject from any state
async def fallback_approve_reject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    ok, msg = False, ""

    if d.startswith("ordapp_"):
        ok, msg = await do_approve_order(d.replace("ordapp_", ""), context)
    elif d.startswith("ordrej_"):
        ok, msg = await do_reject_order(d.replace("ordrej_", ""), context)
    elif d.startswith("depapp_"):
        ok, msg = await do_approve_deposit(d.replace("depapp_", ""), context)
    elif d.startswith("deprej_"):
        ok, msg = await do_reject_deposit(d.replace("deprej_", ""), context)
    elif d.startswith("resapp_"):
        ok, msg = await do_approve_reseller(int(d.replace("resapp_", "")), context)
    elif d.startswith("resrej_"):
        ok, msg = await do_reject_reseller(int(d.replace("resrej_", "")), context)

    try:
        await q.edit_message_caption(caption=msg, parse_mode='Markdown')
    except:
        try:
            await q.edit_message_text(msg, parse_mode='Markdown')
        except:
            pass
    return ADMIN_MENU


# Fallback: back to main
async def fallback_back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.message.delete()
    except:
        pass
    return await send_main(update, context)

# Fallback: back to admin
async def fallback_back_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    try:
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━",
                                   parse_mode='Markdown', reply_markup=admin_kb())
    except:
        await q.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━",
                                    parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== SEND MAIN MENU ====================
async def send_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
    r = c.fetchone()
    bal = r[0] if r else 0
    conn.close()
    rr = gsetting('referral_reward') or '10'

    text = f"""👋 *Hello, {user.first_name}!*
Welcome to our store.

├ 🔑 Exclusive Game Keys Store
├ 👤 Personal Account Dashboard
├ 🔖 Easy Deposit & Fast Credits
├ 📄 Full Purchase & Order History
├ 🗣️ Earn ₹{rr} Per Referral
└ 💎 Apply for Reseller

━━━━━━━━━━━━━━━━━━
💰 *Balance:* ₹{bal}
━━━━━━━━━━━━━━━━━━"""
    await context.bot.send_message(user.id, text, parse_mode='Markdown', reply_markup=main_kb(user.id))
    return MAIN_MENU


# ==================== START ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if ibanned(user.id):
        await update.message.reply_text("🚫 You are banned.")
        return ConversationHandler.END

    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    is_new = c.fetchone() is None

    if is_new:
        ref = 0
        if context.args:
            try:
                ref = int(context.args[0])
                if ref == user.id:
                    ref = 0
            except:
                ref = 0
        c.execute("INSERT INTO users (user_id,username,first_name,is_admin,referred_by,joined_date,last_active) VALUES (?,?,?,?,?,?,?)",
                  (user.id, user.username or '', user.first_name or '', 1 if user.id in ADMIN_IDS else 0, ref,
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        if ref > 0:
            reward = int(gsetting('referral_reward') or 10)
            c.execute("UPDATE users SET balance=balance+?, referral_earnings=referral_earnings+?, total_referrals=total_referrals+1 WHERE user_id=?",
                      (reward, reward, ref))
            try:
                await context.bot.send_message(ref,
                    f"🗣️ *New Referral!*\n👤 {user.first_name} joined!\n💰 ₹{reward} added!", parse_mode='Markdown')
            except:
                pass
    else:
        c.execute("UPDATE users SET last_active=?, username=?, first_name=? WHERE user_id=?",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.username or '', user.first_name or '', user.id))
    conn.commit()
    conn.close()
    return await send_main(update, context)


# ==================== MAIN TEXT HANDLER ====================
async def main_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    user = update.effective_user

    if ibanned(user.id):
        await update.message.reply_text("🚫 Banned.")
        return ConversationHandler.END

    if t == "🛒 Products":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📱 Android", callback_data="plat_android")],
            [InlineKeyboardButton("🍎 iOS", callback_data="plat_ios")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
        ])
        await update.message.reply_text("📱 *Choose Platform:*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=kb)
        return PLATFORM

    elif t == "👤 Profile":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT joined_date,balance,is_admin,is_reseller,referral_earnings,total_referrals FROM users WHERE user_id=?", (user.id,))
        u = c.fetchone()
        c.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='approved'", (user.id,))
        orders = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM orders WHERE user_id=? AND status='approved' AND expiry_date>?",
                  (user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        active = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE user_id=? AND status='approved'", (user.id,))
        spent = c.fetchone()[0]
        conn.close()
        role = "👑 Admin" if u[2] else ("💎 Reseller" if u[3] else "👤 Customer")
        await update.message.reply_text(f"""👤 *Your Profile*
━━━━━━━━━━━━━━━━━━
🆔 *ID:* `{user.id}`
📝 @{user.username or 'N/A'} | {user.first_name}
🏷️ {role}
💰 Balance: ₹{u[1]} | Spent: ₹{spent}
🗣️ Referrals: {u[5]} (₹{u[4]})
📦 Orders: {orders} | 🔑 Active: {active}
📅 Joined: {u[0]}
━━━━━━━━━━━━━━━━━━""", parse_mode='Markdown')
        return MAIN_MENU

    elif t == "💳 Add Balance":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
        bal = c.fetchone()[0] or 0
        conn.close()
        await update.message.reply_text(f"💳 *Add Balance*\n━━━━━━━━━━━━━━━━━━\n💰 Current: ₹{bal}\n\n*Enter amount:*", parse_mode='Markdown')
        return DEP_AMT

    elif t == "🔑 My Keys":
        conn = gdb()
        c = conn.cursor()
        c.execute("""SELECT k.key_value, m.name, o.expiry_date FROM orders o
                     JOIN keys k ON o.key_id=k.id JOIN mods m ON o.mod_id=m.id
                     WHERE o.user_id=? AND o.status='approved' AND o.expiry_date>?""",
                  (user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        keys = c.fetchall()
        conn.close()
        if keys:
            msg = "🔑 *Active Keys:*\n━━━━━━━━━━━━━━━━━━\n\n"
            for k in keys:
                msg += f"📱 *{k[1]}*\n🔐 `{k[0]}`\n⏱️ {k[2]}\n\n"
        else:
            msg = "❌ No active keys."
        await update.message.reply_text(msg, parse_mode='Markdown')
        return MAIN_MENU

    elif t == "📜 History":
        conn = gdb()
        c = conn.cursor()
        c.execute("""SELECT m.name, o.duration, o.amount, o.status, o.order_date, o.order_id
                     FROM orders o JOIN mods m ON o.mod_id=m.id
                     WHERE o.user_id=? ORDER BY o.order_date DESC LIMIT 10""", (user.id,))
        orders = c.fetchall()
        conn.close()
        if orders:
            msg = "📜 *History:*\n━━━━━━━━━━━━━━━━━━\n\n"
            for o in orders:
                st = {"approved": "✅", "pending": "⏳", "rejected": "❌"}.get(o[3], "❓")
                msg += f"`{o[5]}` {st}\n📱 {o[0]} ({DM.get(o[1])}) ₹{o[2]}\n\n"
        else:
            msg = "❌ No orders."
        await update.message.reply_text(msg, parse_mode='Markdown')
        return MAIN_MENU

    elif t == "🗣️ Referral":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT referral_earnings, total_referrals FROM users WHERE user_id=?", (user.id,))
        r = c.fetchone()
        conn.close()
        reward = gsetting('referral_reward') or '10'
        bot_me = await context.bot.get_me()
        link = f"https://t.me/{bot_me.username}?start={user.id}"
        await update.message.reply_text(f"""🗣️ *Referral Program*
━━━━━━━━━━━━━━━━━━
💰 *₹{reward} per referral!*

🔗 *Your Link:*
`{link}`

👥 Referrals: {r[1] if r else 0}
💵 Earned: ₹{r[0] if r else 0}
💎 Per Refer: ₹{reward}
━━━━━━━━━━━━━━━━━━""", parse_mode='Markdown')
        return MAIN_MENU

    elif t == "📞 Support":
        await update.message.reply_text(f"📞 *Support*\n━━━━━━━━━━━━━━━━━━\n👤 @{ADMIN_USERNAME}\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown')
        return MAIN_MENU

    elif t == "💰 Reseller":
        if ireseller(user.id):
            await update.message.reply_text("✅ You are already a Reseller!")
            return MAIN_MENU
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT status FROM reseller_requests WHERE user_id=? AND status='pending'", (user.id,))
        if c.fetchone():
            conn.close()
            await update.message.reply_text("⏳ Request already pending.")
            return MAIN_MENU
        conn.close()
        fee = gsetting('reseller_fee') or '500'
        qr_url, upi_id, inst = gqr()
        try:
            await update.message.reply_photo(photo=qr_url,
                caption=f"💎 *Become Reseller*\n━━━━━━━━━━━━━━━━━━\n💰 Fee: ₹{fee}\n💳 UPI: `{upi_id}`\n\n📝 {inst}\n\n📸 *Pay ₹{fee} and send screenshot:*",
                parse_mode='Markdown')
        except:
            await update.message.reply_text(f"💎 Fee: ₹{fee}\n💳 UPI: `{upi_id}`\n📸 Send screenshot:", parse_mode='Markdown')
        context.user_data['res_fee'] = int(fee)
        return RESELLER_SS

    elif t == "👑 Admin Panel":
        if user.id not in ADMIN_IDS:
            await update.message.reply_text("❌ Unauthorized!")
            return MAIN_MENU
        await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU

    return MAIN_MENU


# ==================== DEPOSIT FLOW ====================
async def dep_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS:
        return await main_text(update, context)
    try:
        amt = int(update.message.text)
        if amt <= 0: raise ValueError
        context.user_data['dep_amt'] = amt
    except:
        await update.message.reply_text("❌ Enter valid amount:")
        return DEP_AMT
    qr_url, upi_id, inst = gqr()
    try:
        await update.message.reply_photo(photo=qr_url,
            caption=f"💰 *Pay ₹{amt}*\n━━━━━━━━━━━━━━━━━━\n💳 UPI: `{upi_id}`\n\n📝 {inst}\n\n📸 *Send screenshot:*",
            parse_mode='Markdown')
    except:
        await update.message.reply_text(f"💰 Pay ₹{amt}\n💳 UPI: `{upi_id}`\n📸 Send screenshot:", parse_mode='Markdown')
    return DEP_SS

async def dep_ss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Send a photo.")
        return DEP_SS
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    amt = context.user_data.get('dep_amt', 0)
    did = gid('DEP')
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT INTO deposits (deposit_id,user_id,amount,screenshot_file_id,deposit_date) VALUES (?,?,?,?,?)",
              (did, user.id, amt, photo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_photo(aid, photo=photo,
                caption=f"💳 *Deposit*\n━━━━━━━━━━━━━━━━━━\n🆔 `{did}`\n👤 @{user.username} ({user.first_name})\n🆔 `{user.id}`\n💰 ₹{amt}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Approve", callback_data=f"depapp_{did}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"deprej_{did}")]]))
        except:
            pass
    await update.message.reply_text(f"✅ *Deposit submitted!*\n🆔 `{did}`\n⏳ Pending", parse_mode='Markdown')
    return await send_main(update, context)


# ==================== RESELLER SS ====================
async def reseller_ss(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Send a photo.")
        return RESELLER_SS
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    fee = context.user_data.get('res_fee', 500)
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT INTO reseller_requests (user_id,amount,screenshot_file_id,status,request_date) VALUES (?,?,?,'pending',?)",
              (user.id, fee, photo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_photo(aid, photo=photo,
                caption=f"💎 *Reseller Request*\n━━━━━━━━━━━━━━━━━━\n👤 @{user.username} ({user.first_name})\n🆔 `{user.id}`\n💰 ₹{fee}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Approve", callback_data=f"resapp_{user.id}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"resrej_{user.id}")]]))
        except:
            pass
    await update.message.reply_text("✅ *Reseller request submitted!*\n⏳ Admin will review.", parse_mode='Markdown')
    return await send_main(update, context)


# ==================== PRODUCT FLOW ====================
async def platform_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    if d == "back_main":
        try: await q.message.delete()
        except: pass
        return await send_main(update, context)
    context.user_data['platform'] = d.replace("plat_", "")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Free Fire", callback_data="game_ff")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
    await q.edit_message_text("🎮 *Choose Game:*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=kb)
    return GAME

async def game_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_main":
        try: await q.message.delete()
        except: pass
        return await send_main(update, context)
    plat = context.user_data.get('platform', 'android')
    uid = q.from_user.id
    res = ireseller(uid)
    conn = gdb()
    c = conn.cursor()
    pfx = "reseller_price" if res else "price"
    c.execute(f"SELECT id, name, {pfx}_1d, {pfx}_3d, {pfx}_7d, {pfx}_30d FROM mods WHERE platform=? AND is_active=1", (plat,))
    mods = c.fetchall()
    conn.close()
    if not mods:
        await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return GAME
    kb = []
    for m in mods:
        kb.append([InlineKeyboardButton(f"📱 {m[1]} | 1D:₹{m[2]} 3D:₹{m[3]} 7D:₹{m[4]} 30D:₹{m[5]}", callback_data=f"mod_{m[0]}")])
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    tag = "💎 Reseller" if res else "👤 Customer"
    await q.edit_message_text(f"📋 *Products ({tag}):*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    return MOD_SELECT

async def mod_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_main":
        try: await q.message.delete()
        except: pass
        return await send_main(update, context)
    mid = int(q.data.replace("mod_", ""))
    context.user_data['mod_id'] = mid
    uid = q.from_user.id
    res = ireseller(uid)
    conn = gdb()
    c = conn.cursor()
    pfx = "reseller_price" if res else "price"
    c.execute(f"SELECT name, {pfx}_1d, {pfx}_3d, {pfx}_7d, {pfx}_30d, description FROM mods WHERE id=?", (mid,))
    mod = c.fetchone()
    c.execute("SELECT duration, COALESCE(SUM(max_uses-current_uses),0) FROM keys WHERE mod_id=? AND current_uses<max_uses GROUP BY duration", (mid,))
    stock = dict(c.fetchall())
    conn.close()
    if not mod:
        await q.edit_message_text("❌ Not found!")
        return MAIN_MENU
    context.user_data['mod_name'] = mod[0]
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"1 Day - ₹{mod[1]} (Stock:{int(stock.get('1d',0))})", callback_data="dur_1d")],
        [InlineKeyboardButton(f"3 Days - ₹{mod[2]} (Stock:{int(stock.get('3d',0))})", callback_data="dur_3d")],
        [InlineKeyboardButton(f"7 Days - ₹{mod[3]} (Stock:{int(stock.get('7d',0))})", callback_data="dur_7d")],
        [InlineKeyboardButton(f"30 Days - ₹{mod[4]} (Stock:{int(stock.get('30d',0))})", callback_data="dur_30d")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
    await q.edit_message_text(f"📱 *{mod[0]}*\n━━━━━━━━━━━━━━━━━━\n{mod[5] or 'No description'}\n\n⏳ *Choose Duration:*",
                               parse_mode='Markdown', reply_markup=kb)
    return DURATION

async def dur_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_main":
        try: await q.message.delete()
        except: pass
        return await send_main(update, context)
    dur = q.data.replace("dur_", "")
    context.user_data['duration'] = dur
    uid = q.from_user.id
    res = ireseller(uid)
    mid = context.user_data['mod_id']
    conn = gdb()
    c = conn.cursor()
    pfx = "reseller_price" if res else "price"
    c.execute(f"SELECT {pfx}_{dur} FROM mods WHERE id=?", (mid,))
    price = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(max_uses-current_uses),0) FROM keys WHERE mod_id=? AND duration=? AND current_uses<max_uses", (mid, dur))
    stock = c.fetchone()[0]
    c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    bal = c.fetchone()[0] or 0
    conn.close()
    if stock <= 0:
        await q.edit_message_text("❌ *Out of stock!*", parse_mode='Markdown',
                                   reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
        return DURATION
    context.user_data['amount'] = price
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"💰 Balance (₹{bal})", callback_data="pay_bal")],
        [InlineKeyboardButton("💳 Pay UPI", callback_data="pay_upi")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
    await q.edit_message_text(f"""🛒 *Order Summary*
━━━━━━━━━━━━━━━━━━
📱 {context.user_data['mod_name']}
⏳ {DM.get(dur)} | 💰 ₹{price}
📦 Stock: {int(stock)} | 💳 Balance: ₹{bal}
━━━━━━━━━━━━━━━━━━""", parse_mode='Markdown', reply_markup=kb)
    return PAYMENT

async def payment_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    user = q.from_user
    if d == "back_main":
        try: await q.message.delete()
        except: pass
        return await send_main(update, context)

    mid = context.user_data.get('mod_id')
    dur = context.user_data.get('duration')
    amt = context.user_data.get('amount')

    if d == "pay_bal":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT balance FROM users WHERE user_id=?", (user.id,))
        bal = c.fetchone()[0] or 0
        if bal < amt:
            await q.edit_message_text(f"❌ *Low Balance!* ₹{bal} < ₹{amt}", parse_mode='Markdown',
                                       reply_markup=InlineKeyboardMarkup([
                                           [InlineKeyboardButton("💳 Add Balance", callback_data="back_main")],
                                           [InlineKeyboardButton("💳 Pay UPI", callback_data="pay_upi")]]))
            conn.close()
            return PAYMENT
        c.execute("SELECT id, key_value FROM keys WHERE mod_id=? AND duration=? AND current_uses<max_uses LIMIT 1", (mid, dur))
        key = c.fetchone()
        if not key:
            await q.edit_message_text("❌ Out of stock!")
            conn.close()
            return await send_main(update, context)
        kid, kval = key
        oid = gid('ORD')
        exp = (datetime.now() + timedelta(days=DD[dur])).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE users SET balance=balance-? WHERE user_id=?", (amt, user.id))
        c.execute("UPDATE keys SET current_uses=current_uses+1 WHERE id=?", (kid,))
        c.execute("INSERT INTO orders (order_id,user_id,mod_id,key_id,duration,amount,status,order_date,expiry_date) VALUES (?,?,?,?,?,?,'approved',?,?)",
                  (oid, user.id, mid, kid, dur, amt, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), exp))
        conn.commit()
        conn.close()
        await q.edit_message_text(f"""✅ *Purchase Successful!*
━━━━━━━━━━━━━━━━━━
📦 `{oid}`
📱 {context.user_data['mod_name']}
🔑 *Key:* `{kval}`
⏱️ Expires: {exp}
💰 Paid: ₹{amt} (Balance)
━━━━━━━━━━━━━━━━━━""", parse_mode='Markdown')
        return await send_main(update, context)

    elif d == "pay_upi":
        qr_url, upi_id, inst = gqr()
        try:
            await q.message.reply_photo(photo=qr_url,
                caption=f"💰 *Pay ₹{amt}*\n━━━━━━━━━━━━━━━━━━\n💳 UPI: `{upi_id}`\n\n📝 {inst}\n\n📸 *Send screenshot:*",
                parse_mode='Markdown')
        except:
            await q.message.reply_text(f"💰 Pay ₹{amt}\n💳 `{upi_id}`\n📸 Send screenshot:", parse_mode='Markdown')
        try: await q.message.delete()
        except: pass
        return SCREENSHOT
    return PAYMENT

async def screenshot_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Send photo.")
        return SCREENSHOT
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    mid = context.user_data.get('mod_id')
    dur = context.user_data.get('duration')
    amt = context.user_data.get('amount')
    oid = gid('ORD')
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT INTO orders (order_id,user_id,mod_id,duration,amount,screenshot_file_id,status,order_date) VALUES (?,?,?,?,?,?,'pending',?)",
              (oid, user.id, mid, dur, amt, photo, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    c.execute("SELECT name FROM mods WHERE id=?", (mid,))
    mname = c.fetchone()[0]
    conn.close()
    for aid in ADMIN_IDS:
        try:
            await context.bot.send_photo(aid, photo=photo,
                caption=f"🛒 *Order*\n━━━━━━━━━━━━━━━━━━\n📦 `{oid}`\n👤 @{user.username} ({user.first_name})\n🆔 `{user.id}`\n📱 {mname} ({DM.get(dur)})\n💰 ₹{amt}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Approve", callback_data=f"ordapp_{oid}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"ordrej_{oid}")]]))
        except:
            pass
    await update.message.reply_text(f"✅ *Order submitted!*\n📦 `{oid}`\n⏳ Pending", parse_mode='Markdown')
    return await send_main(update, context)


# ==================== ADMIN HANDLER ====================
async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    d = q.data
    if q.from_user.id not in ADMIN_IDS:
        await q.edit_message_text("❌ Unauthorized!")
        return MAIN_MENU

    # Handle approve/reject from admin state
    if d.startswith(("ordapp_", "ordrej_", "depapp_", "deprej_", "resapp_", "resrej_")):
        return await fallback_approve_reject(update, context)

    if d == "back_main":
        try: await q.message.delete()
        except: pass
        return await send_main(update, context)

    if d == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU

    # ===== PENDING ORDERS =====
    if d == "a_orders":
        conn = gdb()
        c = conn.cursor()
        c.execute("""SELECT o.order_id, u.username, u.first_name, m.name, o.duration,
                     o.amount, o.screenshot_file_id, o.user_id
                     FROM orders o JOIN users u ON o.user_id=u.user_id JOIN mods m ON o.mod_id=m.id
                     WHERE o.status='pending' ORDER BY o.order_date DESC""")
        orders = c.fetchall()
        conn.close()
        if not orders:
            await q.edit_message_text("✅ No pending orders!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        try: await q.message.delete()
        except: pass
        for o in orders:
            btns = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"ordapp_{o[0]}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"ordrej_{o[0]}")]])
            cap = f"📦 `{o[0]}`\n👤 @{o[1]} ({o[2]})\n🆔 `{o[7]}`\n📱 {o[3]} ({DM.get(o[4])})\n💰 ₹{o[5]}"
            if o[6]:
                try:
                    await q.message.chat.send_photo(photo=o[6], caption=cap, parse_mode='Markdown', reply_markup=btns)
                    continue
                except:
                    pass
            await context.bot.send_message(q.from_user.id, cap + "\n⚠️ No screenshot", parse_mode='Markdown', reply_markup=btns)
        await context.bot.send_message(q.from_user.id, "━━━━━━━━━━━━━━━━━━",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="back_admin")]]))
        return ADMIN_MENU

    # ===== PENDING DEPOSITS =====
    elif d == "a_deposits":
        conn = gdb()
        c = conn.cursor()
        c.execute("""SELECT d.deposit_id, u.username, u.first_name, d.amount,
                     d.screenshot_file_id, d.user_id
                     FROM deposits d JOIN users u ON d.user_id=u.user_id
                     WHERE d.status='pending' ORDER BY d.deposit_date DESC""")
        deps = c.fetchall()
        conn.close()
        if not deps:
            await q.edit_message_text("✅ No pending deposits!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        try: await q.message.delete()
        except: pass
        for dd in deps:
            btns = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"depapp_{dd[0]}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"deprej_{dd[0]}")]])
            cap = f"💳 `{dd[0]}`\n👤 @{dd[1]} ({dd[2]})\n🆔 `{dd[5]}`\n💰 ₹{dd[3]}"
            if dd[4]:
                try:
                    await context.bot.send_photo(q.from_user.id, photo=dd[4], caption=cap, parse_mode='Markdown', reply_markup=btns)
                    continue
                except:
                    pass
            await context.bot.send_message(q.from_user.id, cap, parse_mode='Markdown', reply_markup=btns)
        await context.bot.send_message(q.from_user.id, "━━━━━━━━━━━━━━━━━━",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="back_admin")]]))
        return ADMIN_MENU

    # ===== ADD MOD =====
    elif d == "a_addmod":
        await q.edit_message_text("📝 *Enter product name:*", parse_mode='Markdown')
        return ADD_MOD_NAME

    # ===== EDIT PRODUCT =====
    elif d == "a_editprod":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, name FROM mods WHERE is_active=1")
        mods = c.fetchall()
        conn.close()
        if not mods:
            await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        kb = [[InlineKeyboardButton(f"✏️ {m[1]}", callback_data=f"ep_{m[0]}")] for m in mods]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await q.edit_message_text("✏️ *Select product:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return EP_SEL

    # ===== EDIT PRICE =====
    elif d == "a_editprice":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, name, price_1d, price_3d, price_7d, price_30d FROM mods WHERE is_active=1")
        mods = c.fetchall()
        conn.close()
        if not mods:
            await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        kb = [[InlineKeyboardButton(f"💰 {m[1]} (₹{m[2]}/{m[3]}/{m[4]}/{m[5]})", callback_data=f"epr_{m[0]}")] for m in mods]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await q.edit_message_text("💰 *Select product:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return EPRICE_SEL

    # ===== REMOVE PRODUCT =====
    elif d == "a_delmod":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, name FROM mods WHERE is_active=1")
        mods = c.fetchall()
        conn.close()
        if not mods:
            await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        kb = [[InlineKeyboardButton(f"❌ {m[1]}", callback_data=f"dm_{m[0]}")] for m in mods]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await q.edit_message_text("🗑️ *Select to remove:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return DEL_MOD

    # ===== SINGLE KEY =====
    elif d == "a_skey":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, name FROM mods WHERE is_active=1")
        mods = c.fetchall()
        conn.close()
        if not mods:
            await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        kb = [[InlineKeyboardButton(m[1], callback_data=f"sk_{m[0]}")] for m in mods]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await q.edit_message_text("🔑 *Single Key (1 user) - Select product:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return SK_MOD

    # ===== BULK KEY =====
    elif d == "a_bkey":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, name FROM mods WHERE is_active=1")
        mods = c.fetchall()
        conn.close()
        if not mods:
            await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        kb = [[InlineKeyboardButton(m[1], callback_data=f"bk_{m[0]}")] for m in mods]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await q.edit_message_text("🔑 *Bulk Key (multi user) - Select product:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return BK_MOD

    # ===== REMOVE KEY =====
    elif d == "a_delkey":
        conn = gdb()
        c = conn.cursor()
        c.execute("""SELECT k.id, m.name, k.key_value, k.duration, k.max_uses, k.current_uses
                     FROM keys k JOIN mods m ON k.mod_id=m.id
                     WHERE k.current_uses<k.max_uses ORDER BY m.name LIMIT 20""")
        keys = c.fetchall()
        conn.close()
        if not keys:
            await q.edit_message_text("❌ No keys.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        try: await q.message.delete()
        except: pass
        for k in keys:
            left = k[4] - k[5]
            await context.bot.send_message(q.from_user.id,
                f"📱 {k[1]} ({DM.get(k[3])})\n🔑 `{k[2]}`\nSlots: {left}/{k[4]}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Delete", callback_data=f"dk_{k[0]}")]]))
        await context.bot.send_message(q.from_user.id, "━━━━━━━━━━━━━━━━━━",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="back_admin")]]))
        return DEL_KEY

    # ===== BROADCAST =====
    elif d == "a_bcast":
        await q.edit_message_text("📢 *Enter broadcast message:*", parse_mode='Markdown')
        return BCAST

    # ===== STATS =====
    elif d == "a_stats":
        conn = gdb()
        c = conn.cursor()
        st = {}
        for k, sq in [('users', "SELECT COUNT(*) FROM users"), ('admins', "SELECT COUNT(*) FROM users WHERE is_admin=1"),
                       ('resellers', "SELECT COUNT(*) FROM users WHERE is_reseller=1"), ('banned', "SELECT COUNT(*) FROM users WHERE is_banned=1"),
                       ('orders', "SELECT COUNT(*) FROM orders"), ('pending', "SELECT COUNT(*) FROM orders WHERE status='pending'"),
                       ('approved', "SELECT COUNT(*) FROM orders WHERE status='approved'"),
                       ('revenue', "SELECT COALESCE(SUM(amount),0) FROM orders WHERE status='approved'"),
                       ('products', "SELECT COUNT(*) FROM mods WHERE is_active=1"),
                       ('keys', "SELECT COALESCE(SUM(max_uses-current_uses),0) FROM keys WHERE current_uses<max_uses"),
                       ('pdep', "SELECT COUNT(*) FROM deposits WHERE status='pending'"),
                       ('tdep', "SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'")]:
            c.execute(sq)
            st[k] = c.fetchone()[0]
        conn.close()
        await q.edit_message_text(f"""📊 *Stats*
━━━━━━━━━━━━━━━━━━
👥 {st['users']} | 👑 {st['admins']} | 💎 {st['resellers']} | 🚫 {st['banned']}
📦 Orders: {st['orders']} | ⏳ {st['pending']} | ✅ {st['approved']}
💰 Revenue: ₹{st['revenue']} | 🔑 Keys: {st['keys']}
💳 PendDep: {st['pdep']} | 💵 Deposits: ₹{st['tdep']}
Reseller Fee: ₹{gsetting('reseller_fee')} | Referral: ₹{gsetting('referral_reward')}
━━━━━━━━━━━━━━━━━━""", parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
        return ADMIN_MENU

    # ===== BAN =====
    elif d == "a_ban":
        await q.edit_message_text("🚫 *Enter User ID to ban:*", parse_mode='Markdown')
        return BAN_ID
    elif d == "a_unban":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name FROM users WHERE is_banned=1")
        banned = c.fetchall()
        conn.close()
        msg = "🚫 *Banned:*\n"
        for b in banned:
            msg += f"`{b[0]}` @{b[1]} ({b[2]})\n"
        msg += "\n*Enter ID to unban:*" if banned else "\n✅ No banned users."
        await q.edit_message_text(msg, parse_mode='Markdown')
        if not banned:
            return ADMIN_MENU
        return UNBAN_ID

    # ===== ADD BALANCE =====
    elif d == "a_addbal":
        await q.edit_message_text("💰 *Enter User ID:*", parse_mode='Markdown')
        return AB_USER

    # ===== RESELLER MGMT =====
    elif d == "a_resmgmt":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT user_id, username, first_name FROM users WHERE is_reseller=1")
        resellers = c.fetchall()
        c.execute("""SELECT r.user_id, u.username, u.first_name, r.amount, r.screenshot_file_id
                     FROM reseller_requests r JOIN users u ON r.user_id=u.user_id WHERE r.status='pending'""")
        pending = c.fetchall()
        conn.close()
        msg = "💎 *Resellers:*\n━━━━━━━━━━━━━━━━━━\n"
        if resellers:
            for r in resellers:
                msg += f"✅ `{r[0]}` @{r[1]} ({r[2]})\n"
        else:
            msg += "None\n"

        if pending:
            try: await q.message.delete()
            except: pass
            await context.bot.send_message(q.from_user.id, msg, parse_mode='Markdown')
            for p in pending:
                btns = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅ Approve", callback_data=f"resapp_{p[0]}"),
                    InlineKeyboardButton("❌ Reject", callback_data=f"resrej_{p[0]}")]])
                cap = f"💎 *Pending*\n👤 @{p[1]} ({p[2]})\n🆔 `{p[0]}`\n💰 ₹{p[3]}"
                if p[4]:
                    try:
                        await context.bot.send_photo(q.from_user.id, photo=p[4], caption=cap, parse_mode='Markdown', reply_markup=btns)
                        continue
                    except:
                        pass
                await context.bot.send_message(q.from_user.id, cap, parse_mode='Markdown', reply_markup=btns)
        else:
            msg += "\nNo pending requests."
            kb = [
                [InlineKeyboardButton("➕ Make Reseller", callback_data="a_makeres"),
                 InlineKeyboardButton("➖ Remove Reseller", callback_data="a_rmres")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]
            await q.edit_message_text(msg, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return ADMIN_MENU

    elif d == "a_makeres":
        context.user_data['action'] = 'make_res'
        await q.edit_message_text("💎 *Enter User ID:*", parse_mode='Markdown')
        return CHECK_UID
    elif d == "a_rmres":
        context.user_data['action'] = 'rm_res'
        await q.edit_message_text("💎 *Enter User ID:*", parse_mode='Markdown')
        return CHECK_UID

    # ===== RESELLER PRICES =====
    elif d == "a_resprice":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, name, reseller_price_1d, reseller_price_3d, reseller_price_7d, reseller_price_30d FROM mods WHERE is_active=1")
        mods = c.fetchall()
        conn.close()
        if not mods:
            await q.edit_message_text("❌ No products.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        kb = [[InlineKeyboardButton(f"💎 {m[1]} (₹{m[2]}/{m[3]}/{m[4]}/{m[5]})", callback_data=f"rp_{m[0]}")] for m in mods]
        kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
        await q.edit_message_text("💎 *Reseller Prices:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
        return RP_SEL

    # ===== ALL PRICE EDIT =====
    elif d == "a_allprice":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Increase %", callback_data="a_apinc")],
            [InlineKeyboardButton("📉 Decrease %", callback_data="a_apdec")],
            [InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
        await q.edit_message_text("📊 *All Price Edit:*", parse_mode='Markdown', reply_markup=kb)
        return ADMIN_MENU
    elif d == "a_apinc":
        context.user_data['pdir'] = 'inc'
        await q.edit_message_text("📊 *Enter percentage (e.g. 10):*", parse_mode='Markdown')
        return AP_PCT
    elif d == "a_apdec":
        context.user_data['pdir'] = 'dec'
        await q.edit_message_text("📊 *Enter percentage (e.g. 10):*", parse_mode='Markdown')
        return AP_PCT

    # ===== QR =====
    elif d == "a_qr":
        await q.edit_message_text("🖼️ *Enter QR image URL:*", parse_mode='Markdown')
        return QR_URL_S

    # ===== CHECK USER =====
    elif d == "a_check":
        context.user_data['action'] = 'check'
        await q.edit_message_text("🔍 *Enter User ID:*", parse_mode='Markdown')
        return CHECK_UID

    # ===== BACKUP =====
    elif d == "a_backup":
        if os.path.exists('bot.db'):
            with open('bot.db', 'rb') as f:
                await q.message.reply_document(f, filename=f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db', caption="💾 Backup")
        await q.message.reply_text("━━━━━━━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
        return ADMIN_MENU

    # ===== SETTINGS =====
    elif d == "a_setresfee":
        f = gsetting('reseller_fee') or '500'
        await q.edit_message_text(f"💎 Current Fee: ₹{f}\n\n*Enter new fee:*", parse_mode='Markdown')
        return SET_RESFEE
    elif d == "a_setrefpts":
        p = gsetting('referral_reward') or '10'
        await q.edit_message_text(f"🗣️ Current: ₹{p}/ref\n\n*Enter new reward:*", parse_mode='Markdown')
        return SET_REFPTS

    # ===== PRODUCT FILES =====
    elif d == "a_files":
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT name, apk_file_id, description FROM mods WHERE apk_file_id IS NOT NULL AND is_active=1")
        files = c.fetchall()
        conn.close()
        if not files:
            await q.edit_message_text("❌ No files.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_admin")]]))
            return ADMIN_MENU
        try: await q.message.delete()
        except: pass
        for f in files:
            try:
                await context.bot.send_document(q.from_user.id, document=f[1],
                    caption=f"📱 *{f[0]}*\n{f[2] or ''}", parse_mode='Markdown')
            except:
                pass
        await context.bot.send_message(q.from_user.id, "━━━━━━━━━━━━━━━━━━",
                                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Admin Panel", callback_data="back_admin")]]))
        return ADMIN_MENU

    return ADMIN_MENU


# ==================== ADD MOD FLOW ====================
async def addmod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    context.user_data['nm'] = update.message.text
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Android", callback_data="mp_android")],
        [InlineKeyboardButton("🍎 iOS", callback_data="mp_ios")]])
    await update.message.reply_text("📱 *Platform:*", parse_mode='Markdown', reply_markup=kb)
    return ADD_MOD_PLAT

async def addmod_plat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data['mp'] = q.data.replace("mp_", "")
    await q.edit_message_text("💰 *1 Day price (₹):*", parse_mode='Markdown')
    return ADD_MOD_P1

async def addmod_p1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try: context.user_data['p1'] = int(update.message.text)
    except:
        await update.message.reply_text("❌ Number:")
        return ADD_MOD_P1
    await update.message.reply_text("💰 *3 Days price (₹):*", parse_mode='Markdown')
    return ADD_MOD_P3

async def addmod_p3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try: context.user_data['p3'] = int(update.message.text)
    except:
        await update.message.reply_text("❌ Number:")
        return ADD_MOD_P3
    await update.message.reply_text("💰 *7 Days price (₹):*", parse_mode='Markdown')
    return ADD_MOD_P7

async def addmod_p7(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try: context.user_data['p7'] = int(update.message.text)
    except:
        await update.message.reply_text("❌ Number:")
        return ADD_MOD_P7
    await update.message.reply_text("💰 *30 Days price (₹):*", parse_mode='Markdown')
    return ADD_MOD_P30

async def addmod_p30(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try: context.user_data['p30'] = int(update.message.text)
    except:
        await update.message.reply_text("❌ Number:")
        return ADD_MOD_P30
    await update.message.reply_text("📋 *Description (/skip):*", parse_mode='Markdown')
    return ADD_MOD_DESC

async def addmod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['desc'] = '' if update.message.text == '/skip' else update.message.text
    await update.message.reply_text("📁 *Upload APK (/skip):*", parse_mode='Markdown')
    return ADD_MOD_APK

async def addmod_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fid = None
    if update.message.document:
        fid = update.message.document.file_id
    elif update.message.text != '/skip':
        await update.message.reply_text("❌ Upload file or /skip")
        return ADD_MOD_APK
    d = context.user_data
    conn = gdb()
    c = conn.cursor()
    c.execute("""INSERT INTO mods (name,platform,price_1d,price_3d,price_7d,price_30d,
                 reseller_price_1d,reseller_price_3d,reseller_price_7d,reseller_price_30d,apk_file_id,description)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
              (d['nm'], d['mp'], d['p1'], d['p3'], d['p7'], d['p30'],
               d['p1'], d['p3'], d['p7'], d['p30'], fid, d['desc']))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ *Product added!*", parse_mode='Markdown')
    context.user_data.clear()
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== SINGLE KEY FLOW ====================
async def sk_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['sk_mod'] = int(q.data.replace("sk_", ""))
    kb = [[InlineKeyboardButton(DM[d], callback_data=f"skd_{d}")] for d in ['1d', '3d', '7d', '30d']]
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
    await q.edit_message_text("⏱️ *Duration:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    return SK_DUR

async def sk_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['sk_dur'] = q.data.replace("skd_", "")
    await q.edit_message_text("🔑 *Enter key (for 1 user):*", parse_mode='Markdown')
    return SK_VAL

async def sk_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    kv = update.message.text.strip()
    if not kv:
        await update.message.reply_text("❌ Enter key:")
        return SK_VAL
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT INTO keys (mod_id,key_value,duration,max_uses,current_uses,created_date) VALUES (?,?,?,1,0,?)",
              (context.user_data['sk_mod'], kv, context.user_data['sk_dur'], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ *Single key added!*\n🔑 `{kv}`\n👤 1 user", parse_mode='Markdown')
    context.user_data.clear()
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== BULK KEY FLOW ====================
async def bk_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['bk_mod'] = int(q.data.replace("bk_", ""))
    kb = [[InlineKeyboardButton(DM[d], callback_data=f"bkd_{d}")] for d in ['1d', '3d', '7d', '30d']]
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
    await q.edit_message_text("⏱️ *Duration:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    return BK_DUR

async def bk_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['bk_dur'] = q.data.replace("bkd_", "")
    await q.edit_message_text("👥 *How many users can use this key?*", parse_mode='Markdown')
    return BK_COUNT

async def bk_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        n = int(update.message.text)
        if n <= 0: raise ValueError
        context.user_data['bk_count'] = n
    except:
        await update.message.reply_text("❌ Valid number:")
        return BK_COUNT
    await update.message.reply_text(f"🔑 *Enter key (for {n} users):*", parse_mode='Markdown')
    return BK_VAL

async def bk_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    kv = update.message.text.strip()
    if not kv:
        await update.message.reply_text("❌ Enter key:")
        return BK_VAL
    n = context.user_data['bk_count']
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT INTO keys (mod_id,key_value,duration,max_uses,current_uses,created_date) VALUES (?,?,?,?,0,?)",
              (context.user_data['bk_mod'], kv, context.user_data['bk_dur'], n, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ *Bulk key added!*\n🔑 `{kv}`\n👥 {n} users", parse_mode='Markdown')
    context.user_data.clear()
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== EDIT PRODUCT ====================
async def ep_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['ep_id'] = int(q.data.replace("ep_", ""))
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Name", callback_data="ef_name")],
        [InlineKeyboardButton("📋 Description", callback_data="ef_description")],
        [InlineKeyboardButton("📱 Platform", callback_data="ef_platform")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_admin")]])
    await q.edit_message_text("✏️ *What to edit?*", parse_mode='Markdown', reply_markup=kb)
    return EP_FIELD

async def ep_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['ep_f'] = q.data.replace("ef_", "")
    await q.edit_message_text(f"✏️ *Enter new {context.user_data['ep_f']}:*", parse_mode='Markdown')
    return EP_VAL

async def ep_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    conn = gdb()
    c = conn.cursor()
    c.execute(f"UPDATE mods SET {context.user_data['ep_f']}=? WHERE id=?", (update.message.text, context.user_data['ep_id']))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ *Updated!*", parse_mode='Markdown')
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== EDIT PRICE ====================
async def epr_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['epr_id'] = int(q.data.replace("epr_", ""))
    kb = [[InlineKeyboardButton(DM[d], callback_data=f"eprd_{d}")] for d in ['1d', '3d', '7d', '30d']]
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
    await q.edit_message_text("⏳ *Duration:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    return EPRICE_DUR

async def epr_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['epr_dur'] = q.data.replace("eprd_", "")
    await q.edit_message_text("💰 *New price (₹):*", parse_mode='Markdown')
    return EPRICE_VAL

async def epr_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        p = int(update.message.text)
        conn = gdb()
        c = conn.cursor()
        c.execute(f"UPDATE mods SET price_{context.user_data['epr_dur']}=? WHERE id=?", (p, context.user_data['epr_id']))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Price: ₹{p}", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Number:")
        return EPRICE_VAL
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== DELETE MOD/KEY ====================
async def del_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    mid = int(q.data.replace("dm_", ""))
    conn = gdb()
    c = conn.cursor()
    c.execute("UPDATE mods SET is_active=0 WHERE id=?", (mid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("✅ *Product removed!*", parse_mode='Markdown')
    await q.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU

async def del_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    kid = int(q.data.replace("dk_", ""))
    conn = gdb()
    c = conn.cursor()
    c.execute("DELETE FROM keys WHERE id=?", (kid,))
    conn.commit()
    conn.close()
    await q.edit_message_text("✅ *Key deleted!*", parse_mode='Markdown')
    return ADMIN_MENU


# ==================== BAN/UNBAN ====================
async def ban_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        uid = int(update.message.text)
        if uid in ADMIN_IDS:
            await update.message.reply_text("❌ Can't ban admin!")
        else:
            conn = gdb()
            c = conn.cursor()
            c.execute("UPDATE users SET is_banned=1 WHERE user_id=?", (uid,))
            conn.commit()
            conn.close()
            try: await context.bot.send_message(uid, "🚫 You have been banned.")
            except: pass
            await update.message.reply_text(f"✅ `{uid}` banned!", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Invalid ID!")
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU

async def unban_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        uid = int(update.message.text)
        conn = gdb()
        c = conn.cursor()
        c.execute("UPDATE users SET is_banned=0 WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        try: await context.bot.send_message(uid, "✅ Unbanned!")
        except: pass
        await update.message.reply_text(f"✅ `{uid}` unbanned!", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Invalid ID!")
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== ADD BALANCE ====================
async def ab_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        context.user_data['ab_uid'] = int(update.message.text)
        await update.message.reply_text("💰 *Amount:*", parse_mode='Markdown')
        return AB_AMT
    except:
        await update.message.reply_text("❌ Invalid ID!")
        return AB_USER

async def ab_amt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        a = int(update.message.text)
        uid = context.user_data['ab_uid']
        conn = gdb()
        c = conn.cursor()
        c.execute("UPDATE users SET balance=balance+? WHERE user_id=?", (a, uid))
        conn.commit()
        c.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
        nb = c.fetchone()[0]
        conn.close()
        try: await context.bot.send_message(uid, f"💰 ₹{a} added! Balance: ₹{nb}", parse_mode='Markdown')
        except: pass
        await update.message.reply_text(f"✅ ₹{a} → `{uid}` (₹{nb})", parse_mode='Markdown')
    except:
        await update.message.reply_text("❌ Invalid!")
        return AB_AMT
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== BROADCAST ====================
async def bcast_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    conn = gdb()
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE is_banned=0")
    users = c.fetchall()
    conn.close()
    s = f = 0
    for u in users:
        try:
            await context.bot.send_message(u[0], f"📢 *Broadcast*\n━━━━━━━━━━━━━━━━━━\n\n{update.message.text}", parse_mode='Markdown')
            s += 1
        except:
            f += 1
    await update.message.reply_text(f"✅ Sent: {s} | Failed: {f}")
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== QR SETTINGS ====================
async def qr_url_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    context.user_data['nqr'] = update.message.text
    await update.message.reply_text("💳 *New UPI ID:*", parse_mode='Markdown')
    return QR_UPI_S

async def qr_upi_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    context.user_data['nupi'] = update.message.text
    await update.message.reply_text("📝 *Instructions:*", parse_mode='Markdown')
    return QR_INST_S

async def qr_inst_h(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    conn = gdb()
    c = conn.cursor()
    c.execute("INSERT INTO qr_settings (qr_url,upi_id,instructions) VALUES (?,?,?)",
              (context.user_data['nqr'], context.user_data['nupi'], update.message.text))
    conn.commit()
    conn.close()
    await update.message.reply_text("✅ *QR Updated!*", parse_mode='Markdown')
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== RESELLER PRICES ====================
async def rp_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['rp_id'] = int(q.data.replace("rp_", ""))
    kb = [[InlineKeyboardButton(DM[d], callback_data=f"rpd_{d}")] for d in ['1d', '3d', '7d', '30d']]
    kb.append([InlineKeyboardButton("🔙 Back", callback_data="back_admin")])
    await q.edit_message_text("💎 *Duration:*", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(kb))
    return RP_DUR

async def rp_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "back_admin":
        await q.edit_message_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU
    context.user_data['rp_dur'] = q.data.replace("rpd_", "")
    await q.edit_message_text("💎 *Reseller price (₹):*", parse_mode='Markdown')
    return RP_VAL

async def rp_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        p = int(update.message.text)
        conn = gdb()
        c = conn.cursor()
        c.execute(f"UPDATE mods SET reseller_price_{context.user_data['rp_dur']}=? WHERE id=?", (p, context.user_data['rp_id']))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ Reseller price: ₹{p}")
    except:
        await update.message.reply_text("❌ Number:")
        return RP_VAL
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== ALL PRICE EDIT ====================
async def ap_pct(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        pct = float(update.message.text)
        d = context.user_data.get('pdir', 'inc')
        conn = gdb()
        c = conn.cursor()
        c.execute("SELECT id, price_1d, price_3d, price_7d, price_30d FROM mods WHERE is_active=1")
        for m in c.fetchall():
            for i, dur in enumerate(['1d', '3d', '7d', '30d'], 1):
                old = m[i]
                new = int(old * (1 + pct / 100)) if d == 'inc' else max(0, int(old * (1 - pct / 100)))
                c.execute(f"UPDATE mods SET price_{dur}=? WHERE id=?", (new, m[0]))
        conn.commit()
        conn.close()
        await update.message.reply_text(f"✅ All prices {'increased' if d == 'inc' else 'decreased'} by {pct}%")
    except:
        await update.message.reply_text("❌ Number:")
        return AP_PCT
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== CHECK USER ====================
async def check_uid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    action = context.user_data.get('action', 'check')
    try:
        uid = int(update.message.text)
    except:
        await update.message.reply_text("❌ Invalid ID!")
        await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
        return ADMIN_MENU

    conn = gdb()
    c = conn.cursor()
    if action == 'make_res':
        c.execute("UPDATE users SET is_reseller=1 WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        try: await context.bot.send_message(uid, "💎 *You are now a Reseller!*", parse_mode='Markdown')
        except: pass
        await update.message.reply_text(f"✅ `{uid}` → Reseller!", parse_mode='Markdown')
    elif action == 'rm_res':
        c.execute("UPDATE users SET is_reseller=0 WHERE user_id=?", (uid,))
        conn.commit()
        conn.close()
        try: await context.bot.send_message(uid, "❌ Reseller removed.")
        except: pass
        await update.message.reply_text(f"✅ Reseller removed `{uid}`", parse_mode='Markdown')
    else:
        c.execute("SELECT username,first_name,joined_date,balance,is_admin,is_reseller,is_banned,referral_earnings,total_referrals FROM users WHERE user_id=?", (uid,))
        u = c.fetchone()
        if u:
            c.execute("SELECT COUNT(*) FROM orders WHERE user_id=?", (uid,))
            orders = c.fetchone()[0]
            c.execute("SELECT COALESCE(SUM(amount),0) FROM orders WHERE user_id=? AND status='approved'", (uid,))
            spent = c.fetchone()[0]
            role = "👑 Admin" if u[4] else ("💎 Reseller" if u[5] else "👤 User")
            ban = "🚫 Banned" if u[6] else "✅ Active"
            await update.message.reply_text(f"""🔍 *User*
━━━━━━━━━━━━━━━━━━
🆔 `{uid}` @{u[0]} ({u[1]})
{role} | {ban}
💰 ₹{u[3]} | Spent: ₹{spent}
📦 Orders: {orders}
🗣️ Refs: {u[8]} (₹{u[7]})
📅 {u[2]}
━━━━━━━━━━━━━━━━━━""", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Not found!")
        conn.close()

    context.user_data.clear()
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== SETTINGS ====================
async def set_resfee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        ssetting('reseller_fee', int(update.message.text))
        await update.message.reply_text(f"✅ Fee: ₹{update.message.text}")
    except:
        await update.message.reply_text("❌ Number:")
        return SET_RESFEE
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU

async def set_refpts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text in MENU_BUTTONS: return await main_text(update, context)
    try:
        ssetting('referral_reward', int(update.message.text))
        await update.message.reply_text(f"✅ Referral: ₹{update.message.text}/ref")
    except:
        await update.message.reply_text("❌ Number:")
        return SET_REFPTS
    await update.message.reply_text("👑 *Admin Panel*\n━━━━━━━━━━━━━━━━━━", parse_mode='Markdown', reply_markup=admin_kb())
    return ADMIN_MENU


# ==================== ERROR ====================
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")


# ==================== MAIN ====================
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_text)],

            PLATFORM: [CallbackQueryHandler(platform_cb, pattern=r'^(plat_|back_)')],
            GAME: [CallbackQueryHandler(game_cb, pattern=r'^(game_|back_)')],
            MOD_SELECT: [CallbackQueryHandler(mod_cb, pattern=r'^(mod_|back_)')],
            DURATION: [CallbackQueryHandler(dur_cb, pattern=r'^(dur_|back_)')],
            PAYMENT: [CallbackQueryHandler(payment_cb, pattern=r'^(pay_|back_)')],
            SCREENSHOT: [MessageHandler(filters.PHOTO, screenshot_h)],

            DEP_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, dep_amt)],
            DEP_SS: [MessageHandler(filters.PHOTO, dep_ss)],
            RESELLER_SS: [MessageHandler(filters.PHOTO, reseller_ss)],

            ADMIN_MENU: [CallbackQueryHandler(admin_cb)],

            ADD_MOD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmod_name)],
            ADD_MOD_PLAT: [CallbackQueryHandler(addmod_plat, pattern=r'^mp_')],
            ADD_MOD_P1: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmod_p1)],
            ADD_MOD_P3: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmod_p3)],
            ADD_MOD_P7: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmod_p7)],
            ADD_MOD_P30: [MessageHandler(filters.TEXT & ~filters.COMMAND, addmod_p30)],
            ADD_MOD_DESC: [MessageHandler(filters.TEXT, addmod_desc)],
            ADD_MOD_APK: [MessageHandler(filters.Document.ALL, addmod_apk), MessageHandler(filters.TEXT, addmod_apk)],

            SK_MOD: [CallbackQueryHandler(sk_mod, pattern=r'^(sk_|back_)')],
            SK_DUR: [CallbackQueryHandler(sk_dur, pattern=r'^(skd_|back_)')],
            SK_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, sk_val)],

            BK_MOD: [CallbackQueryHandler(bk_mod, pattern=r'^(bk_|back_)')],
            BK_DUR: [CallbackQueryHandler(bk_dur, pattern=r'^(bkd_|back_)')],
            BK_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bk_count)],
            BK_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, bk_val)],

            EP_SEL: [CallbackQueryHandler(ep_sel, pattern=r'^(ep_|back_)')],
            EP_FIELD: [CallbackQueryHandler(ep_field, pattern=r'^(ef_|back_)')],
            EP_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, ep_val)],

            EPRICE_SEL: [CallbackQueryHandler(epr_sel, pattern=r'^(epr_|back_)')],
            EPRICE_DUR: [CallbackQueryHandler(epr_dur, pattern=r'^(eprd_|back_)')],
            EPRICE_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, epr_val)],

            DEL_MOD: [CallbackQueryHandler(del_mod, pattern=r'^(dm_|back_)')],
            DEL_KEY: [CallbackQueryHandler(del_key, pattern=r'^(dk_|back_)')],

            BAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, ban_h)],
            UNBAN_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, unban_h)],
            AB_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, ab_user)],
            AB_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ab_amt)],
            BCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, bcast_h)],

            QR_URL_S: [MessageHandler(filters.TEXT & ~filters.COMMAND, qr_url_h)],
            QR_UPI_S: [MessageHandler(filters.TEXT & ~filters.COMMAND, qr_upi_h)],
            QR_INST_S: [MessageHandler(filters.TEXT & ~filters.COMMAND, qr_inst_h)],

            CHECK_UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_uid)],

            RP_SEL: [CallbackQueryHandler(rp_sel, pattern=r'^(rp_|back_)')],
            RP_DUR: [CallbackQueryHandler(rp_dur, pattern=r'^(rpd_|back_)')],
            RP_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, rp_val)],

            AP_PCT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ap_pct)],
            SET_RESFEE: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_resfee)],
            SET_REFPTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, set_refpts)],
        },
        fallbacks=[
            CommandHandler('start', start),
            CallbackQueryHandler(fallback_approve_reject, pattern=r'^(ordapp_|ordrej_|depapp_|deprej_|resapp_|resrej_)'),
            CallbackQueryHandler(fallback_back_main, pattern=r'^back_main$'),
            CallbackQueryHandler(fallback_back_admin, pattern=r'^back_admin$'),
            MessageHandler(filters.Regex(r'^(🛒|👤|💳|🔑|📜|🗣️|📞|💰|👑)'), main_text),
        ],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_error_handler(error_handler)

    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("✅ BOT STARTED!")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    app.run_polling()


if __name__ == '__main__':
    main()
