import os
import sqlite3
import secrets
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ChatJoinRequestHandler,
    ContextTypes,
    filters,
)

BOT_TOKEN = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
DB = "bot.db"


def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS channels(
        user_id INTEGER,
        chat_id INTEGER,
        title TEXT,
        PRIMARY KEY(user_id, chat_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS selected(
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pending(
        code TEXT PRIMARY KEY,
        user_id INTEGER
    )
    """)

    con.commit()
    con.close()


def get_db():
    return sqlite3.connect(DB)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running\n\n"
        "/addchannel - channel connect\n"
        "/channels - channel list\n"
        "/use CHANNEL_ID - channel select\n"
        "/post - forwarded post copy\n\n"
        "Bot ko channel admin banao."
    )


async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = "CONNECT_" + secrets.token_hex(4).upper()

    con = get_db()
    con.execute("INSERT OR REPLACE INTO pending(code,user_id) VALUES(?,?)", (code, user_id))
    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ Channel connect steps:\n\n"
        "1. Bot ko channel admin banao\n"
        "2. Channel me ye code send/post karo:\n\n"
        f"{code}\n\n"
        "Bot channel auto save kar dega."
    )


async def save_channel_from_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post

    if not msg or not msg.text:
        return

    code = msg.text.strip()

    con = get_db()
    row = con.execute("SELECT user_id FROM pending WHERE code=?", (code,)).fetchone()

    if not row:
        con.close()
        return

    user_id = row[0]
    chat_id = msg.chat.id
    title = msg.chat.title or "My Channel"

    con.execute(
        "INSERT OR REPLACE INTO channels(user_id, chat_id, title) VALUES(?,?,?)",
        (user_id, chat_id, title)
    )
    con.execute(
        "INSERT OR REPLACE INTO selected(user_id, chat_id) VALUES(?,?)",
        (user_id, chat_id)
    )
    con.execute("DELETE FROM pending WHERE code=?", (code,))
    con.commit()
    con.close()

    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=msg.message_id)
    except Exception:
        pass

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✅ Channel connected:\n{title}"
        )
    except Exception:
        pass


async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    con = get_db()
    rows = con.execute(
        "SELECT chat_id,title FROM channels WHERE user_id=?",
        (user_id,)
    ).fetchall()
    con.close()

    if not rows:
        await update.message.reply_text("❌ Pehle /addchannel use karo.")
        return

    text = "📢 Your channels:\n\n"
    for i, (chat_id, title) in enumerate(rows, 1):
        text += f"{i}. {title}\nID: {chat_id}\n\n"

    text += "Select:\n/use CHANNEL_ID"
    await update.message.reply_text(text)


async def use_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Use:\n/use CHANNEL_ID")
        return

    try:
        chat_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid channel ID.")
        return

    con = get_db()
    row = con.execute(
        "SELECT title FROM channels WHERE user_id=? AND chat_id=?",
        (user_id, chat_id)
    ).fetchone()

    if not row:
        con.close()
        await update.message.reply_text("❌ Ye channel connected nahi hai.")
        return

    con.execute(
        "INSERT OR REPLACE INTO selected(user_id, chat_id) VALUES(?,?)",
        (user_id, chat_id)
    )
    con.commit()
    con.close()

    await update.message.reply_text(f"✅ Selected: {row[0]}")


async def post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_post"] = True
    await update.message.reply_text(
        "✅ Ab forwarded message bhejo.\n"
        "Bot usko copy karega, forward source/link hide rahega."
    )


async def copy_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_post"):
        return

    user_id = update.effective_user.id

    con = get_db()
    row = con.execute("SELECT chat_id FROM selected WHERE user_id=?", (user_id,)).fetchone()
    con.close()

    if not row:
        await update.message.reply_text("❌ Pehle /addchannel use karo.")
        return

    try:
        await context.bot.copy_message(
            chat_id=row[0],
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )
        context.user_data["waiting_post"] = False
        await update.message.reply_text("✅ Posted without forward tag/link.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error:\n{e}")


async def auto_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request

    try:
        await context.bot.approve_chat_join_request(
            chat_id=req.chat.id,
            user_id=req.from_user.id
        )
    except Exception as e:
        print("Accept error:", e)


def main():
    if BOT_TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        print("❌ BOT_TOKEN add karo.")
        return

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", addchannel))
    app.add_handler(CommandHandler("channels", channels))
    app.add_handler(CommandHandler("use", use_channel))
    app.add_handler(CommandHandler("post", post))

    app.add_handler(ChatJoinRequestHandler(auto_accept))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, save_channel_from_code))
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, copy_post))

    print("✅ Bot started...")
    app.run_polling()


if __name__ == "__main__":
    main()
