import os
import sqlite3
import threading
import time
import asyncio
import atexit
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
        if not x:
            continue
        try:
            ADMIN_IDS.append(int(x))
        except ValueError:
            print(f"Warning: ignoring invalid ADMIN_ID '{x}'")

APP_URL = os.getenv("APP_URL", "https://commercial-emma-robel-e81fbc32.koyeb.app")
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
        c.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions (
                        user_id INTEGER PRIMARY KEY,
                        expiry_date INTEGER NOT NULL)"""
        )
        conn.commit()
        conn.close()

def add_subscription(user_id, days=30):
    expiry = int(time.time()) + days * 86400
    with db_lock:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "REPLACE INTO subscriptions (user_id, expiry_date) VALUES (?, ?)",
            (user_id, expiry),
        )
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

init_db()

# -------------------- Flask App --------------------
app = Flask(__name__)

# -------------------- Telegram Bot Handlers (defined first) --------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Start command from user {update.effective_user.id}", flush=True)
    await update.message.reply_text(
        "Welcome! To get access to the private channel, please send a screenshot of your payment."
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    photo = update.message.photo[-1]
    caption = f"Payment screenshot from {user.full_name} (@{user.username}) ID: {user.id}"
    keyboard = [
        [
            InlineKeyboardButton("Approve", callback_data=f"approve:{user.id}"),
            InlineKeyboardButton("Decline", callback_data=f"decline:{user.id}"),
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
            )
        except Exception as e:
            print(f"Failed to send to admin {admin_id}: {e}", flush=True)

    await update.message.reply_text(
        "Your screenshot has been sent to the admins. We'll notify you once it's approved."
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id not in ADMIN_IDS:
        await query.edit_message_text("Unauthorized.")
        return

    action, user_id_str = query.data.split(":")
    user_id = int(user_id_str)

    if action == "approve":
        add_subscription(user_id)
        try:
            invite_link = await context.bot.create_chat_invite_link(
                chat_id=PRIVATE_CHANNEL_ID,
                member_limit=1,
                expire_date=int(time.time()) + 30 * 86400,
            )
            await context.bot.send_message(
                chat_id=user_id,
                text=f"✅ Your payment has been approved! Here is your 30-day invite link:\n{invite_link.invite_link}\n\nThe link expires in 30 days.",
            )
            await query.edit_message_text(f"✅ Approved user {user_id}.")
        except Exception as e:
            await query.edit_message_text(f"Approval failed: {e}")
    elif action == "decline":
        await query.edit_message_text(f"❌ Declined user {user_id}.")

async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("Unauthorized.")
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /approve <user_id> [days]")
        return
    try:
        user_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30
    except ValueError:
        await update.message.reply_text("Invalid arguments.")
        return

    add_subscription(user_id, days)
    try:
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=PRIVATE_CHANNEL_ID,
            member_limit=1,
            expire_date=int(time.time()) + days * 86400,
        )
        await context.bot.send_message(
            chat_id=user_id,
            text=f"An admin approved your subscription for {days} days! Link: {invite_link.invite_link}",
        )
        await update.message.reply_text(f"✅ Approved user {user_id} for {days} days.")
    except Exception as e:
        await update.message.reply_text(f"Approval failed: {e}")

# -------------------- Telegram Bot Setup --------------------
application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start_command))
application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(CommandHandler("approve", approve_command))

# Initialize the application once (synchronously)
async def init_app():
    await application.initialize()
    await application.start()
asyncio.run(init_app())

# Shutdown hook
def shutdown():
    asyncio.run(application.stop())
    asyncio.run(application.shutdown())
atexit.register(shutdown)

# -------------------- Flask Routes --------------------
@app.route("/")
def health():
    return "Bot is running", 200

@app.route("/status")
def status():
    return "OK", 200

@app.route("/webhook", methods=["POST"])
def webhook():
    """Handle incoming Telegram updates."""
    # Optional file log (keep for debugging)
    try:
        with open("/tmp/webhook.log", "a") as f:
            f.write(f"Webhook received at {time.time()}\n")
    except Exception as e:
        print(f"Error writing log: {e}", flush=True)

    try:
        data = request.get_json(force=True)
        async def process():
            update = Update.de_json(data, application.bot)
            await application.process_update(update)
        asyncio.run(process())
        return "OK", 200
    except Exception as e:
        print(f"❌ Error in webhook: {e}", flush=True)
        return "OK", 200

@app.route("/view_log")
def view_log():
    """View the webhook log file."""
    try:
        with open("/tmp/webhook.log", "r") as f:
            content = f.read()
        return f"<pre>{content}</pre>"
    except FileNotFoundError:
        return "No webhook hits yet."

@app.route("/set_webhook")
def set_webhook():
    """Register the webhook with Telegram."""
    async def set_hook():
        await application.bot.set_webhook(url=WEBHOOK_URL)
    asyncio.run(set_hook())
    return f"Webhook set to {WEBHOOK_URL}"

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

@app.route("/bot_info")
def bot_info():
    """Check bot token and get bot info."""
    async def get_me():
        return await application.bot.get_me()
    try:
        me = asyncio.run(get_me())
        return f"Bot: @{me.username} (ID: {me.id})"
    except Exception as e:
        return f"Error: {e}"

# -------------------- Run Flask --------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))