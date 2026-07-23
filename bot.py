import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import requests
import re
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime

TOKEN = "8677564847:AAFTiom_OcaG4aHOvo0WHFWCrVgy0kiKHlQ"

CHANNEL_ID = "@Zhirick_script"
ADMIN_ID   = 6382264272
BOT_START  = time.time()

bot = telebot.TeleBot(TOKEN)

PHOTOS = {
    "welcome":        "photos/welcome.jpg",
    "loading":        "photos/loading.jpg",
    "bypass_success": "photos/bypass_success.jpg",
    "script_got":     "photos/script_got.jpg",
}

def send_photo(chat_id, photo_key, caption=None, reply_markup=None, parse_mode=None):
    path = PHOTOS.get(photo_key)
    if path and os.path.exists(path):
        with open(path, "rb") as f:
            return bot.send_photo(chat_id, f, caption=caption,
                                  reply_markup=reply_markup, parse_mode=parse_mode)
    return bot.send_message(chat_id, caption or "",
                            reply_markup=reply_markup, parse_mode=parse_mode)

# ── Файлы хранилищ ────────────────────────────────────────────────────────────
SCRIPTS_FILE      = "scripts.json"
ADMINS_FILE       = "admins.json"
MODERATORS_FILE   = "moderators.json"
MUTED_FILE        = "muted.json"
SUGGESTIONS_FILE  = "suggestions.json"
USERS_FILE        = "users.json"         # {uid: {"name": ..., "joined": timestamp}}
SCRIPT_STATS_FILE = "script_stats.json"  # {key: count}
LINK_VER_FILE     = "link_verified.json" # [uid, ...]   — прошли по ссылке

def _load(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    data = default() if callable(default) else default
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return data

def _save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

SCRIPTS       = _load(SCRIPTS_FILE,      dict)
ADMINS        = _load(ADMINS_FILE,       lambda: [ADMIN_ID])
MODERATORS    = _load(MODERATORS_FILE,   list)
MUTED         = _load(MUTED_FILE,        list)
SUGGESTIONS   = _load(SUGGESTIONS_FILE,  dict)
USERS         = _load(USERS_FILE,        dict)   # str(uid) → info
SCRIPT_STATS  = _load(SCRIPT_STATS_FILE, dict)
LINK_VERIFIED = _load(LINK_VER_FILE,     list)   # uid (int) прошедших по ссылке

def save_scripts():       _save(SCRIPTS_FILE,      SCRIPTS)
def save_admins():        _save(ADMINS_FILE,        ADMINS)
def save_moderators():    _save(MODERATORS_FILE,    MODERATORS)
def save_muted():         _save(MUTED_FILE,         MUTED)
def save_suggestions():   _save(SUGGESTIONS_FILE,   SUGGESTIONS)
def save_users():         _save(USERS_FILE,          USERS)
def save_script_stats():  _save(SCRIPT_STATS_FILE,  SCRIPT_STATS)
def save_link_verified(): _save(LINK_VER_FILE,      LINK_VERIFIED)

def register_user(user):
    key = str(user.id)
    if key not in USERS:
        name = (user.first_name or "") + (" " + user.last_name if user.last_name else "")
        USERS[key] = {
            "name":   name.strip(),
            "uname":  user.username or "",
            "joined": int(time.time()),
        }
        save_users()

def inc_script_stat(key):
    SCRIPT_STATS[key] = SCRIPT_STATS.get(key, 0) + 1
    save_script_stats()

# ── Тех. перерыв ─────────────────────────────────────────────────────────────
MAINTENANCE = {"active": False, "reason": "", "until": 0}

def maintenance_active() -> bool:
    if not MAINTENANCE["active"]:
        return False
    if MAINTENANCE["until"] and time.time() > MAINTENANCE["until"]:
        MAINTENANCE["active"] = False
        return False
    return True

def maintenance_text() -> str:
    lines = [
        "┌──────────────────────┐",
        "│  🔧  ТЕХ. ПЕРЕРЫВ  🔧  │",
        "└──────────────────────┘",
        "",
    ]
    if MAINTENANCE["reason"]:
        lines.append(st("📌 Причина: ") + MAINTENANCE["reason"])
    if MAINTENANCE["until"]:
        mins_left = max(0, int((MAINTENANCE["until"] - time.time()) / 60))
        lines.append(st(f"⏱ Осталось: ~ {mins_left} мин."))
    else:
        lines.append(st("⏳ Время окончания не указано"))
    lines += ["", st("🙏 Возвращайся чуть позже!")]
    return "\n".join(lines)

# ── Роли ──────────────────────────────────────────────────────────────────────
def is_admin(uid):     return uid in ADMINS
def is_moderator(uid): return uid in MODERATORS or uid in ADMINS
def is_muted(uid):     return uid in MUTED

def is_subscribed(uid):
    if is_admin(uid):
        return True
    try:
        m = bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ["member", "administrator", "creator"]
    except:
        return False

REQUIRED_LINK = "https://t.me/easy_roblox_bot?start=8353477872"

def check_required_link(uid):
    """True если пользователь подтвердил переход по ссылке."""
    return is_admin(uid) or uid in LINK_VERIFIED

# ── Unicode-стиль ─────────────────────────────────────────────────────────────
_STYLE_MAP = {
    'а':'ᴀ','б':'ʙ','в':'ᴠ','е':'ᴇ','к':'ᴋ','л':'ᴧ','м':'ᴍ','о':'ᴏ',
    'п':'ᴨ','р':'ᴩ','с':'ᴄ','т':'ᴛ','у':'ᴜ','х':'х',
    'А':'ᴀ','Б':'ʙ','В':'ᴠ','Е':'ᴇ','К':'ᴋ','Л':'ᴧ','М':'ᴍ','О':'ᴏ',
    'П':'ᴨ','Р':'ᴩ','С':'ᴄ','Т':'ᴛ','У':'ᴜ',
    'a':'ᴀ','b':'ʙ','c':'ᴄ','d':'ᴅ','e':'ᴇ','f':'ꜰ','g':'ɢ','h':'ʜ',
    'i':'ɪ','j':'ᴊ','k':'ᴋ','l':'ʟ','m':'ᴍ','n':'ɴ','o':'ᴏ','p':'ᴘ',
    'r':'ʀ','s':'s','t':'ᴛ','u':'ᴜ','v':'ᴠ','w':'ᴡ','y':'ʏ','z':'ᴢ',
    'A':'ᴀ','B':'ʙ','C':'ᴄ','D':'ᴅ','E':'ᴇ','F':'ꜰ','G':'ɢ','H':'ʜ',
    'I':'ɪ','J':'ᴊ','K':'ᴋ','L':'ʟ','M':'ᴍ','N':'ɴ','O':'ᴏ','P':'ᴘ',
    'R':'ʀ','T':'ᴛ','U':'ᴜ','V':'ᴠ','W':'ᴡ','Y':'ʏ','Z':'ᴢ',
}
def st(text: str) -> str:
    return ''.join(_STYLE_MAP.get(ch, ch) for ch in text)

SEP = "▰▱▰▱▰▱▰▱▰▱▰▱▰▱▰"

# ── Состояния ─────────────────────────────────────────────────────────────────
user_state   = {}
_sug_counter = [len(SUGGESTIONS)]

def next_sug_id() -> str:
    _sug_counter[0] += 1
    return str(_sug_counter[0])

# ── Вспомогательные функции ───────────────────────────────────────────────────
def uptime_str() -> str:
    secs  = int(time.time() - BOT_START)
    h, r  = divmod(secs, 3600)
    m, s  = divmod(r, 60)
    return f"{h}ч {m}м {s}с"

# ── Панели ────────────────────────────────────────────────────────────────────
def show_admin_panel(chat_id):
    maint_btn = (
        InlineKeyboardButton("✅ Снять перерыв", callback_data="maint_off")
        if maintenance_active()
        else InlineKeyboardButton("🔧 Тех. перерыв", callback_data="maint_on")
    )
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Добавить скрипт",  callback_data="add_script"),
        InlineKeyboardButton("🗑 Удалить скрипт",   callback_data="delete_script"),
        InlineKeyboardButton("📋 Список скриптов",  callback_data="list_scripts"),
        InlineKeyboardButton("👥 Админы",           callback_data="manage_admins"),
        InlineKeyboardButton("🛡 Модераторы",        callback_data="manage_mods"),
        InlineKeyboardButton("📤 Получить ссылку",  callback_data="get_link"),
        InlineKeyboardButton("📊 Статистика",        callback_data="stats"),
        maint_btn,
        InlineKeyboardButton("❌ Закрыть",          callback_data="close_panel"),
    )
    text = (
        f"╔══════════════════╗\n"
        f"║  🔐  {st('ПАНЕЛЬ УПРАВЛЕНИЯ')}  ║\n"
        f"╚══════════════════╝\n"
        f"{SEP}\n"
        f"🗂 {st('Скриптов')}: {len(SCRIPTS)}  •  "
        f"👥 {st('Адм.')}: {len(ADMINS)}  •  "
        f"🛡 {st('Мод.')}: {len(MODERATORS)}\n"
        f"👤 {st('Всего юзеров')}: {len(USERS)}\n"
        f"{SEP}"
    )
    bot.send_message(chat_id, text, reply_markup=markup)

def show_stats(chat_id):
    # Считаем топ скриптов
    top = sorted(SCRIPT_STATS.items(), key=lambda x: x[1], reverse=True)[:5]
    top_text = "\n".join(f"  🔹 `{k}` — {v} раз" for k, v in top) if top else f"  {st('Пока нет данных')}"
    # Дата запуска
    started = datetime.fromtimestamp(BOT_START).strftime("%d.%m.%Y %H:%M")
    text = (
        f"📊 {st('Статистика бота')}\n"
        f"{SEP}\n"
        f"👤 {st('Уникальных пользователей')}: *{len(USERS)}*\n"
        f"🔇 {st('Замучено')}: *{len(MUTED)}*\n"
        f"📬 {st('Предложений получено')}: *{len(SUGGESTIONS)}*\n"
        f"{SEP}\n"
        f"🗂 {st('Скриптов в базе')}: *{len(SCRIPTS)}*\n"
        f"📈 {st('Топ скриптов по выдачам')}:\n{top_text}\n"
        f"{SEP}\n"
        f"⏱ {st('Аптайм')}: *{uptime_str()}*\n"
        f"🚀 {st('Запущен')}: {started}"
    )
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("🔙 Назад", callback_data="back_to_admin"))
    bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

def moderator_buttons(sug_id: str, user_id: int) -> InlineKeyboardMarkup:
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("🗑 Удалить",  callback_data=f"sug_del_{sug_id}"),
        InlineKeyboardButton("🔇 Мутить",  callback_data=f"sug_mute_{sug_id}_{user_id}"),
    )
    return markup

# ── /start ────────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    register_user(message.from_user)

    if maintenance_active() and not is_admin(uid):
        bot.send_message(message.chat.id, maintenance_text())
        return

    args = message.text.split()
    if len(args) > 1:
        key = args[1]
        if key in SCRIPTS:
            subscribed = is_subscribed(uid)
            link_ok    = check_required_link(uid)

            if subscribed and link_ok:
                # ✅ Оба условия выполнены — выдаём скрипт
                inc_script_stat(key)
                caption = (
                    f"🎉 {st('Скрипт получен!')}\n"
                    f"{SEP}\n"
                    f"```lua\n{SCRIPTS[key]}\n```"
                )
                send_photo(message.chat.id, "script_got",
                           caption=caption, parse_mode="Markdown")

            elif not subscribed and not link_ok:
                # ❌ Оба условия не выполнены
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(
                    InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/Zhirick_script"),
                    InlineKeyboardButton("🔗 Перейти по ссылке",   url=REQUIRED_LINK),
                    InlineKeyboardButton("✅ Я всё сделал!",        callback_data=f"link_done_{key}"),
                )
                send_photo(message.chat.id, "welcome",
                           caption=(
                               f"🚫 {st('Выполни оба условия:')}\n"
                               f"{SEP}\n"
                               f"1️⃣ 📢 {st('Подпишись на')} @Zhirick_script\n"
                               f"2️⃣ 🔗 {st('Перейди по ссылке ниже')}\n"
                               f"{SEP}\n"
                               f"💡 {st('После этого нажми')} ✅ {st('Я всё сделал!')}"
                           ),
                           reply_markup=markup)

            elif not subscribed:
                # ❌ Только не подписан
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(
                    InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/Zhirick_script"),
                    InlineKeyboardButton("✅ Я подписался!",         callback_data=f"link_done_{key}"),
                )
                send_photo(message.chat.id, "welcome",
                           caption=(
                               f"🚫 {st('Доступ закрыт!')}\n"
                               f"{SEP}\n"
                               f"📢 {st('Подпишись на канал')} @Zhirick_script\n"
                               f"💡 {st('Затем нажми')} ✅ {st('Я подписался!')}"
                           ),
                           reply_markup=markup)

            else:
                # ❌ Только ссылку не нажал
                markup = InlineKeyboardMarkup(row_width=1)
                markup.add(
                    InlineKeyboardButton("🔗 Перейти по ссылке", url=REQUIRED_LINK),
                    InlineKeyboardButton("✅ Я перешёл!",         callback_data=f"link_done_{key}"),
                )
                send_photo(message.chat.id, "welcome",
                           caption=(
                               f"⚠️ {st('Почти готово!')}\n"
                               f"{SEP}\n"
                               f"🔗 {st('Перейди по ссылке ниже')}\n"
                               f"💡 {st('Затем нажми')} ✅ {st('Я перешёл!')}"
                           ),
                           reply_markup=markup)
        else:
            bot.send_message(message.chat.id,
                f"❌ {st('Скрипт не найден!')}\n"
                f"{SEP}\n"
                f"🔎 {st('Проверь правильность ключа.')}")
    else:
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("⚡ Bypass",       callback_data="bypass"),
            InlineKeyboardButton("📬 Предложка",    callback_data="predloshka"),
            InlineKeyboardButton("❓ Помощь",        callback_data="help"),
            InlineKeyboardButton("🔑 Панель",        callback_data="admin_panel"),
        )
        caption = (
            f"👋 {st('Привет')}, {message.from_user.first_name}!\n"
            f"{SEP}\n"
            f"🤖 {st('Добро пожаловать в бот!')}\n"
            f"📌 {st('Выбери действие ниже:')}\n"
            f"{SEP}"
        )
        send_photo(message.chat.id, "welcome", caption=caption, reply_markup=markup)

# ── /help ─────────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['help'])
def help_cmd(message):
    register_user(message.from_user)
    send_help(message.chat.id)

def send_help(chat_id):
    text = (
        f"❓ {st('КАК ПОЛУЧИТЬ СКРИПТ')}\n"
        f"{SEP}\n\n"
        f"1️⃣  📢 {st('Подпишись на канал:')}\n"
        f"       👉 @Zhirick_script\n\n"
        f"2️⃣  🔗 {st('Перейди по обязательной ссылке:')}\n"
        f"       👉 easy_roblox_bot\n\n"
        f"3️⃣  📌 {st('Найди пост с нужным скриптом в канале и нажми кнопку-ссылку в нём.')}\n\n"
        f"4️⃣  ✅ {st('Нажми')} «{st('Я всё сделал!')}» — {st('скрипт придёт автоматически!')}\n\n"
        f"{SEP}\n"
        f"⚡ {st('Bypass')} — {st('обход ссылок-защит (linkvertise и др.)')}\n"
        f"📬 {st('Предложка')} — {st('написать пожелание модераторам')}\n"
        f"{SEP}\n"
        f"❗ {st('Оба условия обязательны для получения скрипта!')}"
    )
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📢 Канал @Zhirick_script", url="https://t.me/Zhirick_script"),
        InlineKeyboardButton("🔗 Обязательная ссылка",  url=REQUIRED_LINK),
    )
    bot.send_message(chat_id, text, reply_markup=markup)

# ── /predloshka ───────────────────────────────────────────────────────────────
@bot.message_handler(commands=['predloshka'])
def predloshka_cmd(message):
    uid = message.from_user.id
    register_user(message.from_user)
    if maintenance_active() and not is_admin(uid):
        bot.send_message(message.chat.id, maintenance_text())
        return
    if is_muted(uid):
        bot.send_message(message.chat.id,
            f"🔇 {st('Ты замучен!')}\n"
            f"{SEP}\n"
            f"😶 {st('Ты не можешь отправлять предложения.')}")
        return
    user_state[message.chat.id] = "predloshka"
    bot.send_message(message.chat.id,
        f"📬 {st('Предложка')}\n"
        f"{SEP}\n"
        f"✏️ {st('Напиши своё предложение.')}\n"
        f"👁 {st('Его увидят только модераторы.')}\n"
        f"{SEP}")

# ── /bypass ───────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['bypass'])
def bypass_cmd(message):
    uid = message.from_user.id
    register_user(message.from_user)
    if maintenance_active() and not is_admin(uid):
        bot.send_message(message.chat.id, maintenance_text())
        return
    user_state[message.chat.id] = "awaiting_bypass_link"
    bot.send_message(message.chat.id,
        f"⚡ {st('Bypass')}\n"
        f"{SEP}\n"
        f"🔗 {st('Вставь ссылку для обхода:')}")

# ── /admins ───────────────────────────────────────────────────────────────────
@bot.message_handler(commands=['admins'])
def admin_cmd(message):
    register_user(message.from_user)
    if not is_admin(message.from_user.id):
        bot.send_message(message.chat.id,
            f"🚫 {st('Нет прав!')}\n"
            f"{SEP}\n"
            f"🔐 {st('Эта команда только для администраторов.')}")
        return
    show_admin_panel(message.chat.id)

# ── Bypass-логика ─────────────────────────────────────────────────────────────
def bypass_link(link):
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        }
        session = requests.Session()
        session.headers.update(headers)
        response = session.get(link, timeout=15, allow_redirects=True)
        matches = re.findall(r'[A-Za-z0-9_\-=+]{20,}', response.text)
        if matches:
            return matches[0]
        for _, value in response.headers.items():
            matches = re.findall(r'[A-Za-z0-9_\-=+]{20,}', str(value))
            if matches:
                return matches[0]
        if "iframe" in response.text or "script" in response.text:
            for url in re.findall(r'https?://[^\s"\'<>]+', response.text):
                if any(x in url for x in ("auth", "key", "token")):
                    try:
                        sub = session.get(url, timeout=10, allow_redirects=True)
                        matches = re.findall(r'[A-Za-z0-9_\-=+]{20,}', sub.text)
                        if matches:
                            return matches[0]
                    except:
                        continue
        return None
    except:
        return None

# ── Callback-хэндлеры ─────────────────────────────────────────────────────────
@bot.callback_query_handler(func=lambda call: call.data.startswith("copy_"))
def copy_key(call):
    key = call.data.replace("copy_", "")
    bot.answer_callback_query(call.id, st(f"Ключ: {key}"), show_alert=False)

@bot.callback_query_handler(func=lambda call: True)
def handle(call):
    chat_id = call.message.chat.id
    uid     = call.from_user.id
    data    = call.data

    register_user(call.from_user)

    # ── Подтверждение выполнения условий → выдача скрипта ────────────────────
    if data.startswith("link_done_"):
        key = data[len("link_done_"):]

        # Помечаем пользователя как прошедшего по ссылке
        if uid not in LINK_VERIFIED:
            LINK_VERIFIED.append(uid)
            save_link_verified()

        # Повторно проверяем подписку на канал
        if not is_subscribed(uid):
            markup = InlineKeyboardMarkup(row_width=1)
            markup.add(
                InlineKeyboardButton("📢 Подписаться на канал", url="https://t.me/Zhirick_script"),
                InlineKeyboardButton("✅ Я подписался!",         callback_data=f"link_done_{key}"),
            )
            bot.answer_callback_query(call.id, "❌ Ты ещё не подписан на канал!", show_alert=True)
            return

        # Оба условия выполнены
        if key in SCRIPTS:
            inc_script_stat(key)
            caption = (
                f"🎉 {st('Скрипт получен!')}\n"
                f"{SEP}\n"
                f"```lua\n{SCRIPTS[key]}\n```"
            )
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except:
                pass
            send_photo(chat_id, "script_got", caption=caption, parse_mode="Markdown")
        else:
            bot.answer_callback_query(call.id, "❌ Скрипт не найден", show_alert=True)
        return

    # ── Предложка: удалить ────────────────────────────────────────────────────
    if data.startswith("sug_del_"):
        if not is_moderator(uid):
            bot.answer_callback_query(call.id, "🚫 Нет прав", show_alert=True)
            return
        sug_id = data[len("sug_del_"):]
        sug = SUGGESTIONS.get(sug_id)
        if sug:
            for mod_cid, msg_id in sug.get("deliveries", []):
                try:
                    bot.delete_message(mod_cid, msg_id)
                except:
                    pass
            del SUGGESTIONS[sug_id]
            save_suggestions()
        else:
            bot.answer_callback_query(call.id, "⚠️ Уже удалено")
        bot.answer_callback_query(call.id, "🗑 Предложение удалено")
        return

    # ── Предложка: мутить ─────────────────────────────────────────────────────
    if data.startswith("sug_mute_"):
        if not is_moderator(uid):
            bot.answer_callback_query(call.id, "🚫 Нет прав", show_alert=True)
            return
        # формат: sug_mute_<sug_id>_<user_id>
        # sug_id может быть числом, user_id — тоже число; берём последний кусок
        parts    = data.split("_")  # ['sug','mute','<id>','<uid>']
        mute_uid = int(parts[-1])
        sug_id   = parts[-2]
        if mute_uid not in MUTED:
            MUTED.append(mute_uid)
            save_muted()
        new_markup = InlineKeyboardMarkup()
        new_markup.add(
            InlineKeyboardButton("🗑 Удалить",  callback_data=f"sug_del_{sug_id}"),
            InlineKeyboardButton("✅ Замучен",  callback_data="noop"),
        )
        try:
            bot.edit_message_reply_markup(chat_id, call.message.message_id,
                                          reply_markup=new_markup)
        except:
            pass
        bot.answer_callback_query(call.id, f"🔇 Пользователь замучен", show_alert=True)
        return

    if data == "noop":
        bot.answer_callback_query(call.id)
        return

    # ── Помощь ────────────────────────────────────────────────────────────────
    if data == "help":
        send_help(chat_id)
        return

    # ── Предложка (кнопка /start) ─────────────────────────────────────────────
    if data == "predloshka":
        if maintenance_active() and not is_admin(uid):
            bot.answer_callback_query(call.id, "🔧 Тех. перерыв!", show_alert=True)
            return
        if is_muted(uid):
            bot.answer_callback_query(call.id, "🔇 Ты замучен!", show_alert=True)
            return
        user_state[chat_id] = "predloshka"
        bot.send_message(chat_id,
            f"📬 {st('Предложка')}\n"
            f"{SEP}\n"
            f"✏️ {st('Напиши своё предложение.')}\n"
            f"👁 {st('Его увидят только модераторы.')}\n"
            f"{SEP}")
        return

    # ── Bypass ────────────────────────────────────────────────────────────────
    if data == "bypass":
        if maintenance_active() and not is_admin(uid):
            bot.answer_callback_query(call.id, "🔧 Тех. перерыв!", show_alert=True)
            return
        user_state[chat_id] = "awaiting_bypass_link"
        bot.send_message(chat_id,
            f"⚡ {st('Bypass')}\n"
            f"{SEP}\n"
            f"🔗 {st('Вставь ссылку для обхода:')}")
        return

    # ── Панель (кнопка /start) ────────────────────────────────────────────────
    if data == "admin_panel":
        if not is_admin(uid):
            bot.answer_callback_query(call.id, "🚫 Нет прав!", show_alert=True)
            return
        show_admin_panel(chat_id)
        return

    # ── Всё остальное — только для админов ───────────────────────────────────
    if not is_admin(uid):
        bot.answer_callback_query(call.id, "🚫 Нет прав!")
        return

    # ── Статистика ────────────────────────────────────────────────────────────
    if data == "stats":
        show_stats(chat_id)
        return

    # ── Тех. перерыв ──────────────────────────────────────────────────────────
    if data == "maint_on":
        user_state[chat_id] = "maint_time"
        bot.send_message(chat_id,
            f"🔧 {st('Тех. перерыв')}\n"
            f"{SEP}\n"
            f"⏱ {st('Введи время в минутах')}\n"
            f"💡 {st('(0 = без ограничения):')}")
        return

    if data == "maint_off":
        MAINTENANCE.update(active=False, reason="", until=0)
        bot.answer_callback_query(call.id, "✅ Тех. перерыв снят!")
        show_admin_panel(chat_id)
        return

    if data == "close_panel":
        try:
            bot.delete_message(chat_id, call.message.message_id)
        except:
            pass
        return

    # ── Скрипты ───────────────────────────────────────────────────────────────
    if data == "add_script":
        user_state[chat_id] = "add_script"
        bot.send_message(chat_id,
            f"➕ {st('Добавить скрипт')}\n"
            f"{SEP}\n"
            f"📝 {st('Введи ключ и скрипт через запятую:')}\n"
            f"`ключ, loadstring(...)`",
            parse_mode="Markdown")

    elif data == "delete_script":
        user_state[chat_id] = "delete_script"
        bot.send_message(chat_id,
            f"🗑 {st('Удалить скрипт')}\n"
            f"{SEP}\n"
            f"🔑 {st('Введи ключ скрипта:')}")

    elif data == "list_scripts":
        if not SCRIPTS:
            bot.send_message(chat_id,
                f"📋 {st('Список скриптов')}\n"
                f"{SEP}\n"
                f"🗂 {st('Скриптов пока нет.')}")
        else:
            items = "\n".join(
                f"  🔹 `{k}` — {st('выдан')} {SCRIPT_STATS.get(k, 0)} {st('раз')}"
                for k in SCRIPTS
            )
            bot.send_message(chat_id,
                f"📋 {st('Список скриптов')}\n"
                f"{SEP}\n{items}\n{SEP}\n"
                f"🗂 {st('Всего')}: {len(SCRIPTS)}",
                parse_mode="Markdown")

    elif data == "get_link":
        user_state[chat_id] = "get_link"
        bot.send_message(chat_id,
            f"📤 {st('Получить ссылку')}\n"
            f"{SEP}\n"
            f"🔑 {st('Введи ключ скрипта:')}")

    # ── Управление админами ───────────────────────────────────────────────────
    elif data == "manage_admins":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("➕ Добавить", callback_data="add_admin"),
            InlineKeyboardButton("➖ Удалить",  callback_data="remove_admin"),
            InlineKeyboardButton("📋 Список",   callback_data="list_admins"),
            InlineKeyboardButton("🔙 Назад",    callback_data="back_to_admin"),
        )
        bot.send_message(chat_id,
            f"👥 {st('Управление админами')}\n"
            f"{SEP}\n"
            f"👑 {st('Сейчас админов')}: {len(ADMINS)}",
            reply_markup=markup)

    elif data == "add_admin":
        user_state[chat_id] = "add_admin"
        bot.send_message(chat_id,
            f"➕ {st('Добавить админа')}\n"
            f"{SEP}\n"
            f"🆔 {st('Введи Telegram ID пользователя:')}")

    elif data == "remove_admin":
        user_state[chat_id] = "remove_admin"
        bot.send_message(chat_id,
            f"➖ {st('Удалить админа')}\n"
            f"{SEP}\n"
            f"🆔 {st('Введи ID для удаления:')}")

    elif data == "list_admins":
        items = "\n".join(f"  👑 `{a}`" for a in ADMINS)
        bot.send_message(chat_id,
            f"👥 {st('Список админов')}\n"
            f"{SEP}\n{items}\n{SEP}\n"
            f"📊 {st('Всего')}: {len(ADMINS)}",
            parse_mode="Markdown")

    # ── Управление модераторами ───────────────────────────────────────────────
    elif data == "manage_mods":
        markup = InlineKeyboardMarkup(row_width=2)
        markup.add(
            InlineKeyboardButton("➕ Добавить", callback_data="add_mod"),
            InlineKeyboardButton("➖ Удалить",  callback_data="remove_mod"),
            InlineKeyboardButton("📋 Список",   callback_data="list_mods"),
            InlineKeyboardButton("🔙 Назад",    callback_data="back_to_admin"),
        )
        bot.send_message(chat_id,
            f"🛡 {st('Управление модераторами')}\n"
            f"{SEP}\n"
            f"🛡 {st('Сейчас модераторов')}: {len(MODERATORS)}",
            reply_markup=markup)

    elif data == "add_mod":
        user_state[chat_id] = "add_mod"
        bot.send_message(chat_id,
            f"➕ {st('Добавить модератора')}\n"
            f"{SEP}\n"
            f"🆔 {st('Введи Telegram ID пользователя:')}")

    elif data == "remove_mod":
        user_state[chat_id] = "remove_mod"
        bot.send_message(chat_id,
            f"➖ {st('Удалить модератора')}\n"
            f"{SEP}\n"
            f"🆔 {st('Введи ID для удаления:')}")

    elif data == "list_mods":
        if not MODERATORS:
            bot.send_message(chat_id,
                f"🛡 {st('Список модераторов')}\n"
                f"{SEP}\n"
                f"👀 {st('Модераторов пока нет.')}")
        else:
            items = "\n".join(f"  🛡 `{m}`" for m in MODERATORS)
            bot.send_message(chat_id,
                f"🛡 {st('Список модераторов')}\n"
                f"{SEP}\n{items}\n{SEP}\n"
                f"📊 {st('Всего')}: {len(MODERATORS)}",
                parse_mode="Markdown")

    elif data == "back_to_admin":
        show_admin_panel(chat_id)

# ── Текстовые сообщения ───────────────────────────────────────────────────────
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    chat_id = message.chat.id
    uid     = message.from_user.id
    state   = user_state.get(chat_id)

    register_user(message.from_user)

    if maintenance_active() and not is_admin(uid) and state != "awaiting_bypass_link":
        bot.send_message(chat_id, maintenance_text())
        return

    # ── Тех. перерыв: ввод времени ───────────────────────────────────────────
    if state == "maint_time":
        try:
            mins = int(message.text.strip())
            if mins < 0:
                raise ValueError
        except ValueError:
            bot.send_message(chat_id,
                f"❌ {st('Ошибка!')}\n"
                f"{SEP}\n"
                f"🔢 {st('Введи целое число минут (0 или больше).')}")
            return
        user_state[chat_id] = {"state": "maint_reason", "mins": mins}
        bot.send_message(chat_id,
            f"📝 {st('Тех. перерыв')}\n"
            f"{SEP}\n"
            f"💬 {st('Введи причину перерыва:')}")
        return

    if isinstance(state, dict) and state.get("state") == "maint_reason":
        reason = message.text.strip()
        mins   = state["mins"]
        MAINTENANCE["active"] = True
        MAINTENANCE["reason"] = reason
        MAINTENANCE["until"]  = int(time.time()) + mins * 60 if mins > 0 else 0
        user_state[chat_id] = None
        dur = f"{mins} мин." if mins > 0 else "без ограничения"
        bot.send_message(chat_id,
            f"🔧 {st('Тех. перерыв включён!')}\n"
            f"{SEP}\n"
            f"⏱ {st('Время')}: {dur}\n"
            f"📌 {st('Причина')}: {reason}\n"
            f"{SEP}\n"
            f"✅ {st('Готово!')}")
        show_admin_panel(chat_id)
        return

    # ── Предложка ─────────────────────────────────────────────────────────────
    if state == "predloshka":
        if is_muted(uid):
            bot.send_message(chat_id,
                f"🔇 {st('Ты замучен!')}\n"
                f"{SEP}\n"
                f"😶 {st('Ты не можешь отправлять предложения.')}")
            user_state[chat_id] = None
            return

        text      = message.text.strip()
        sug_id    = next_sug_id()
        user_info = message.from_user
        name      = (user_info.first_name or "") + (" " + user_info.last_name if user_info.last_name else "")
        uname     = f"@{user_info.username}" if user_info.username else f"id:{uid}"

        deliveries = []
        for mod_id in list(set(ADMINS + MODERATORS)):
            try:
                sent = bot.send_message(
                    mod_id,
                    f"📬 {st('Новое предложение!')}\n"
                    f"{SEP}\n"
                    f"👤 {st('От')}: {name} ({uname})\n"
                    f"🆔 {st('ID')}: `{uid}`\n"
                    f"{SEP}\n"
                    f"💬 {text}\n"
                    f"{SEP}",
                    reply_markup=moderator_buttons(sug_id, uid),
                    parse_mode="Markdown"
                )
                deliveries.append([mod_id, sent.message_id])
            except:
                pass

        SUGGESTIONS[sug_id] = {"user_id": uid, "text": text, "deliveries": deliveries}
        save_suggestions()

        bot.send_message(chat_id,
            f"✅ {st('Предложение отправлено!')}\n"
            f"{SEP}\n"
            f"👁 {st('Модераторы скоро его рассмотрят.')}\n"
            f"🙏 {st('Спасибо за участие!')}")
        user_state[chat_id] = None
        return

    # ── Bypass ────────────────────────────────────────────────────────────────
    if state == "awaiting_bypass_link":
        if maintenance_active() and not is_admin(uid):
            bot.send_message(chat_id, maintenance_text())
            user_state[chat_id] = None
            return
        link = message.text.strip()
        if not link.startswith("http"):
            bot.send_message(chat_id,
                f"❌ {st('Это не ссылка!')}\n"
                f"{SEP}\n"
                f"🔗 {st('Вставь корректную http-ссылку.')}")
            return
        send_photo(chat_id, "loading",
                   caption=f"⚡ {st('Bypass запущен...')}\n{SEP}\n⏳ {st('Обрабатываю ссылку...')}")
        key = bypass_link(link)
        if key:
            send_photo(chat_id, "bypass_success",
                       caption=(
                           f"🎉 {st('Байпасс успешен!')}\n"
                           f"{SEP}\n"
                           f"🔑 {st('Ключ')}:\n"
                           f"`{key}`\n"
                           f"{SEP}"
                       ),
                       parse_mode="Markdown")
        else:
            bot.send_message(chat_id,
                f"😔 {st('Не удалось обойти ссылку.')}\n"
                f"{SEP}\n"
                f"🔄 {st('Попробуй другую ссылку.')}")
        user_state[chat_id] = None
        return

    # ── Скрипты ───────────────────────────────────────────────────────────────
    elif state == "add_script":
        try:
            key, script = message.text.split(",", 1)
            key = key.strip()
            if not key:
                raise ValueError("empty key")
            SCRIPTS[key] = script.strip()
            save_scripts()
            bot.send_message(chat_id,
                f"✅ {st('Скрипт добавлен!')}\n"
                f"{SEP}\n"
                f"🔑 {st('Ключ')}: `{key}`",
                parse_mode="Markdown")
        except:
            bot.send_message(chat_id,
                f"❌ {st('Ошибка!')}\n"
                f"{SEP}\n"
                f"📝 {st('Формат')}: `ключ, loadstring(...)`",
                parse_mode="Markdown")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

    elif state == "delete_script":
        key = message.text.strip()
        if key in SCRIPTS:
            del SCRIPTS[key]
            SCRIPT_STATS.pop(key, None)
            save_scripts()
            save_script_stats()
            bot.send_message(chat_id,
                f"🗑 {st('Скрипт удалён!')}\n"
                f"{SEP}\n"
                f"🔑 {st('Ключ')}: `{key}`",
                parse_mode="Markdown")
        else:
            bot.send_message(chat_id,
                f"❌ {st('Скрипт не найден!')}\n"
                f"{SEP}\n"
                f"🔎 {st('Проверь правильность ключа.')}")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

    elif state == "get_link":
        key = message.text.strip()
        if key in SCRIPTS:
            me   = bot.get_me()
            link = f"https://t.me/{me.username}?start={key}"
            bot.send_message(chat_id,
                f"📤 {st('Ссылка на скрипт')}\n"
                f"{SEP}\n"
                f"🔑 {st('Ключ')}: `{key}`\n"
                f"🔗 {link}\n"
                f"{SEP}",
                parse_mode="Markdown")
        else:
            bot.send_message(chat_id,
                f"❌ {st('Скрипт не найден!')}\n"
                f"{SEP}\n"
                f"🔎 {st('Проверь правильность ключа.')}")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

    # ── Управление админами ───────────────────────────────────────────────────
    elif state == "add_admin":
        try:
            new_uid = int(message.text.strip())
            if new_uid in ADMINS:
                bot.send_message(chat_id, f"⚠️ {st('Этот пользователь уже админ!')}")
            else:
                ADMINS.append(new_uid)
                save_admins()
                bot.send_message(chat_id,
                    f"✅ {st('Администратор добавлен!')}\n"
                    f"{SEP}\n"
                    f"👑 {st('ID')}: `{new_uid}`",
                    parse_mode="Markdown")
        except:
            bot.send_message(chat_id, f"❌ {st('Ошибка!')} {st('Введи корректный ID.')}")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

    elif state == "remove_admin":
        try:
            rem_uid = int(message.text.strip())
            if rem_uid == ADMIN_ID:
                bot.send_message(chat_id, f"🚫 {st('Нельзя удалить главного администратора!')}")
            elif rem_uid in ADMINS:
                ADMINS.remove(rem_uid)
                save_admins()
                bot.send_message(chat_id,
                    f"🗑 {st('Администратор удалён!')}\n"
                    f"{SEP}\n"
                    f"🆔 {st('ID')}: `{rem_uid}`",
                    parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"❌ {st('Администратор не найден. Проверь ID.')}")
        except:
            bot.send_message(chat_id, f"❌ {st('Ошибка!')} {st('Введи корректный ID.')}")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

    # ── Управление модераторами ───────────────────────────────────────────────
    elif state == "add_mod":
        try:
            new_uid = int(message.text.strip())
            if new_uid in MODERATORS:
                bot.send_message(chat_id, f"⚠️ {st('Этот пользователь уже модератор!')}")
            else:
                MODERATORS.append(new_uid)
                save_moderators()
                bot.send_message(chat_id,
                    f"✅ {st('Модератор добавлен!')}\n"
                    f"{SEP}\n"
                    f"🛡 {st('ID')}: `{new_uid}`",
                    parse_mode="Markdown")
        except:
            bot.send_message(chat_id, f"❌ {st('Ошибка!')} {st('Введи корректный ID.')}")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

    elif state == "remove_mod":
        try:
            rem_uid = int(message.text.strip())
            if rem_uid in MODERATORS:
                MODERATORS.remove(rem_uid)
                save_moderators()
                bot.send_message(chat_id,
                    f"🗑 {st('Модератор удалён!')}\n"
                    f"{SEP}\n"
                    f"🆔 {st('ID')}: `{rem_uid}`",
                    parse_mode="Markdown")
            else:
                bot.send_message(chat_id, f"❌ {st('Модератор не найден. Проверь ID.')}")
        except:
            bot.send_message(chat_id, f"❌ {st('Ошибка!')} {st('Введи корректный ID.')}")
        user_state[chat_id] = None
        show_admin_panel(chat_id)

# ── Keep-alive HTTP сервер (для 24/7) ────────────────────────────────────────
class _PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, *_):  # заглушить логи
        pass

def _run_http():
    port = int(os.environ.get("PORT", 8080))
    try:
        HTTPServer(("0.0.0.0", port), _PingHandler).serve_forever()
    except OSError:
        pass   # порт занят — не критично

threading.Thread(target=_run_http, daemon=True).start()

# ── Запуск polling с авто-перезапуском ───────────────────────────────────────
print("✅ Бот запущен!")
bot.remove_webhook()
while True:
    try:
        bot.polling(non_stop=True, interval=3, timeout=30)
    except Exception as e:
        print(f"[polling error] {e} — перезапуск через 5с")
        time.sleep(5)
