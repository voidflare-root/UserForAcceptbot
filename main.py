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

BOT_TOKEN = "YOUR_BOT_TOKEN"
DB = "bot.db"


def db():
    con = sqlite3.connect(DB)
    con.execute("""
    CREATE TABLE IF NOT EXISTS channels(
        user_id INTEGER,
        chat_id INTEGER,
        title TEXT,
        PRIMARY KEY(user_id, chat_id)
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS selected(
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER
    )
    """)
    con.execute("""
    CREATE TABLE IF NOT EXISTS pending(
        code TEXT PRIMARY KEY,
        user_id INTEGER
    )
    """)
    con.commit()
    return con


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "✅ Bot running\n\n"
        "Commands:\n"
        "/addchannel - apna channel connect karo\n"
        "/channels - connected channels dekho\n"
        "/use - channel select karo\n"
        "/post - forwarded message ko channel me copy karo\n\n"
        "Bot ko channel me admin banana zaroori hai."
    )


async def addchannel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    code = "CONNECT_" + secrets.token_hex(4).upper()

    con = db()
    con.execute("INSERT OR REPLACE INTO pending(code,user_id) VALUES(?,?)", (code, user_id))
    con.commit()
    con.close()

    await update.message.reply_text(
        "✅ Channel connect karne ke liye:\n\n"
        "1. Bot ko apne channel me admin banao\n"
        "2. Channel me ye code post karo:\n\n"
        f"`{code}`\n\n"
        "Bot automatic channel save kar dega.",
        parse_mode="Markdown"
    )


async def channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.channel_post
    if not msg or not msg.text:
        return

    code = msg.text.strip()

    con = db()
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
    except:
        pass

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Channel connected:\n{title}\n\nAb /post use karke forwarded message copy kar sakte ho."
    )


async def channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    con = db()
    rows = con.execute(
        "SELECT chat_id,title FROM channels WHERE user_id=?",
        (user_id,)
    ).fetchall()
    selected_row = con.execute(
        "SELECT chat_id FROM selected WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()

    if not rows:
        await update.message.reply_text("❌ Koi channel connected nahi hai. Pehle /addchannel use karo.")
        return

    selected_id = selected_row[0] if selected_row else None

    text = "📢 Your channels:\n\n"
    for i, row in enumerate(rows, start=1):
        mark = "✅" if row[0] == selected_id else "▫️"
        text += f"{mark} {i}. {row[1]}\nID: `{row[0]}`\n\n"

    text += "Channel select karne ke liye:\n/use channel_id"

    await update.message.reply_text(text, parse_mode="Markdown")


async def use_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text("Use karo:\n/use channel_id")
        return

    try:
        chat_id = int(context.args[0])
    except:
        await update.message.reply_text("❌ Galat channel ID.")
        return

    con = db()
    row = con.execute(
        "SELECT title FROM channels WHERE user_id=? AND chat_id=?",
        (user_id, chat_id)
    ).fetchone()

    if not row:
        con.close()
        await update.message.reply_text("❌ Ye channel aapke account me connected nahi hai.")
        return

    con.execute(
        "INSERT OR REPLACE INTO selected(user_id, chat_id) VALUES(?,?)",
        (user_id, chat_id)
    )
    con.commit()
    con.close()

    await update.message.reply_text(f"✅ Selected channel:\n{row[0]}")


async def post_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["waiting_post"] = True
    await update.message.reply_text(
        "✅ Ab jis message ko post karna hai, mujhe forward karo.\n\n"
        "Bot usko channel me copy karega, original channel ka link/name nahi dikhega."
    )


async def copy_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("waiting_post"):
        return

    user_id = update.effective_user.id

    con = db()
    row = con.execute(
        "SELECT chat_id FROM selected WHERE user_id=?",
        (user_id,)
    ).fetchone()
    con.close()

    if not row:
        await update.message.reply_text("❌ Pehle /addchannel se channel connect karo.")
        return

    target_chat_id = row[0]

    try:
        await context.bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id
        )

        context.user_data["waiting_post"] = False
        await update.message.reply_text("✅ Post copied without forward tag/link.")

    except Exception as e:
        await update.message.reply_text(
            "❌ Post copy nahi hua.\n\n"
            "Check karo:\n"
            "1. Bot channel me admin hai\n"
            "2. Bot ko post message permission hai\n"
            f"\nError: {e}"
        )


async def auto_accept(update: Update, context: ContextTypes.DEFAULT_TYPE):
    req = update.chat_join_request

    try:
        await context.bot.approve_chat_join_request(
            chat_id=req.chat.id,
            user_id=req.from_user.id
        )
        print(f"Accepted: {req.from_user.id} in {req.chat.title}")
    except Exception as e:
        print("Join accept error:", e)


def main():
    db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("addchannel", addchannel))
    app.add_handler(CommandHandler("channels", channels))
    app.add_handler(CommandHandler("use", use_channel))
    app.add_handler(CommandHandler("post", post_command))

    app.add_handler(ChatJoinRequestHandler(auto_accept))
    app.add_handler(MessageHandler(filters.ChatType.CHANNEL, channel_post))
    app.add_handler(MessageHandler(filters.ALL & filters.ChatType.PRIVATE, copy_post))

    print("Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
