from bale import Bot, Message
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os

TOKEN = "181225967:7lVqaxpiGrFXQonLy7BytgNQRynjgejn3A4"
bot = Bot(token=TOKEN)

CONFIG_FILE = "config.json"
BROADCAST_FILE = "broadcast_chats.json"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

# ------------------------- JSON helpers -------------------------
def load_json(path, default):
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:   # <-- fixed: overwrite
        json.dump(data, f, indent=2)

def get_config():
    return load_json(CONFIG_FILE, {"disabled": False, "schedule": None})

def save_config(cfg):
    save_json(CONFIG_FILE, cfg)

def get_broadcast_chats():
    return load_json(BROADCAST_FILE, [])

def save_broadcast_chats(chats):
    save_json(BROADCAST_FILE, chats)

# ------------------------- Chat name helper -------------------------
def get_chat_name(chat_id):
    """Fetch chat title from Bale API (requires bot admin)."""
    try:
        resp = requests.get(f"{BASE_URL}/getChat?chat_id={chat_id}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                chat = data["result"]
                return chat.get("title", str(chat_id))
    except Exception:
        pass
    # If it's a username, return it as is
    if isinstance(chat_id, str) and chat_id.startswith('@'):
        return chat_id
    return str(chat_id)
# ------------------------- Price scraping (no select_one) -------------------------
def get_gold_prices():
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get('https://www.tala.ir/', headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. Find all divs with class "mprice"
        price_divs = soup.find_all('div', class_='mprice')
        prices = []
        for div in price_divs:
            span = div.find('span', class_='price greeen')   # exact typo "greeen"
            if span:
                # manual text extraction
                price_text = ''.join(span.strings).strip()
                prices.append(price_text)
            else:
                prices.append(None)

        # 2. Find all name links (a[href^='/price/'] containing a p)
        name_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('/price/') and a.find('p'):
                p = a.find('p')
                name = ''.join(p.strings).strip()
                name_links.append((name, href))

        # 3. Pair by index (assumed same order)
        result = {}
        for idx, (name, href) in enumerate(name_links):
            if idx < len(prices) and prices[idx]:
                # Use the URL path as key (e.g., 'sekke-rob')
                key = href.replace('/price/', '')
                result[key] = prices[idx]

        # Fallback if the above fails: try original method with id extraction
        if not result:
            for div in price_divs:
                parent = div.find_parent('div', class_='newsprice')
                if parent and parent.get('id'):
                    label = parent['id']
                    span = div.find('span', class_='price greeen')
                    if span:
                        result[label] = ''.join(span.strings).strip()
        return result

    except Exception as e:
        print(f"Error fetching gold prices: {e}")
        return {}

def format_prices_message(prices):
    if not prices:
        # return "⚠️ خطا در دریافت قیمت از tala.ir"
        return None
    lines = ["🏆 قیمت طلا و سکه – tala.ir\n"]
    for label, value in prices.items():
        lines.append(f"🔸 {label}: {value} 🪙")
    lines.append(f"\n📅 {datetime.now().strftime('%Y/%m/%d %H:%M')}")
    return '\n'.join(lines)

# ------------------------- Keyboard helper -------------------------
def build_reply_markup(buttons):
    return {
        "keyboard": [[{"text": btn} for btn in row] for row in buttons],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

# ------------------------- Send message via API -------------------------
def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"API send error: {e}")

# ------------------------- Broadcast task -------------------------
async def scheduled_broadcast():
    last_sent = {}
    while True:
        now = datetime.now()
        current_key = now.strftime('%Y%m%d%H%M')
        cfg = get_config()
        if cfg['disabled']:
            await asyncio.sleep(30)
            continue
        sched = cfg.get('schedule')
        if not sched or sched['hour'] != now.hour or sched['minute'] != now.minute:
            await asyncio.sleep(30)
            continue
        if last_sent.get('key') == current_key:
            await asyncio.sleep(30)
            continue

        prices = get_gold_prices()
        msg = format_prices_message(prices)
        for chat_id in get_broadcast_chats():
            try:
                send_message(chat_id, msg)
            except Exception as e:
                print(f"Failed to send to {chat_id}: {e}")
        last_sent['key'] = current_key
        await asyncio.sleep(60)  # wait a minute after sending

# ------------------------- Bale event handlers -------------------------
@bot.event
async def on_ready():
    print(f"Bot ready – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.create_task(scheduled_broadcast())

@bot.event
async def on_message(message: Message):
    # Only respond in private chat with the bot
    if getattr(message.chat, 'type', '') != 'private':
        # Optional: print channel messages for debugging
        # print(f"Channel msg from {message.chat.id}: {message.text}")
        return

    text = message.text.strip() if message.text else ""
    chat_id = message.chat.id
    cfg = get_config()
    disabled = cfg.get('disabled', False)

    if disabled and text not in ["/start", "/enable", "Enable bot"]:
        send_message(chat_id, "🔴 Bot is disabled. Use Enable bot from menu.")
        return

    try:
        # ---------- /start or /menu ----------
        if text in ["/start", "/menu"]:
            buttons = []
            if disabled:
                buttons.append(["Enable bot"])
            else:
                buttons.append(["Disable bot"])
            buttons.append(["Guide", "Set Time"])
            markup = build_reply_markup(buttons)
            msg = "🤖 Gold Price Bot – control panel.\n" + ("Bot is DISABLED." if disabled else "Bot is ACTIVE.")
            send_message(chat_id, msg, markup)

        # ---------- Guide ----------
        elif text in ["/guide", "Guide"]:
            help_text = (
                "📘 *راهنما* 📘\n\n"
                "/start – منوی اصلی\n"
                "/enable – فعال کردن ارسال خودکار\n"
                "/disable – غیرفعال کردن\n"
                "/set_time HH:MM – تنظیم ساعت ارسال روزانه\n"
                "/clear_time – حذف زمانبندی\n"
                "/mytime – نمایش زمان فعلی\n"
                "/status – وضعیت بات + لیست کانال‌ها\n"
                "/add_channel <chat_id> – اضافه کردن کانال\n"
                "/remove_channel <chat_id> – حذف کانال\n"
                "/list_channels – لیست کانال‌ها\n"
                "/test_channel <chat_id> – تست دسترسی بات به کانال\n"
                "/broadcast_now – ارسال فوری قیمت‌ها به همه کانال‌ها"
            )
            send_message(chat_id, help_text)

        # ---------- Enable / Disable ----------
        elif text in ["/disable", "Disable bot"]:
            cfg['disabled'] = True
            save_config(cfg)
            markup = build_reply_markup([["Enable bot"], ["Guide"], ["Set Time"]])
            send_message(chat_id, "🔴 بات غیرفعال شد. هیچ پیامی ارسال نمی‌شود.", markup)

        elif text in ["/enable", "Enable bot"]:
            cfg['disabled'] = False
            save_config(cfg)
            markup = build_reply_markup([["Disable bot"], ["Guide"], ["Set Time"]])
            send_message(chat_id, "🟢 بات فعال شد. طبق برنامه قیمت‌ها ارسال خواهد شد.", markup)

        # ---------- Set Time ----------
        elif text.startswith("/set_time ") or text == "Set Time":
            if text == "Set Time":
                send_message(chat_id, "⏰ ساعت را به فرمت HH:MM ارسال کنید (مثلاً 09:15)")
                return
            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /set_time HH:MM")
                return
            time_str = parts[1]
            try:
                hour, minute = map(int, time_str.split(':'))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except:
                send_message(chat_id, "❌ فرمت نامعتبر. از اعداد 00 تا 23 برای ساعت و 00 تا 59 برای دقیقه استفاده کنید.")
                return
            cfg['schedule'] = {'hour': hour, 'minute': minute}
            save_config(cfg)
            send_message(chat_id, f"⏰ زمان ارسال روزانه تنظیم شد: {hour:02d}:{minute:02d} (به وقت سرور)")

        # ---------- Clear Time ----------
        elif text == "/clear_time":
            if cfg.get('schedule'):
                cfg['schedule'] = None
                save_config(cfg)
                send_message(chat_id, "زمانبندی حذف شد.")
            else:
                send_message(chat_id, "هیچ زمانبندی تنظیم نشده بود.")

        # ---------- My Time ----------
        elif text == "/mytime":
            sched = cfg.get('schedule')
            if sched:
                send_message(chat_id, f"زمان ارسال فعلی: {sched['hour']:02d}:{sched['minute']:02d}")
            else:
                send_message(chat_id, "هیچ زمانبندی تنظیم نشده است.")

        # ---------- Status ----------
        elif text == "/status":
            sched = cfg.get('schedule')
            schedule_str = f"{sched['hour']:02d}:{sched['minute']:02d}" if sched else "تنظیم نشده"
            status_str = "غیرفعال" if cfg.get('disabled') else "فعال"
            channels = get_broadcast_chats()
            lines = [
                f"📊 *وضعیت بات*",
                f"▶️ وضعیت: {status_str}",
                f"⏰ زمان ارسال: {schedule_str}",
                f"📢 تعداد کانال‌ها: {len(channels)}"
            ]
            if channels:
                named = []
                for cid in channels:
                    name = get_chat_name(cid)
                    named.append(f"• {name} ({cid})")
                lines.append("📋 لیست کانال‌ها:\n" + "\n".join(named))
            send_message(chat_id, '\n'.join(lines))

        # ---------- Add channel ----------
        elif text.startswith("/add_channel "):
            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /add_channel @channelusername")
                return
            channel_identifier = parts[1].strip()
            
            # Validate username format (must start with @)
            if not channel_identifier.startswith('@'):
                send_message(chat_id, "❌ Channel username must start with @ (e.g., @my_channel)")
                return
            
            chats = get_broadcast_chats()
            if channel_identifier in chats:
                send_message(chat_id, "This channel is already in the list.")
            else:
                chats.append(channel_identifier)
                save_broadcast_chats(chats)
                name = get_chat_name(channel_identifier)
                send_message(chat_id, f"✅ Channel \"{name}\" added. Broadcast list now has {len(chats)} channels.")

        # ---------- Remove channel ----------
        elif text.startswith("/remove_channel "):
            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /remove_channel @channelusername")
                return
            channel_identifier = parts[1].strip()
        
            chats = get_broadcast_chats()
            if channel_identifier in chats:
                name = get_chat_name(channel_identifier)
                chats.remove(channel_identifier)
                save_broadcast_chats(chats)
                send_message(chat_id, f"❌ Channel \"{name}\" removed.")
            else:
                send_message(chat_id, "Channel not found in the list.")

        # ---------- List channels ----------
        elif text == "/list_channels":
            chats = get_broadcast_chats()
            if chats:
                lines = ["📋 Registered channels:"]
            for cid in chats:
                # Show username if it's a string, otherwise numeric ID
                display_name = cid if isinstance(cid, str) and cid.startswith('@') else get_chat_name(cid)
                lines.append(f"• {display_name}")
                send_message(chat_id, '\n'.join(lines))
            else:
                send_message(chat_id, "No channels registered. Use /add_channel @channelusername.")

        # ---------- Test channel (debug) ----------
        elif text.startswith("/test_channel "):
            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /test_channel <chat_id>")
                return
            test_id = parts[1]  # can be @username or numeric
            try:
                resp = requests.get(f"{BASE_URL}/getChat?chat_id={test_id}", timeout=5)
                data = resp.json()
                if data.get("ok"):
                    chat_info = data["result"]
                    title = chat_info.get("title", "بدون عنوان")
                    send_message(chat_id, f"✅ بات به کانال دسترسی دارد:\nعنوان: {title}\nشناسه: {test_id}")
                else:
                    error_desc = data.get("description", "ناشناخته")
                    send_message(chat_id, f"❌ دسترسی وجود ندارد.\nخطا: {error_desc}\n\nدلایل احتمالی:\n- بات ادمین نیست\n- chat_id اشتباه است (برای کانال خصوصی باید با -100 شروع شود)\n- کانال وجود ندارد")
            except Exception as e:
                send_message(chat_id, f"⚠️ خطا در ارتباط با API: {e}")

        # ---------- Broadcast now (force send) ----------
        elif text == "/broadcast_now":
            send_message(chat_id, "🔄 در حال ارسال قیمت‌ها به تمام کانال‌ها...")
            prices = get_gold_prices()
            msg = format_prices_message(prices)
            channels = get_broadcast_chats()
            if not channels:
                send_message(chat_id, "⚠️ هیچ کانالی ثبت نشده. از /add_channel استفاده کنید.")
            else:
                success = 0
                for cid in channels:
                    try:
                        send_message(cid, msg)
                        success += 1
                    except Exception as e:
                        print(f"Failed to send to {cid}: {e}")
                send_message(chat_id, f"✅ ارسال شد به {success} از {len(channels)} کانال")

        else:
            # Unknown command – ignore or show menu hint
            pass

    except Exception as e:
        print(f"Handler error: {e}")
        send_message(chat_id, "❗ خطای داخلی لطفاً دوباره تلاش کنید.")

# ------------------------- Run bot -------------------------
if __name__ == "__main__":
    asyncio.run(bot.run())