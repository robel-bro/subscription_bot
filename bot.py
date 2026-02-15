import os
import sqlite3
import threading
import time
import asyncio
from datetime import datetime
from flask import Flask, request
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes,
)

# -------------------- Load Environment Variables --------------------
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PRIVATE_CHANNEL_ID = os.getenv("PRIVATE_CHANNEL_ID")
if PRIVATE_CHANNEL_ID and PRIVATE_CHANNEL_ID.lstrip("-").isdigit():
    PRIVATE_CHANNEL_ID = int(PRIVATE_CHANNEL_ID)

ADMIN_IDS = []
_admins = os.getenv("ADMIN_IDS", "")
if _admins:
    for x in _admins.split(","):
        x = x.strip()
        if x and x.isdigit():
            ADMIN_IDS.append(int(x))

# Koyeb will provide the PORT via environment variable
PORT = int(os.environ.get("PORT", 8000))
# Your Koyeb app URL - set this in Koyeb environment variables
APP_URL = os.getenv("APP_URL", "https://your-app-name.koyeb.app")
WEBHOOK_URL = f"{APP_URL}/webhook"

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not PRIVATE_CHANNEL_ID:
    raise RuntimeError("PRIVATE_CHANNEL_ID is required")

# -------------------- Database Setup --------------------
DB_PATH = "subscriptions.db"
db_lock = threading.Lock()

def init_db():
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
                        user_id INTEGER PRIMARY KEY,
                        expiry_date INTEGER NOT NULL)''')
        conn.commit()
        conn.close()

def add_subscription(user_id, days):
    expiry = int(time.time()) + days * 86400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("REPLACE INTO subscriptions (user_id, expiry_date) VALUES (?, ?)", (user_id, expiry))
        conn.commit()
        conn.close()

def remove_subscription(user_id):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

def get_expired_users(now=None):
    if now is None:
        now = int(time.time())
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id FROM subscriptions WHERE expiry_date <= ?", (now,))
        expired = [row[0] for row in c.fetchall()]
        conn.close()
    return expired

def get_subscription_expiry(user_id):
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT expiry_date FROM subscriptions WHERE user_id = ?", (user_id,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else None

init_db()

# -------------------- Flask App --------------------
app = Flask(__name__)

# -------------------- Telegram Bot Setup --------------------
# Build application (no updater/ polling)
application = Application.builder().token(BOT_TOKEN).build()

# Prices in Ethiopian Birr
TELEBIRR_ACCOUNT = "0987973732"
PRICE_1 = 700
PRICE_2 = 1400
PRICE_3 = 2000

def format_expiry(timestamp):
    if not timestamp:
        return "`Not subscribed`"
    dt = datetime.fromtimestamp(timestamp)
    return f"`{dt.strftime('%Y-%m-%d %H:%M:%S')}`"

def plan_keyboard():
    keyboard = [
        [InlineKeyboardButton(f"1 Month – {PRICE_1} Birr", callback_data="plan:1")],
        [InlineKeyboardButton(f"2 Months – {PRICE_2} Birr", callback_data="plan:2")],
        [InlineKeyboardButton(f"3 Months – {PRICE_3} Birr", callback_data="plan:3")],
    ]
    return InlineKeyboardMarkup(keyboard)

# -------------------- Telegram Bot Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    welcome_text = (
        f"👋 *Welcome to Our VVIP Habesha Premium Private Channel* 🔥💋\n\n"
        f"🇺🇸 *English:*\n"
        f"Welcome to our VVIP Habesha 🔥 Premium sex Private Channel 😈💎\n"
        f"To unlock exclusive hot content and enjoy full access, please select your membership plan below and complete your payment on Telebirr.\n"
        f"💳 Choose your membership.\n"
        f"✅ Make payment.\n"
        f"🔓 Get instant access now.\n"
        f"Don’t miss the exclusive vibes waiting for you… 💋🔥\n\n"
        f"🇪🇹 *አማርኛ:*\n"
        f"ወደ VVIP Habesha 🔥 ፕሪሚየም ወሲብ ፕራይቬት ቻናላችን 😈💎 እንኳን በደህና መጡ!\n"
        f"ሙሉ እና ልዩ የሆነ የሀበሻ ወሲብ ኮንቴንት 🔥💋 ለማግኘት ከታች ያለውን የአባልነት አማራጭ ይምረጡ እና ክፍያዎን በ ቴሌብር ይፈጽሙ።\n"
        f"💳 አባልነትዎን ይምረጡ\n"
        f"✅ ክፍያ ይፈጽሙ\n"
        f"🔓 ወዲያውኑ መግቢያ ያግኙ"
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=plan_keyboard())

async def plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split(":")
    if data[0] != "plan":
        return
    months = int(data[1])
    context.user_data['selected_months'] = months

    if months == 1:
        price = PRICE_1
    elif months == 2:
        price = PRICE_2
    else:
        price = PRICE_3

    confirm_text = (
        f"✅ *You selected {months} month(s) – Total: {price} Birr*\n\n"
        f"🇺🇸 Please send **{price} Birr** to the following Telebirr account:\n"
        f"`{TELEBIRR_ACCOUNT}`\n\n"
        f"After payment, **send a screenshot** of the transaction.\n\n"
        f"🇪🇹 እባክዎ **{price} ብር** ወደዚህ ቴሌብር አካውንት ይላኩ።\n"
        f"`{TELEBIRR_ACCOUNT}`\n\n"
        f"ከክፍያ በኋላ የስክሪን ሾት ይላኩ።"
    )
    await query.edit_message_text(confirm_text, parse_mode="Markdown")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    months = context.user_data.get('selected_months')
    if not months:
        await update.message.reply_text(
            "🇺🇸 Please first choose a subscription plan using /start.\n"
            "🇪🇹 እባክዎ መጀመሪያ የደንበኝነት ምርጫዎን ይምረጡ።",
            reply_markup=plan_keyboard()
        )
        return

    if months == 1:
        price = PRICE_1
    elif months == 2:
        price = PRICE_2
    else:
        price = PRICE_3

    photo = update.message.photo[-1]
    caption = (
        f"💳 *New payment screenshot*\n"
        f"From: [{user.first_name}](tg://user?id={user.id})\n"
        f"User ID: `{user.id}`\n"
        f"Username: @{user.username or 'N/A'}\n"
        f"Plan: {months} month(s) – {price} Birr\n"
        f"Telebirr account: `{TELEBIRR_ACCOUNT}`"
    )
    keyboard = [
        [
            InlineKeyboardButton(f"✅ Approve ({months} months)", callback_data=f"approve:{user.id}:{months}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"decline:{user.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_photo(
                chat_id=admin_id,
                photo=photo.file_id,
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to send to admin {admin_id}: {e}")

    await update.message.reply_text(
        "✅ Your screenshot has been sent. You'll be notified once approved.\n\n"
        "✅ የስክሪን ሾትዎ ተልኳል። ሲፀድቅ ይነገርዎታል።"
    )
    context.user_data.clear()

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("⛔ Unauthorized.")
        return

    data = query.data.split(":")
    action = data[0]
    user_id = int(data[1])

    if action == "approve":
        months = int(data[2])
        add_subscription(user_id, months * 30)
        try:
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=PRIVATE_CHANNEL_ID,
                member_limit=1,
                expire_date=int(time.time()) + months * 30 * 86400
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 *Your payment has been approved! / ክፍያዎ ጸድቋል!*\n\n"
                    f"🇺🇸 You have been granted access for {months} month(s).\n"
                    f"Here is your invite link:\n{invite_link.invite_link}\n\n"
                    f"🇪🇹 የ{months} ወር መዳረሻ ተሰጥቶዎታል።\n"
                    f"የመግቢያ ሊንክዎ ይህ ነው።"
                ),
                parse_mode="Markdown"
            )
            await query.edit_message_text(
                text=f"✅ Approved user `{user_id}` for {months} months.\n\nInvite link sent.",
                parse_mode="Markdown"
            )
        except Exception as e:
            await query.edit_message_text(f"❌ Approval failed: {e}")
    elif action == "decline":
        await query.edit_message_text(f"❌ Declined user `{user_id}`.", parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "🤖 *Available Commands*\n\n"
        "👤 *For everyone:*\n"
        "/start – Choose subscription plan\n"
        "/help – Show this message\n"
        "/status – Check your subscription status\n"
        "/renew – Request renewal (if expired)\n\n"
        "👑 *For admins only:*\n"
        "/approve <user_id> [months] – Manually approve (default 1 month)\n"
        "/list – List all active subscribers"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    expiry = get_subscription_expiry(user_id)
    if expiry and expiry > int(time.time()):
        remaining = expiry - int(time.time())
        days = remaining // 86400
        hours = (remaining % 86400) // 3600
        status_text = (
            f"✅ *You are subscribed!*\n"
            f"Expires: {format_expiry(expiry)}\n"
            f"Time left: {days} days, {hours} hours"
        )
    elif expiry:
        status_text = "❌ *Your subscription has expired.* Use /renew to request renewal."
    else:
        status_text = "❌ *You are not subscribed.* Send /start to choose a plan."
    await update.message.reply_text(status_text, parse_mode="Markdown")

async def renew_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=f"🔄 *Renewal request* from [{user.first_name}](tg://user?id={user.id}) (ID: `{user.id}`)",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Failed to notify admin {admin_id}: {e}")
    await update.message.reply_text(
        "📩 Your renewal request has been sent to the admins.\n\n"
        "📩 የእድሳት ጥያቄዎ ለአስተዳዳሪዎች ተልኳል።"
    )

async def approve_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /approve <user_id> [months]")
        return
    try:
        user_id = int(context.args[0])
        months = int(context.args[1]) if len(context.args) > 1 else 1
    except ValueError:
        await update.message.reply_text("Invalid arguments.")
        return

    add_subscription(user_id, months * 30)
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=PRIVATE_CHANNEL_ID,
            member_limit=1,
            expire_date=int(time.time()) + months * 30 * 86400
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 An admin has manually approved your subscription for {months} months!\n\n"
                f"Your invite link:\n{invite_link.invite_link}"
            )
        )
        await update.message.reply_text(f"✅ Approved user {user_id} for {months} months.")
    except Exception as e:
        await update.message.reply_text(f"❌ Approval failed: {e}")

async def list_subscribers(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("⛔ Unauthorized.")
        return
    now = int(time.time())
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT user_id, expiry_date FROM subscriptions ORDER BY expiry_date")
        rows = c.fetchall()
        conn.close()
    if not rows:
        await update.message.reply_text("No active subscribers.")
        return
    lines = ["📋 *Active Subscribers:*\n"]
    for uid, exp in rows:
        status = "✅" if exp > now else "❌"
        lines.append(f"{status} `{uid}` – expires {format_expiry(exp)}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

# Register all handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("help", help_command))
application.add_handler(CommandHandler("status", status_command))
application.add_handler(CommandHandler("renew", renew_request))
application.add_handler(CommandHandler("approve", approve_manual, filters=filters.User(user_id=ADMIN_IDS)))
application.add_handler(CommandHandler("list", list_subscribers, filters=filters.User(user_id=ADMIN_IDS)))
application.add_handler(CallbackQueryHandler(plan_callback, pattern="^plan:"))
application.add_handler(CallbackQueryHandler(handle_callback, pattern="^(approve|decline):"))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

# -------------------- Flask Routes --------------------
@app.route("/")
def home():
    return "Bot is running (webhook mode)", 200

@app.route("/status")
def status():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates via webhook."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        # Process update synchronously in a new event loop
        asyncio.run(application.process_update(update))
        return "OK", 200
    except Exception as e:
        print(f"Error in webhook: {e}")
        return "OK", 200  # Always return OK to acknowledge receipt

@app.route("/set_webhook")
def set_webhook():
    """Register the webhook with Telegram."""
    async def set_hook():
        await application.bot.set_webhook(url=WEBHOOK_URL)
    asyncio.run(set_hook())
    return f"✅ Webhook set to {WEBHOOK_URL}"

@app.route("/webhook_info")
def webhook_info():
    """Get current webhook status from Telegram."""
    async def get_info():
        return await application.bot.get_webhook_info()
    info = asyncio.run(get_info())
    return f"""
    <html>
    <body>
    <h2>Webhook Info</h2>
    <p><b>URL:</b> {info.url}</p>
    <p><b>Pending updates:</b> {info.pending_update_count}</p>
    <p><b>Last error message:</b> {info.last_error_message}</p>
    <p><b>Last error date:</b> {info.last_error_date}</p>
    </body>
    </html>
    """

@app.route("/cleanup")
def cleanup_expired():
    """Remove expired users from channel and database."""
    token = request.args.get("token")
    if token != "habeshaVVIP2025":  # Change this to your secret token
        return "Unauthorized", 403

    now = int(time.time())
    expired = get_expired_users(now)
    for user_id in expired:
        try:
            asyncio.run(application.bot.ban_chat_member(
                chat_id=PRIVATE_CHANNEL_ID,
                user_id=user_id
            ))
            remove_subscription(user_id)
            asyncio.run(application.bot.send_message(
                chat_id=user_id,
                text="Your subscription has expired. To renew, please send a new payment screenshot."
            ))
        except Exception as e:
            print(f"Error removing user {user_id}: {e}")
    return f"Removed {len(expired)} expired users."

# -------------------- Run Flask --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)