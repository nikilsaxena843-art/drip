import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
BOT_TOKEN = "8717905432:AAHyY8OIYwyBdqnIf0ds4ctefflUmLlGDrg"
ADMIN_IDS = [6480827931]
ADMIN_USERNAME = "DRIP_CLIENT_OFFICIAL"
QR_URL = "https://vipxofficial.in/payqr.jpg"
DEFAULT_UPI = "h9641729-1@okaxis"
# ========================================================

# Database setup
def init_db():
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                  balance INTEGER DEFAULT 0, is_admin INTEGER DEFAULT 0, 
                  joined_date TEXT, last_active TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS mods
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT, platform TEXT, price_1d INTEGER, price_3d INTEGER,
                  price_7d INTEGER, price_30d INTEGER, apk_file_id TEXT,
                  description TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS keys
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  mod_id INTEGER, key_value TEXT, duration TEXT,
                  is_used INTEGER DEFAULT 0, used_by INTEGER,
                  expiry_date TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS orders
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  order_id TEXT UNIQUE, user_id INTEGER, mod_id INTEGER,
                  duration TEXT, amount INTEGER, screenshot_file_id TEXT,
                  status TEXT DEFAULT 'pending', order_date TEXT,
                  key_id INTEGER, expiry_date TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS qr_settings
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  qr_url TEXT, upi_id TEXT, instructions TEXT)''')
    
    c.execute("SELECT COUNT(*) FROM qr_settings")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO qr_settings (qr_url, upi_id, instructions) VALUES (?, ?, ?)",
                 (QR_URL, DEFAULT_UPI, "Pay and send screenshot"))
    
    for admin_id in ADMIN_IDS:
        c.execute("INSERT OR IGNORE INTO users (user_id, is_admin, joined_date) VALUES (?, 1, ?)",
                 (admin_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        c.execute("UPDATE users SET is_admin = 1 WHERE user_id = ?", (admin_id,))
    
    conn.commit()
    conn.close()

def generate_order_id():
    return 'ORD' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

# Conversation states
MAIN_MENU, PLATFORM, GAME, MOD_SELECT, DURATION, PAYMENT, SCREENSHOT, ADMIN_MENU = range(8)
ADD_MOD_NAME, ADD_MOD_PLATFORM, ADD_MOD_PRICE_1D, ADD_MOD_PRICE_3D, ADD_MOD_PRICE_7D, ADD_MOD_PRICE_30D, ADD_MOD_DESC, ADD_MOD_APK = range(8, 16)
ADD_KEY_MOD, ADD_KEY_DUR, ADD_KEY_VAL = range(16, 19)
REMOVE_MOD, REMOVE_KEY, BROADCAST_MSG, CHANGE_QR_URL, CHANGE_QR_UPI, CHANGE_QR_INST, CHECK_USER_ID = range(19, 26)

# ==================== START COMMAND ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user.id,))
    if not c.fetchone():
        is_admin = 1 if user.id in ADMIN_IDS else 0
        c.execute("INSERT INTO users (user_id, username, first_name, is_admin, joined_date, last_active) VALUES (?, ?, ?, ?, ?, ?)",
                 (user.id, user.username or "", user.first_name or "", is_admin,
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                  datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    else:
        c.execute("UPDATE users SET last_active = ?, username = ?, first_name = ? WHERE user_id = ?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user.username or "", user.first_name or "", user.id))
    conn.commit()
    conn.close()
    
    await show_main_menu(update, context)
    return MAIN_MENU

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("SELECT is_admin FROM users WHERE user_id = ?", (user.id,))
    result = c.fetchone()
    is_admin = result[0] if result else 0
    conn.close()
    
    keyboard = [
        [InlineKeyboardButton("📦 Products", callback_data="products"),
         InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("🔑 My Keys", callback_data="my_keys"),
         InlineKeyboardButton("📜 History", callback_data="history")],
        [InlineKeyboardButton("📁 Product Files", callback_data="product_files"),
         InlineKeyboardButton("📞 Contact Support", callback_data="contact_support")],
        [InlineKeyboardButton("💰 Apply Reseller", callback_data="apply_reseller")]
    ]
    
    if is_admin:
        keyboard.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"👋 Welcome, {user.first_name}!\n\nWhat would you like to do?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"👋 Welcome, {user.first_name}!\n\nWhat would you like to do?",
            reply_markup=reply_markup
        )

# ==================== USER MENU HANDLERS ====================

async def menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "main_menu":
        await show_main_menu(update, context)
        return MAIN_MENU
    
    elif query.data == "products":
        keyboard = [
            [InlineKeyboardButton("📱 Android", callback_data="platform_android")],
            [InlineKeyboardButton("🍎 iOS", callback_data="platform_ios")],
            [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
        ]
        await query.edit_message_text("📱 Choose your platform:", reply_markup=InlineKeyboardMarkup(keyboard))
        return PLATFORM
    
    elif query.data == "profile":
        user = query.from_user
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute("SELECT joined_date, balance, is_admin FROM users WHERE user_id = ?", (user.id,))
        u = c.fetchone()
        c.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user.id,))
        orders = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM keys WHERE used_by = ? AND is_used = 1 AND expiry_date > ?",
                 (user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        keys = c.fetchone()[0]
        conn.close()
        
        role = "Admin" if u[2] == 1 else "Customer"
        text = f"👤 Profile\n\nID: {user.id}\nUsername: @{user.username}\nRole: {role}\nBalance: ₹{u[1]}\nJoined: {u[0]}\nOrders: {orders}\nActive Keys: {keys}"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU
    
    elif query.data == "my_keys":
        user = query.from_user
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute('''SELECT k.key_value, m.name, k.expiry_date FROM keys k
                     JOIN mods m ON k.mod_id = m.id
                     WHERE k.used_by = ? AND k.is_used = 1 AND k.expiry_date > ?''',
                  (user.id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        keys = c.fetchall()
        conn.close()
        
        if keys:
            text = "Your Active Keys:\n\n"
            for k in keys:
                text += f"📱 {k[1]}\n🔐 {k[0]}\n⏱️ Expires: {k[2]}\n\n"
        else:
            text = "You have no active keys."
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU
    
    elif query.data == "history":
        user = query.from_user
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute('''SELECT m.name, o.duration, o.amount, o.status, o.order_date, o.order_id
                     FROM orders o 
                     JOIN mods m ON o.mod_id = m.id
                     WHERE o.user_id = ? 
                     ORDER BY o.order_date DESC LIMIT 10''', (user.id,))
        orders = c.fetchall()
        conn.close()
        
        if orders:
            text = "Recent Orders:\n\n"
            for o in orders:
                status = "✅" if o[3] == "approved" else "⏳" if o[3] == "pending" else "❌"
                dur_map = {'1d': '1D', '3d': '3D', '7d': '7D', '30d': '30D'}
                dur = dur_map.get(o[1], o[1])
                text += f"{o[5]}\n{o[0]} ({dur}) {status}\n₹{o[2]} - {o[4]}\n\n"
        else:
            text = "No order history."
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU
    
    elif query.data == "product_files":
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute("SELECT name, apk_file_id, description FROM mods WHERE apk_file_id IS NOT NULL")
        files = c.fetchall()
        conn.close()
        
        if files:
            await query.edit_message_text("📁 Sending files...")
            for f in files:
                caption = f"📱 {f[0]}" + (f"\n\n{f[2]}" if f[2] else "")
                await query.message.reply_document(document=f[1], caption=caption)
        else:
            await query.edit_message_text("No product files available.")
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.message.reply_text("Back to main menu?", reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU
    
    elif query.data == "contact_support":
        text = f"📞 Contact Support\n\nAdmin: @{ADMIN_USERNAME}\n\nPlease message the admin for any assistance."
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU
    
    elif query.data == "apply_reseller":
        text = f"💰 Apply for Reseller\n\nTo become a reseller, please contact:\n👉 @{ADMIN_USERNAME}"
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main_menu")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        return MAIN_MENU
    
    elif query.data == "admin_panel":
        if query.from_user.id not in ADMIN_IDS:
            await query.edit_message_text("❌ You are not authorized to access the admin panel.")
            return MAIN_MENU
        return await admin_panel(query, context)

# ==================== PRODUCT FLOW ====================

async def platform_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    platform = query.data.split('_')[1]
    context.user_data['platform'] = platform
    
    keyboard = [
        [InlineKeyboardButton("🔥 Free Fire", callback_data="game_freefire")],
        [InlineKeyboardButton("🔙 Back", callback_data="products")]
    ]
    await query.edit_message_text("🎮 Choose game:", reply_markup=InlineKeyboardMarkup(keyboard))
    return GAME

async def game_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    platform = context.user_data.get('platform')
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("SELECT id, name, price_1d, price_3d, price_7d, price_30d FROM mods WHERE platform = ?", (platform,))
    mods = c.fetchall()
    conn.close()
    
    if not mods:
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="products")]]
        await query.edit_message_text("No mods available for this platform.", reply_markup=InlineKeyboardMarkup(keyboard))
        return PLATFORM
    
    keyboard = []
    for m in mods:
        btn_text = f"{m[1]}\n💰 1D: ₹{m[2]} | 3D: ₹{m[3]} | 7D: ₹{m[4]} | 30D: ₹{m[5]}"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"mod_{m[0]}")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="products")])
    await query.edit_message_text("📋 Available Mods:", reply_markup=InlineKeyboardMarkup(keyboard))
    return MOD_SELECT

async def mod_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mod_id = int(query.data.split('_')[1])
    context.user_data['mod_id'] = mod_id
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("SELECT name, price_1d, price_3d, price_7d, price_30d FROM mods WHERE id = ?", (mod_id,))
    mod = c.fetchone()
    conn.close()
    
    if not mod:
        await query.edit_message_text("Mod not found!")
        return MAIN_MENU
    
    context.user_data['mod_name'] = mod[0]
    
    keyboard = [
        [InlineKeyboardButton(f"1 Day - ₹{mod[1]}", callback_data="dur_1d")],
        [InlineKeyboardButton(f"3 Days - ₹{mod[2]}", callback_data="dur_3d")],
        [InlineKeyboardButton(f"7 Days - ₹{mod[3]}", callback_data="dur_7d")],
        [InlineKeyboardButton(f"30 Days - ₹{mod[4]}", callback_data="dur_30d")],
        [InlineKeyboardButton("🔙 Back", callback_data="products")]
    ]
    await query.edit_message_text(f"{mod[0]}\n\n⏳ Choose duration:", reply_markup=InlineKeyboardMarkup(keyboard))
    return DURATION

async def duration_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    duration = query.data.split('_')[1]
    context.user_data['duration'] = duration
    
    mod_id = context.user_data['mod_id']
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute(f"SELECT price_{duration} FROM mods WHERE id = ?", (mod_id,))
    price = c.fetchone()[0]
    
    c.execute("SELECT qr_url, upi_id, instructions FROM qr_settings ORDER BY id DESC LIMIT 1")
    qr = c.fetchone()
    conn.close()
    
    qr_url = qr[0] if qr else QR_URL
    upi_id = qr[1] if qr else DEFAULT_UPI
    instructions = qr[2] if qr else "Pay and send screenshot"
    context.user_data['amount'] = price
    
    # Send QR code
    try:
        await query.message.reply_photo(
            photo=qr_url,
            caption=f"💰 Amount: ₹{price}\n💳 UPI ID: {upi_id}\n\n📝 {instructions}"
        )
    except:
        qr_img = qrcode.QRCode(box_size=10, border=5)
        qr_img.add_data(f"upi://pay?pa={upi_id}&am={price}&cu=INR")
        img = qr_img.make_image()
        bio = BytesIO()
        img.save(bio, 'PNG')
        bio.seek(0)
        await query.message.reply_photo(
            photo=bio,
            caption=f"💰 Amount: ₹{price}\n💳 UPI ID: {upi_id}\n\n📝 {instructions}"
        )
    
    # IMPORTANT: Pay button QR ke NICHE aa raha hai
    keyboard = [[InlineKeyboardButton("💳 I have paid", callback_data="pay_now")]]
    await query.edit_message_text("Click after making payment:", reply_markup=InlineKeyboardMarkup(keyboard))
    return PAYMENT

async def payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📸 Please upload your payment screenshot:")
    return SCREENSHOT

async def screenshot_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("❌ Please upload a photo.")
        return SCREENSHOT
    
    user = update.effective_user
    photo = update.message.photo[-1].file_id
    mod_id = context.user_data['mod_id']
    duration = context.user_data['duration']
    amount = context.user_data['amount']
    
    order_id = generate_order_id()
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute('''INSERT INTO orders 
                 (order_id, user_id, mod_id, duration, amount, screenshot_file_id, status, order_date)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (order_id, user.id, mod_id, duration, amount, photo, 'pending',
               datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    conn.close()
    
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"💰 New Payment!\n\nOrder: {order_id}\nUser: {user.first_name} (ID: {user.id})\nAmount: ₹{amount}"
            )
        except:
            pass
    
    await update.message.reply_text("✅ Payment received! Admin will verify soon.")
    
    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data="main_menu")]]
    await update.message.reply_text("Return to menu?", reply_markup=InlineKeyboardMarkup(keyboard))
    return MAIN_MENU

# ==================== ADMIN PANEL ====================

async def admin_panel(query, context):
    keyboard = [
        [InlineKeyboardButton("➕ Add Mod", callback_data="admin_add_mod")],
        [InlineKeyboardButton("➖ Remove Mod", callback_data="admin_remove_mod")],
        [InlineKeyboardButton("🔐 Add Key", callback_data="admin_add_key")],
        [InlineKeyboardButton("🔓 Remove Key", callback_data="admin_remove_key")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("👥 User Stats", callback_data="admin_users")],
        [InlineKeyboardButton("🔄 Change QR", callback_data="admin_change_qr")],
        [InlineKeyboardButton("⏳ Pending Orders", callback_data="admin_pending")],
        [InlineKeyboardButton("🔍 Check User", callback_data="admin_check")],
        [InlineKeyboardButton("💾 Backup DB", callback_data="admin_backup")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    await query.edit_message_text("👑 Admin Panel", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

async def admin_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("❌ Unauthorized!")
        return MAIN_MENU
    
    data = query.data
    
    # Pending Orders
    if data == "admin_pending":
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute('''SELECT o.id, o.order_id, u.username, u.first_name, m.name, o.duration, o.amount, o.order_date
                     FROM orders o 
                     JOIN users u ON o.user_id = u.user_id
                     JOIN mods m ON o.mod_id = m.id 
                     WHERE o.status = 'pending'
                     ORDER BY o.order_date DESC''')
        orders = c.fetchall()
        conn.close()
        
        if not orders:
            await query.edit_message_text("No pending orders.")
            return ADMIN_MENU
        
        await query.edit_message_text("📋 Pending Orders:")
        for o in orders:
            db_id, order_id, username, name, mod_name, duration, amount, date = o
            dur_map = {'1d': '1D', '3d': '3D', '7d': '7D', '30d': '30D'}
            dur = dur_map.get(duration, duration)
            
            btns = [[
                InlineKeyboardButton("✅ Approve", callback_data=f"app_{db_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"rej_{db_id}")
            ]]
            
            await query.message.reply_text(
                f"Order: {order_id}\nUser: @{username} ({name})\nMod: {mod_name} ({dur})\nAmount: ₹{amount}\nDate: {date}",
                reply_markup=InlineKeyboardMarkup(btns)
            )
        return ADMIN_MENU
    
    # Approve Order
    elif data.startswith("app_"):
        db_id = int(data.split('_')[1])
        
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        
        c.execute("SELECT user_id, mod_id, duration FROM orders WHERE id = ?", (db_id,))
        order = c.fetchone()
        
        if not order:
            await query.edit_message_text("Order not found.")
            conn.close()
            return ADMIN_MENU
        
        user_id, mod_id, duration = order
        
        c.execute("SELECT id, key_value FROM keys WHERE mod_id = ? AND duration = ? AND is_used = 0 LIMIT 1", (mod_id, duration))
        key = c.fetchone()
        
        if not key:
            await query.edit_message_text("❌ No keys available!")
            conn.close()
            return ADMIN_MENU
        
        key_id, key_value = key
        
        days = {'1d': 1, '3d': 3, '7d': 7, '30d': 30}
        expiry = (datetime.now() + timedelta(days=days[duration])).strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("UPDATE keys SET is_used = 1, used_by = ?, expiry_date = ? WHERE id = ?", (user_id, expiry, key_id))
        c.execute("UPDATE orders SET status = 'approved', key_id = ?, expiry_date = ? WHERE id = ?", (key_id, expiry, db_id))
        
        conn.commit()
        conn.close()
        
        try:
            await context.bot.send_message(
                user_id,
                f"✅ Payment Approved!\n\n🔑 Your Key: {key_value}\n⏱️ Valid Until: {expiry}"
            )
        except:
            pass
        
        await query.edit_message_text(f"✅ Approved. Key: {key_value}")
        return ADMIN_MENU
    
    # Reject Order
    elif data.startswith("rej_"):
        db_id = int(data.split('_')[1])
        
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        
        c.execute("SELECT user_id FROM orders WHERE id = ?", (db_id,))
        order = c.fetchone()
        
        if order:
            c.execute("UPDATE orders SET status = 'rejected' WHERE id = ?", (db_id,))
            conn.commit()
            
            try:
                await context.bot.send_message(order[0], "❌ Your payment was rejected. Please contact support.")
            except:
                pass
        
        conn.close()
        
        await query.edit_message_text("❌ Order rejected.")
        return ADMIN_MENU
    
    # Add Mod
    elif data == "admin_add_mod":
        context.user_data['admin_step'] = 'add_mod_name'
        await query.edit_message_text("📝 Enter mod name:")
        return ADD_MOD_NAME
    
    # Remove Mod
    elif data == "admin_remove_mod":
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, name FROM mods")
        mods = c.fetchall()
        conn.close()
        
        if not mods:
            await query.edit_message_text("No mods to remove.")
            return ADMIN_MENU
        
        keyboard = []
        for m in mods:
            keyboard.append([InlineKeyboardButton(f"❌ {m[1]}", callback_data=f"remove_mod_{m[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        
        await query.edit_message_text("Select mod to remove:", reply_markup=InlineKeyboardMarkup(keyboard))
        return REMOVE_MOD
    
    # Add Key
    elif data == "admin_add_key":
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute("SELECT id, name FROM mods")
        mods = c.fetchall()
        conn.close()
        
        if not mods:
            await query.edit_message_text("No mods available.")
            return ADMIN_MENU
        
        keyboard = []
        for m in mods:
            keyboard.append([InlineKeyboardButton(m[1], callback_data=f"addkey_mod_{m[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_panel")])
        
        await query.edit_message_text("Select mod to add key for:", reply_markup=InlineKeyboardMarkup(keyboard))
        return ADD_KEY_MOD
    
    # Remove Key
    elif data == "admin_remove_key":
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        c.execute('''SELECT k.id, m.name, k.key_value, k.duration FROM keys k
                     JOIN mods m ON k.mod_id = m.id
                     WHERE k.is_used = 0
                     ORDER BY m.name''')
        keys = c.fetchall()
        conn.close()
        
        if not keys:
            await query.edit_message_text("No unused keys to remove.")
            return ADMIN_MENU
        
        for k in keys:
            key_id, mod_name, key_value, duration = k
            dur_map = {'1d': '1D', '3d': '3D', '7d': '7D', '30d': '30D'}
            dur = dur_map.get(duration, duration)
            
            btn = InlineKeyboardButton(f"❌ {mod_name} ({dur}) {key_value[:10]}...", callback_data=f"remove_key_{key_id}")
            await query.message.reply_text(f"Key: {key_value}", reply_markup=InlineKeyboardMarkup([[btn]]))
        return REMOVE_KEY
    
    # Broadcast
    elif data == "admin_broadcast":
        context.user_data['admin_step'] = 'broadcast'
        await query.edit_message_text("📢 Enter broadcast message:")
        return BROADCAST_MSG
    
    # User Stats
    elif data == "admin_users":
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        
        c.execute("SELECT COUNT(*) FROM users")
        total_users = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1")
        admins = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM orders")
        total_orders = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'")
        pending = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM orders WHERE status = 'approved'")
        approved = c.fetchone()[0]
        
        c.execute("SELECT SUM(amount) FROM orders WHERE status = 'approved'")
        revenue = c.fetchone()[0] or 0
        
        c.execute("SELECT COUNT(*) FROM mods")
        mods = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM keys")
        total_keys = c.fetchone()[0]
        
        c.execute("SELECT COUNT(*) FROM keys WHERE is_used = 1")
        used_keys = c.fetchone()[0]
        
        conn.close()
        
        text = f"📊 Bot Statistics\n\n"
        text += f"👥 Total Users: {total_users}\n"
        text += f"👑 Admins: {admins}\n"
        text += f"📦 Total Orders: {total_orders}\n"
        text += f"⏳ Pending: {pending}\n"
        text += f"✅ Approved: {approved}\n"
        text += f"💰 Revenue: ₹{revenue}\n"
        text += f"🎮 Mods: {mods}\n"
        text += f"🔑 Total Keys: {total_keys}\n"
        text += f"🔓 Used Keys: {used_keys}"
        
        await query.edit_message_text(text)
        return ADMIN_MENU
    
    # Change QR
    elif data == "admin_change_qr":
        context.user_data['admin_step'] = 'qr_url'
        await query.edit_message_text("🖼️ Enter new QR code image URL:")
        return CHANGE_QR_URL
    
    # Check User
    elif data == "admin_check":
        context.user_data['admin_step'] = 'check_user'
        await query.edit_message_text("🔍 Enter user ID:")
        return CHECK_USER_ID
    
    # Backup DB
    elif data == "admin_backup":
        if os.path.exists('freefire_bot.db'):
            with open('freefire_bot.db', 'rb') as f:
                await query.message.reply_document(
                    document=f,
                    filename=f'backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db',
                    caption="💾 Database Backup"
                )
        return ADMIN_MENU
    
    return ADMIN_MENU

# ==================== ADD MOD HANDLERS ====================

async def add_mod_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['mod_name'] = update.message.text
    context.user_data['admin_step'] = 'add_mod_platform'
    
    keyboard = [
        [InlineKeyboardButton("📱 Android", callback_data="mod_platform_android")],
        [InlineKeyboardButton("🍎 iOS", callback_data="mod_platform_ios")]
    ]
    await update.message.reply_text("📱 Select platform:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_MOD_PLATFORM

async def add_mod_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    platform = query.data.split('_')[2]
    context.user_data['mod_platform'] = platform
    context.user_data['admin_step'] = 'add_mod_price_1d'
    
    await query.edit_message_text("💰 Enter price for 1 day (in ₹):")
    return ADD_MOD_PRICE_1D

async def add_mod_price_1d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        context.user_data['price_1d'] = price
        context.user_data['admin_step'] = 'add_mod_price_3d'
        await update.message.reply_text("💰 Enter price for 3 days (in ₹):")
        return ADD_MOD_PRICE_3D
    except:
        await update.message.reply_text("❌ Invalid number. Try again:")
        return ADD_MOD_PRICE_1D

async def add_mod_price_3d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        context.user_data['price_3d'] = price
        context.user_data['admin_step'] = 'add_mod_price_7d'
        await update.message.reply_text("💰 Enter price for 7 days (in ₹):")
        return ADD_MOD_PRICE_7D
    except:
        await update.message.reply_text("❌ Invalid number. Try again:")
        return ADD_MOD_PRICE_3D

async def add_mod_price_7d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        context.user_data['price_7d'] = price
        context.user_data['admin_step'] = 'add_mod_price_30d'
        await update.message.reply_text("💰 Enter price for 30 days (in ₹):")
        return ADD_MOD_PRICE_30D
    except:
        await update.message.reply_text("❌ Invalid number. Try again:")
        return ADD_MOD_PRICE_7D

async def add_mod_price_30d(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = int(update.message.text)
        context.user_data['price_30d'] = price
        context.user_data['admin_step'] = 'add_mod_desc'
        await update.message.reply_text("📋 Enter description (or /skip):")
        return ADD_MOD_DESC
    except:
        await update.message.reply_text("❌ Invalid number. Try again:")
        return ADD_MOD_PRICE_30D

async def add_mod_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/skip":
        context.user_data['mod_desc'] = ""
    else:
        context.user_data['mod_desc'] = update.message.text
    
    context.user_data['admin_step'] = 'add_mod_apk'
    await update.message.reply_text("📁 Upload APK file (or /skip):")
    return ADD_MOD_APK

async def add_mod_apk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text == "/skip":
        file_id = None
    elif update.message.document:
        file_id = update.message.document.file_id
    else:
        await update.message.reply_text("❌ Please upload an APK file or type /skip")
        return ADD_MOD_APK
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute('''INSERT INTO mods 
                 (name, platform, price_1d, price_3d, price_7d, price_30d, apk_file_id, description)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
              (context.user_data['mod_name'], context.user_data['mod_platform'],
               context.user_data['price_1d'], context.user_data['price_3d'],
               context.user_data['price_7d'], context.user_data['price_30d'],
               file_id, context.user_data['mod_desc']))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("✅ Mod added successfully!")
    context.user_data.clear()
    
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await update.message.reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== ADD KEY HANDLERS ====================

async def add_key_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mod_id = int(query.data.split('_')[2])
    context.user_data['key_mod_id'] = mod_id
    context.user_data['admin_step'] = 'add_key_dur'
    
    keyboard = [
        [InlineKeyboardButton("1 Day", callback_data="key_dur_1d")],
        [InlineKeyboardButton("3 Days", callback_data="key_dur_3d")],
        [InlineKeyboardButton("7 Days", callback_data="key_dur_7d")],
        [InlineKeyboardButton("30 Days", callback_data="key_dur_30d")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_panel")]
    ]
    await query.edit_message_text("⏱️ Select duration:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_KEY_DUR

async def add_key_dur(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    duration = query.data.split('_')[2]
    context.user_data['key_duration'] = duration
    context.user_data['admin_step'] = 'add_key_val'
    
    keyboard = [[InlineKeyboardButton("🎲 Generate", callback_data="generate_key")]]
    await query.edit_message_text("🔑 Enter key value:", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADD_KEY_VAL

async def add_key_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        key_val = update.message.text
    else:
        query = update.callback_query
        await query.answer()
        chars = string.ascii_uppercase + string.digits
        key_val = 'FF-' + '-'.join(''.join(random.choices(chars, k=4)) for _ in range(4))
        await query.edit_message_text(f"✅ Generated: {key_val}")
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute('''INSERT INTO keys (mod_id, key_value, duration)
                 VALUES (?, ?, ?)''',
              (context.user_data['key_mod_id'], key_val, context.user_data['key_duration']))
    conn.commit()
    conn.close()
    
    if update.message:
        await update.message.reply_text(f"✅ Key added: {key_val}")
    else:
        await update.callback_query.message.reply_text(f"✅ Key added: {key_val}")
    
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await (update.message or update.callback_query.message).reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== REMOVE MOD HANDLERS ====================

async def remove_mod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mod_id = int(query.data.split('_')[2])
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("DELETE FROM mods WHERE id = ?", (mod_id,))
    c.execute("DELETE FROM keys WHERE mod_id = ?", (mod_id,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text("✅ Mod removed successfully!")
    
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await query.message.reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== REMOVE KEY HANDLERS ====================

async def remove_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    key_id = int(query.data.split('_')[2])
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("DELETE FROM keys WHERE id = ? AND is_used = 0", (key_id,))
    conn.commit()
    conn.close()
    
    await query.edit_message_text("✅ Key removed successfully!")
    
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await query.message.reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== BROADCAST HANDLER ====================

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("SELECT user_id FROM users")
    users = c.fetchall()
    conn.close()
    
    sent = 0
    for u in users:
        try:
            await context.bot.send_message(u[0], f"📢 Broadcast Message\n\n{message}")
            sent += 1
        except:
            pass
    
    await update.message.reply_text(f"✅ Broadcast sent to {sent} users!")
    context.user_data.clear()
    
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await update.message.reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== CHANGE QR HANDLERS ====================

async def change_qr_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_qr_url'] = update.message.text
    context.user_data['admin_step'] = 'qr_upi'
    await update.message.reply_text("💳 Enter new UPI ID:")
    return CHANGE_QR_UPI

async def change_qr_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_upi'] = update.message.text
    context.user_data['admin_step'] = 'qr_inst'
    await update.message.reply_text("📝 Enter payment instructions:")
    return CHANGE_QR_INST

async def change_qr_inst(update: Update, context: ContextTypes.DEFAULT_TYPE):
    instructions = update.message.text
    
    conn = sqlite3.connect('freefire_bot.db')
    c = conn.cursor()
    c.execute("INSERT INTO qr_settings (qr_url, upi_id, instructions) VALUES (?, ?, ?)",
              (context.user_data['new_qr_url'], context.user_data['new_upi'], instructions))
    conn.commit()
    conn.close()
    
    await update.message.reply_text("✅ QR settings updated successfully!")
    context.user_data.clear()
    
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await update.message.reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== CHECK USER HANDLER ====================

async def check_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        user_id = int(update.message.text)
        
        conn = sqlite3.connect('freefire_bot.db')
        c = conn.cursor()
        
        c.execute("SELECT username, first_name, joined_date, balance, is_admin FROM users WHERE user_id = ?", (user_id,))
        user = c.fetchone()
        
        if user:
            username, first_name, joined, balance, is_admin = user
            
            c.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
            orders = c.fetchone()[0]
            
            c.execute("SELECT COUNT(*) FROM keys WHERE used_by = ? AND is_used = 1", (user_id,))
            keys = c.fetchone()[0]
            
            c.execute("SELECT SUM(amount) FROM orders WHERE user_id = ? AND status = 'approved'", (user_id,))
            spent = c.fetchone()[0] or 0
            
            role = "Admin" if is_admin else "User"
            
            text = f"👤 User Details\n\n"
            text += f"ID: {user_id}\n"
            text += f"Username: @{username}\n"
            text += f"Name: {first_name}\n"
            text += f"Role: {role}\n"
            text += f"Joined: {joined}\n"
            text += f"Balance: ₹{balance}\n"
            text += f"Orders: {orders}\n"
            text += f"Keys: {keys}\n"
            text += f"Total Spent: ₹{spent}"
        else:
            text = "❌ User not found!"
        
        conn.close()
        await update.message.reply_text(text)
        
    except:
        await update.message.reply_text("❌ Invalid user ID!")
    
    context.user_data.clear()
    keyboard = [[InlineKeyboardButton("👑 Admin Panel", callback_data="admin_panel")]]
    await update.message.reply_text("Return to admin panel?", reply_markup=InlineKeyboardMarkup(keyboard))
    return ADMIN_MENU

# ==================== ERROR HANDLER ====================

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")

# ==================== MAIN ====================

def main():
    init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    conv = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            MAIN_MENU: [CallbackQueryHandler(menu_handler)],
            PLATFORM: [CallbackQueryHandler(platform_handler, pattern="^platform_")],
            GAME: [CallbackQueryHandler(game_handler, pattern="^game_")],
            MOD_SELECT: [CallbackQueryHandler(mod_handler, pattern="^mod_")],
            DURATION: [CallbackQueryHandler(duration_handler, pattern="^dur_")],
            PAYMENT: [CallbackQueryHandler(payment_handler, pattern="^pay_now$")],
            SCREENSHOT: [MessageHandler(filters.PHOTO, screenshot_handler)],
            ADMIN_MENU: [CallbackQueryHandler(admin_handler)],
            ADD_MOD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_mod_name)],
            ADD_MOD_PLATFORM: [CallbackQueryHandler(add_mod_platform, pattern="^mod_platform_")],
            ADD_MOD_PRICE_1D: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_mod_price_1d)],
            ADD_MOD_PRICE_3D: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_mod_price_3d)],
            ADD_MOD_PRICE_7D: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_mod_price_7d)],
            ADD_MOD_PRICE_30D: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_mod_price_30d)],
            ADD_MOD_DESC: [MessageHandler(filters.TEXT | filters.COMMAND, add_mod_desc)],
            ADD_MOD_APK: [MessageHandler(filters.Document.ALL | filters.TEXT | filters.COMMAND, add_mod_apk)],
            ADD_KEY_MOD: [CallbackQueryHandler(add_key_mod, pattern="^addkey_mod_")],
            ADD_KEY_DUR: [CallbackQueryHandler(add_key_dur, pattern="^key_dur_")],
            ADD_KEY_VAL: [CallbackQueryHandler(add_key_val, pattern="^generate_key$"), MessageHandler(filters.TEXT & ~filters.COMMAND, add_key_val)],
            REMOVE_MOD: [CallbackQueryHandler(remove_mod, pattern="^remove_mod_")],
            REMOVE_KEY: [CallbackQueryHandler(remove_key, pattern="^remove_key_")],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast)],
            CHANGE_QR_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_qr_url)],
            CHANGE_QR_UPI: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_qr_upi)],
            CHANGE_QR_INST: [MessageHandler(filters.TEXT & ~filters.COMMAND, change_qr_inst)],
            CHECK_USER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_user)],
        },
        fallbacks=[CommandHandler('start', start)]
    )
    
    app.add_handler(conv)
    app.add_error_handler(error_handler)
    
    print("✅ BOT STARTED - ALL FEATURES WORKING!")
    print(f"👑 Admin: @{ADMIN_USERNAME}")
    print(f"🆔 Admin ID: {ADMIN_IDS[0]}")
    app.run_polling()

if __name__ == '__main__':
    main()