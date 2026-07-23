import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import requests
import re
import time

TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise ValueError("TOKEN не задан в переменных окружения")
CHANNEL_ID = "@Zhirick_script"
ADMIN_ID = 6382264272

bot = telebot.TeleBot(TOKEN)

SCRIPTS_FILE = "scripts.json"
ADMINS_FILE = "admins.json"

if os.path.exists(SCRIPTS_FILE):
    with open(SCRIPTS_FILE, "r") as f:
        SCRIPTS = json.load(f)
else:
    SCRIPTS = {}
    with open(SCRIPTS_FILE, "w") as f:
        json.dump(SCRIPTS, f)

if os.path.exists(ADMINS_FILE):
    with open(ADMINS_FILE, "r") as f:
        ADMINS = json.load(f)
else:
    ADMINS = [ADMIN_ID]
    with open(ADMINS_FILE, "w") as f:
        json.dump(ADMINS, f)

def save_scripts():
    with open(SCRIPTS_FILE, "w") as f:
        json.dump(SCRIPTS, f)

def save_admins():
    with open(ADMINS_FILE, "w") as f:
        json.dump(ADMINS, f)

def is_admin(user_id):
    return user_id in ADMINS

def is_subscribed(user_id):
    if is_admin(user_id):
        return True
    try:
        member = bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

user_state = {}

def show_admin_panel(chat_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Добавить скрипт", callback_data="add_script"),
        InlineKeyboardButton("🗑 Удалить скрипт", callback_data="delete_script"),
        InlineKeyboardButton("📋 Список скриптов", callback_data="list_scripts"),
        InlineKeyboardButton("👥 Админы", callback_data="manage_admins"),
        InlineKeyboardButton("📤 Получить ссылку", callback_data="get_link"),
        InlineKeyboardButton("❌ Закрыть", callback_data="close_panel")
    )
    bot.send_message(chat_id, "🔐 Панель:", reply_markup=markup)

@bot.message_handler(commands=['start'])
def start_cmd(message):
    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        if key in SCRIPTS:
            if is_subscribed(message.from_user.id):
                bot.send_message(message.chat.id, f"```lua\n{SCRIPTS[key]}\n```", parse_mode="Markdown")
            else:
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("📢 Подписаться", url="https://t.me/Zhirick_script"))
                bot.send_message(message.chat.id, "❌ Подпишись на канал!", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, "❌ Такого скрипта нет")
    else:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("🔓 Bypass", callback_data="bypass"),
            InlineKeyboardButton("👥 Админы", callback_data="admin_panel")
        )
        bot.send_message(message.chat.id, "👋 Привет! Выбери действие:", reply_markup=markup)

@bot.message_handler(commands=['bypass'])
def bypass_cmd(message):
    user_state[message.chat.id] = "awaiting_bypass_link"
    bot.send_message(message.chat.id, "Вставь ссылку для обхода:")

@bot.message_handler(commands=['admins'])
def admin_cmd(message):
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id, "❌ Нет прав")
        return
    show_admin_panel(message.chat.id)

def bypass_link(link):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(link, timeout=15, allow_redirects=True)
        matches = re.findall(r'[A-Za-z0-9_\-=+]{20,}', response.text)
        if matches:
            return matches[0]
        return None
    except:
        return None

@bot.callback_query_handler(func=lambda call: True)
def handle(call):
    chat_id = call.message.chat.id
    uid = call.from_user.id
    data = call.data

    if data == "bypass":
        user_state[chat_id] = "awaiting_bypass_link"
        bot.send_message(chat_id, "Вставь ссылку для обхода:")
        return

    if data == "admin_panel":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "❌ Нет прав")
            return
        show_admin_panel(chat_id)
        return

    if data == "close_panel":
        bot.delete_message(chat_id, call.message.message_id)
        return

    if data == "add_script":
        user_state[chat_id] = "add_script"
        bot.send_message(chat_id, "Введи ключ и скрипт через запятую:\n`ключ, loadstring(...)`", parse_mode="Markdown")
        return

    if data == "delete_script":
        user_state[chat_id] = "delete_script"
        bot.send_message(chat_id, "Введи ключ:")
        return

    if data == "list_scripts":
        if not SCRIPTS:
            bot.send_message(chat_id, "Пусто")
        else:
            text = "📋 Список:\n" + "\n".join(f"• {k}" for k in SCRIPTS.keys())
            bot.send_message(chat_id, text)
        return

    if data == "get_link":
        user_state[chat_id] = "get_link"
        bot.send_message(chat_id, "Введи ключ:")
        return

    if data == "manage_admins":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("➕ Добавить", callback_data="add_admin"),
            InlineKeyboardButton("➖ Удалить", callback_data="remove_admin"),
            InlineKeyboardButton("📋 Список", callback_data="list_admins"),
            InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin")
        )
        bot.send_message(chat_id, "👥 Админы:", reply_markup=markup)
        return

    if data == "add_admin":
        user_state[chat_id] = "add_admin"
        bot.send_message(chat_id, "Введи ID админа:")
        return

    if data == "remove_admin":
        user_state[chat_id] = "remove_admin"
        bot.send_message(chat_id, "Введи ID:")
        return

    if data == "list_admins":
        text = "👥 Админы:\n" + "\n".join(f"• {a}" for a in ADMINS)
        bot.send_message(chat_id, text)
        return

    if data == "back_to_admin":
        show_admin_panel(chat_id)
        return

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    state = user_state.get(chat_id)

    if state == "awaiting_bypass_link":
        link = message.text.strip()
        if not link.startswith("http"):
            bot.send_message(chat_id, "❌ Это не ссылка")
            return
        key = bypass_link(link)
        if key:
            bot.send_message(chat_id, f"✅ Ключ: `{key}`", parse_mode="Markdown")
        else:
            bot.send_message(chat_id, "❌ Не удалось")
        user_state[chat_id] = None
        return

    if state == "add_script":
        try:
            key, script = message.text.split(",", 1)
            key = key.strip()
            script = script.strip()
            SCRIPTS[key] = script
            save_scripts()
            bot.send_message(chat_id, f"✅ {key} добавлен")
        except:
            bot.send_message(chat_id, "❌ Ошибка")
        user_state[chat_id] = None
        show_admin_panel(chat_id)
        return

    if state == "delete_script":
        key = message.text.strip()
        if key in SCRIPTS:
            del SCRIPTS[key]
            save_scripts()
            bot.send_message(chat_id, f"🗑 {key} удалён")
        else:
            bot.send_message(chat_id, "❌ Не найден")
        user_state[chat_id] = None
        show_admin_panel(chat_id)
        return

    if state == "get_link":
        key = message.text.strip()
        if key in SCRIPTS:
            link = f"https://t.me/{bot.get_me().username}?start={key}"
            bot.send_message(chat_id, f"🔗 {link}")
        else:
            bot.send_message(chat_id, "❌ Не найден")
        user_state[chat_id] = None
        show_admin_panel(chat_id)
        return

    if state == "add_admin":
        try:
            uid = int(message.text.strip())
            if uid not in ADMINS:
                ADMINS.append(uid)
                save_admins()
                bot.send_message(chat_id, "✅ Добавлен")
            else:
                bot.send_message(chat_id, "Уже админ")
        except:
            bot.send_message(chat_id, "❌ Ошибка")
        user_state[chat_id] = None
        show_admin_panel(chat_id)
        return

    if state == "remove_admin":
        try:
            uid = int(message.text.strip())
            if uid != ADMIN_ID and uid in ADMINS:
                ADMINS.remove(uid)
                save_admins()
                bot.send_message(chat_id, "🗑 Удалён")
            else:
                bot.send_message(chat_id, "❌ Нельзя или не найден")
        except:
            bot.send_message(chat_id, "❌ Ошибка")
        user_state[chat_id] = None
        show_admin_panel(chat_id)
        return

print("✅ Бот запущен!")
bot.polling()
