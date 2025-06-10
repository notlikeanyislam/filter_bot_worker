from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, MessageHandler, CommandHandler,
    CallbackQueryHandler, ContextTypes,
    ConversationHandler, filters
)
import json, re, datetime, os
from config import TOKEN, ADMIN_IDS

FILTERS_FILE = os.path.join(os.path.dirname(__file__), 'filters.json')
WARNINGS_FILE = os.path.join(os.path.dirname(__file__), 'warnings.json')

SELECT_ACTION, ADD_WORD, REMOVE_WORD, CONFIRM_UNBAN, CONFIRM_DELETE = range(5)

# تحميل/حفظ JSON
def load_json(file):
    with open(file, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(file, data):
    with open(file, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.chat.type != "private":
        return

    keyboard = [
        [InlineKeyboardButton("🛑 الكلمات المحظورة", callback_data='show_filters')],
        [InlineKeyboardButton("📋 عرض السجلات", callback_data='detailed_logs')],
        [InlineKeyboardButton("🔓 إدارة الحظر", callback_data='manage_bans')],
        [InlineKeyboardButton("🗑️ حذف سجل مستخدم", callback_data='delete_log')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.message:
        await update.message.reply_text("👋 مرحباً، اختر أحد الخيارات:", reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text("👋 مرحباً، اختر أحد الخيارات:", reply_markup=reply_markup)

    return SELECT_ACTION

# فحص الرسائل
async def check_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id in ADMIN_IDS:
        return

    text = update.message.text
    filters_list = load_json(FILTERS_FILE)
    pattern = re.compile("|".join(filters_list), re.IGNORECASE)

    if pattern.search(text):
        try:
            await update.message.delete()
            warnings = load_json(WARNINGS_FILE)
            user_id = str(user.id)
            warnings.setdefault(user_id, {"count": 0, "log": [], "chat_id": update.message.chat_id})
            warnings[user_id]["count"] += 1
            warnings[user_id]["log"].append({
                "text": text,
                "time": datetime.datetime.now().isoformat()
            })
            save_json(WARNINGS_FILE, warnings)

            if warnings[user_id]["count"] >= 2:
                await context.bot.ban_chat_member(update.message.chat_id, user.id)
                await context.bot.send_message(chat_id=update.message.chat_id, text=f"🚫 تم حظر {user.full_name} بعد تكرار المخالفات.")
                for admin_id in ADMIN_IDS:
                    try:
                        await context.bot.send_message(admin_id, f"🚨 تم حظر المستخدم {user.full_name} (ID: {user_id}) بسبب تكرار المخالفات.")
                    except:
                        pass
            else:
                await context.bot.send_message(chat_id=update.message.chat_id, text=f"⚠️ تحذير {warnings[user_id]['count']}! سيتم حظرك بعد تحذيرين.")
        except Exception as e:
            print(f"❌ خطأ: {e}")

# الكلمات المحظورة
async def show_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    filters_list = load_json(FILTERS_FILE)
    words = "\n".join(f"- {w}" for w in filters_list) if filters_list else "⚠️ لا توجد كلمات محظورة"
    keyboard = [
        [InlineKeyboardButton("➕ إضافة كلمة", callback_data='add_word')],
        [InlineKeyboardButton("➖ حذف كلمة", callback_data='remove_word')],
        [InlineKeyboardButton("⬅️ رجوع", callback_data='start')],
    ]
    await query.edit_message_text(f"🛑 الكلمات المحظورة:\n{words}", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ACTION

async def ask_add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("✏️ أرسل الكلمة التي تريد إضافتها:")
    return ADD_WORD

async def receive_add_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = update.message.text.strip().split()
    filters_list = load_json(FILTERS_FILE)
    added = [word for word in words if word not in filters_list]

    filters_list.extend(added)
    save_json(FILTERS_FILE, filters_list)

    text = f"✅ تمت إضافة الكلمات:\n- " + "\n- ".join(added) if added else "⚠️ لا جديد."
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data='show_filters')]]))
    return SELECT_ACTION

async def ask_remove_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("✏️ أرسل الكلمة التي تريد حذفها:")
    return REMOVE_WORD

async def receive_remove_word(update: Update, context: ContextTypes.DEFAULT_TYPE):
    words = update.message.text.strip().split()
    filters_list = load_json(FILTERS_FILE)
    removed = [word for word in words if word in filters_list]

    for word in removed:
        filters_list.remove(word)
    save_json(FILTERS_FILE, filters_list)

    text = f"✅ تم حذف الكلمات:\n- " + "\n- ".join(removed) if removed else "⚠️ لم يتم العثور على الكلمات."
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data='show_filters')]]))
    return SELECT_ACTION

# عرض السجل المفصل
async def show_detailed_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    warnings = load_json(WARNINGS_FILE)

    if not warnings:
        await query.edit_message_text("📭 لا توجد مخالفات.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data='start')]]))
        return SELECT_ACTION

    messages = []
    for uid, data in warnings.items():
        entry = f"👤 ID: {uid} | تحذيرات: {data['count']}\n"
        for i, log in enumerate(data.get("log", []), 1):
            time = log['time'][:19].replace("T", " ")
            entry += f"   {i}. 🕒 {time}\n      💬 {log['text']}\n"
        messages.append(entry)

    for part in messages:
        await query.message.reply_text(part[:4096])

    await query.message.reply_text("✅ انتهى العرض.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data='start')]]))
    return SELECT_ACTION

# إدارة الحظر
async def manage_bans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    warnings = load_json(WARNINGS_FILE)
    banned = [uid for uid, data in warnings.items() if data["count"] >= 2]

    if not banned:
        await query.edit_message_text("🚫 لا يوجد مستخدمين محظورين حالياً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع", callback_data='start')]]))
        return SELECT_ACTION

    keyboard = [[InlineKeyboardButton(f"🔓 فك حظر {uid}", callback_data=f'confirm_unban_{uid}')] for uid in banned]
    keyboard.append([InlineKeyboardButton("⬅️ رجوع", callback_data='start')])
    await query.edit_message_text("🔒 المحظورون:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ACTION

async def confirm_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.data.split('_')[2]
    keyboard = [
        [InlineKeyboardButton("✅ نعم", callback_data=f'unban_{uid}'),
         InlineKeyboardButton("❌ إلغاء", callback_data='manage_bans')]
    ]
    await update.callback_query.edit_message_text(f"❓ هل تريد فك الحظر عن {uid}؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ACTION

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.data.split('_')[1]
    warnings = load_json(WARNINGS_FILE)
    chat_id = warnings.get(uid, {}).get("chat_id")
    if chat_id:
        await context.bot.unban_chat_member(chat_id=int(chat_id), user_id=int(uid))
        warnings[uid]["count"] = 1
        save_json(WARNINGS_FILE, warnings)
        await update.callback_query.edit_message_text(f"✅ تم فك الحظر عن {uid}")
    else:
        await update.callback_query.edit_message_text("⚠️ لا يمكن فك الحظر (chat_id مفقود).")
    return await manage_bans(update, context)

# حذف سجل مستخدم
async def delete_log_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    warnings = load_json(WARNINGS_FILE)
    keyboard = [[InlineKeyboardButton("⬅️ رجوع", callback_data='start')]]

    if not warnings:
        await update.callback_query.edit_message_text(
            "📭 لا توجد سجلات.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_ACTION

    for uid in warnings:
        keyboard.insert(0, [InlineKeyboardButton(f"🗑️ حذف سجل {uid}", callback_data=f'confirm_delete_{uid}')])

    await update.callback_query.edit_message_text(
        "🗑️ اختر مستخدم لحذف سجله:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_ACTION


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.data.split('_')[2]
    keyboard = [
        [InlineKeyboardButton("✅ نعم", callback_data=f'delete_{uid}'),
         InlineKeyboardButton("❌ إلغاء", callback_data='delete_log')]
    ]
    await update.callback_query.edit_message_text(f"❓ هل أنت متأكد من حذف سجل {uid}؟", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_ACTION

async def delete_log_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.data.split('_')[1]
    warnings = load_json(WARNINGS_FILE)
    if uid in warnings:
        del warnings[uid]
        save_json(WARNINGS_FILE, warnings)
        await update.callback_query.edit_message_text(f"✅ تم حذف سجل {uid}")
    else:
        await update.callback_query.edit_message_text("⚠️ لم يتم العثور على السجل.")
    return await delete_log_menu(update, context)

# تشغيل البوت
async def run():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(start, pattern="^start$")
        ],
        states={
            SELECT_ACTION: [
                CallbackQueryHandler(show_filters, pattern="^show_filters$"),
                CallbackQueryHandler(ask_add_word, pattern="^add_word$"),
                CallbackQueryHandler(ask_remove_word, pattern="^remove_word$"),
                CallbackQueryHandler(manage_bans, pattern="^manage_bans$"),
                CallbackQueryHandler(confirm_unban, pattern="^confirm_unban_"),
                CallbackQueryHandler(unban_user, pattern="^unban_"),
                CallbackQueryHandler(delete_log_menu, pattern="^delete_log$"),
                CallbackQueryHandler(confirm_delete, pattern="^confirm_delete_"),
                CallbackQueryHandler(delete_log_confirm, pattern="^delete_"),
                CallbackQueryHandler(show_detailed_logs, pattern="^detailed_logs$"),
                CallbackQueryHandler(start, pattern="^start$"),
            ],
            ADD_WORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_add_word)],
            REMOVE_WORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_remove_word)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, check_message))

    print("✅ البوت شغال...")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio, asyncio
    nest_asyncio.apply()
    asyncio.run(run())
