from bale import Bot, Message
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os
import re   # <-- was missing

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
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)

def get_config():
    return load_json(CONFIG_FILE, {"disabled": False, "schedule": None})

def save_config(cfg):
    save_json(CONFIG_FILE, cfg)

def get_broadcast_chats():
    return load_json(BROADCAST_FILE, [])

def save_broadcast_chats(chats):
    save_json(BROADCAST_FILE, chats)
def deleteAll():
    if os.path.exists(BROADCAST_FILE):
        os.remove(BROADCAST_FILE)
        send_message("Removed All.✅")
# ------------------------- Chat name helper -------------------------
def get_chat_name(chat_id):
    """Fetch chat title from Bale API (requires bot admin)."""
    # If it's a username string starting with '@', return it as is
    if isinstance(chat_id, str) and chat_id.startswith('@'):
        return chat_id

    try:
        resp = requests.get(f"{BASE_URL}/getChat?chat_id={chat_id}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                chat = data["result"]
                return chat.get("title", str(chat_id))
            else:
                return data.get("description", "Unknown error")
    except Exception as e:
        return f"Error: {e}"
    return str(chat_id)

# ------------------------- Price scraping (robust) -------------------------
def get_gold_prices():
    """
    Scrape gold and coin prices from tala.ir.
    Returns a dictionary with item names as keys and prices as values.
    """
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get('https://www.tala.ir/', headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # ---------- METHOD 1: Direct enumeration (most reliable) ----------
        # Order of items as they appear on tala.ir (verified)
        currency_names = [
            'انس طلا', 'مظنه', 'طلای ۱۸ عیار', 'سکه جدید', 'نیم سکه',
            'ربع سکه', 'سکه گرمی', 'شمش طلا', 'بیت‌کوین', 'سکه طلا',
            'نفت', 'تتر', 'پارسیان'
        ]

        # Find all price spans with class 'price greeen' (exact typo)
        price_spans = soup.find_all('span', class_='price greeen')

        prices = {}
        for idx, name in enumerate(currency_names):
            if idx < len(price_spans):
                price_text = price_spans[idx].get_text(strip=True)
                # Clean price: keep digits and commas
                price_clean = re.sub(r'[^\d,]', '', price_text)
                if price_clean:
                    prices[name] = price_clean
                else:
                    prices[name] = '-'
            else:
                prices[name] = '-'

        # If we got at least one real price, return the result
        if any(v not in ['-', ''] for v in prices.values()):
            return prices

        # ---------- METHOD 2: Fallback using 'mprice' divs ----------
        mprice_divs = soup.find_all('div', class_='mprice')
        if mprice_divs:
            fallback_prices = {}
            for idx, div in enumerate(mprice_divs):
                if idx < len(currency_names):
                    span = div.find('span', class_='price greeen')
                    if span:
                        price_text = span.get_text(strip=True)
                        price_clean = re.sub(r'[^\d,]', '', price_text)
                        fallback_prices[currency_names[idx]] = price_clean if price_clean else '-'
                    else:
                        fallback_prices[currency_names[idx]] = '-'
            if any(v not in ['-', ''] for v in fallback_prices.values()):
                return fallback_prices

        # ---------- METHOD 3: Last resort - ID mapping ----------
        news_divs = soup.find_all('div', class_=re.compile(r'newsprice|pricebox'))
        id_map = {
            'ounce': 'انس طلا', 'mazaneh': 'مظنه', '18k': 'طلای ۱۸ عیار',
            'sekke-jad': 'سکه جدید', 'sekke-nim': 'نیم سکه', 'sekke-rob': 'ربع سکه',
            'sekke-garmi': 'سکه گرمی', 'shemsh': 'شمش طلا', 'btc': 'بیت‌کوین',
            'sekke-gold': 'سکه طلا', 'oil': 'نفت', 'usdt': 'تتر', 'parsian': 'پارسیان'
        }
        final_prices = {}
        for div in news_divs:
            item_id = div.get('id')
            if item_id and item_id in id_map:
                span = div.find('span', class_=re.compile(r'green|price', re.I))
                if span:
                    price_text = span.get_text(strip=True)
                    price_clean = re.sub(r'[^\d,]', '', price_text)
                    if price_clean:
                        final_prices[id_map[item_id]] = price_clean
        if final_prices:
            # Fill missing items with '-'
            for name in currency_names:
                if name not in final_prices:
                    final_prices[name] = '-'
            return final_prices

        # Nothing worked
        print("Warning: No prices extracted from tala.ir")
        return {'error': 'Unable to fetch prices. Website structure may have changed.'}

    except requests.exceptions.Timeout:
        return {'error': 'Connection timeout. Please try again later.'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Cannot reach tala.ir. Check your internet connection.'}
    except Exception as e:
        print(f"Error fetching gold prices: {e}")
        return {'error': f'Scraping error: {str(e)[:50]}...'}

def format_prices_message(prices):
    if not prices:
        return "⚠️ خطا در دریافت قیمت از tala.ir\nلطفاً چند دقیقه دیگر تلاش کنید."

    if 'error' in prices:
        return f"⚠️ {prices['error']}"

    lines = ["🏆 قیمت طلا و سکه – tala.ir\n"]

    for label, value in prices.items():
        if value and value != '-':
            lines.append(f"🔸 {label}: {value} 🪙")
        else:
            lines.append(f"🔸 {label}: در حال دریافت... 🪙")

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
        await asyncio.sleep(60)

# ------------------------- Bale event handlers -------------------------
@bot.event
async def on_ready():
    print(f"Bot ready – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.create_task(scheduled_broadcast())

@bot.event
async def on_message(message: Message):
    # Only respond in private chat
    if getattr(message.chat, 'type', '') != 'private':
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
                buttons.append(["✅ Enable bot"])
            else:
                buttons.append(["❌ Disable bot"])
            buttons.append(["📖 Guide", "⏰ Set Time"])
            buttons.append(["📊 Status", "📢 Broadcast Now"])
            buttons.append(["💢 Delete All Channels", "📢 Delete All"])
            buttons.append(["➕ Add Channel", "➖ Remove Channel"])
            buttons.append(["📋 List Channels", "🔍 Test Channel"])
            buttons.append(["⛔ Limit Channels/Channel"])   # <-- new tab
            markup = build_reply_markup(buttons)
            msg = "🤖 Gold Price Bot – control panel.\n" + ("🔴 DISABLED" if disabled else "🟢 ACTIVE")
            send_message(chat_id, msg, markup)

        # ---------- Guide ----------
        elif text in ["/guide", "📖 Guide"]:
            help_text = (
                "📘 *راهنما* 📘\n\n"
                "/start – منوی اصلی\n"
                "/enable – فعال کردن ارسال خودکار\n"
                "/disable – غیرفعال کردن\n"
                "/set_time HH:MM – تنظیم ساعت ارسال روزانه\n"
                "/clear_time – حذف زمانبندی\n"
                "/mytime – نمایش زمان فعلی\n"
                "/clearallch - پاک کردن تمام کانال ها \n"
                "/status – وضعیت بات + لیست کانال‌ها\n"
                "/add_channel @username – اضافه کردن کانال\n"
                "/remove_channel @username – حذف کانال\n"
                "/list_channels – لیست کانال‌ها\n"
                "/test_channel @username – تست دسترسی\n"
                "/broadcast_now – ارسال فوری قیمت‌ها"
            )
            send_message(chat_id, help_text)

        # ---------- Enable / Disable ----------
        elif text in ["/disable", "❌ Disable bot"]:
            cfg['disabled'] = True
            save_config(cfg)
            send_message(chat_id, "🔴 Bot disabled. No messages will be sent.")
            # Re-show menu
            await on_message(message)  # recursive call to refresh menu (safe here)

        elif text in ["/enable", "✅ Enable bot"]:
            cfg['disabled'] = False
            save_config(cfg)
            send_message(chat_id, "🟢 Bot enabled. Scheduled messages will be sent.")
            await on_message(message)

        # ---------- Set Time ----------
        elif text.startswith("/set_time ") or text == "⏰ Set Time":
            if text == "⏰ Set Time":
                send_message(chat_id, "⏰ Send time as HH:MM (e.g., 09:15)")
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
                send_message(chat_id, "❌ Invalid format. Use HH:MM (24h)")
                return
            cfg['schedule'] = {'hour': hour, 'minute': minute}
            save_config(cfg)
            send_message(chat_id, f"⏰ Daily broadcast set to {hour:02d}:{minute:02d} (server time)")

        # ---------- Clear Time ----------
        elif text == "/clear_time":
            if cfg.get('schedule'):
                cfg['schedule'] = None
                save_config(cfg)
                send_message(chat_id, "Schedule cleared.")
            else:
                send_message(chat_id, "No schedule was set.")

        # ---------- My Time ----------
        elif text == "/mytime":
            sched = cfg.get('schedule')
            if sched:
                send_message(chat_id, f"Current schedule: {sched['hour']:02d}:{sched['minute']:02d}")
            else:
                send_message(chat_id, "No schedule set.")

        # ---------- Status ----------
        elif text == "/status" or text == "📊 Status":
            sched = cfg.get('schedule')
            schedule_str = f"{sched['hour']:02d}:{sched['minute']:02d}" if sched else "Not set"
            status_str = "DISABLED" if cfg.get('disabled') else "ENABLED"
            channels = get_broadcast_chats()
            lines = [
                f"📊 *Bot Status*",
                f"▶️ Status: {status_str}",
                f"⏰ Schedule: {schedule_str}",
                f"📢 Channels: {len(channels)}"
            ]
            if channels:
                named = []
                for cid in channels:
                    name = get_chat_name(cid)
                    named.append(f"• {name} ({cid})")
                lines.append("📋 Channel list:\n" + "\n".join(named))
            send_message(chat_id, '\n'.join(lines))

        elif text.startswith("/add_channel ") or text == "➕ Add Channel":
            if text == "➕ Add Channel":
                send_message(chat_id, "Send channel username like:\n/add_channel @my_channel")
                return

            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /add_channel @channelusername")
                return

            channel_identifier = parts[1].strip()

            if not channel_identifier.startswith('@'):
                send_message(chat_id, "❌ Username must start with @ (e.g., @my_channel)")
                return

            # Use the HTTP API directly for validation - more reliable
            try:
                resp = requests.get(f"{BASE_URL}/getChat?chat_id={channel_identifier}", timeout=10)
                data = resp.json()
                if not data.get("ok"):
                    error_desc = data.get("description", "Unknown error")
                    send_message(chat_id, f"❌ Cannot access channel.\nError: {error_desc}\n\nMake sure:\n1. Bot is admin\n2. Username is correct")
                    return
                
            except Exception as e:
                send_message(chat_id, f"❌ API error: {e}")
                return
            chat_info = data["result"]
            channel_title = chat_info.get("title", channel_identifier)
            chats = get_broadcast_chats()
            already_exists = any(
                c.lower() == channel_identifier.lower() if isinstance(c, str) else c == channel_identifier
                for c in chats
            )

            if already_exists:
                send_message(chat_id, "❌ This channel is already in the broadcast list.")
                return

            chats.append(channel_identifier)
            save_broadcast_chats(chats)
            send_message(chat_id, f"✅ Channel {channel_title} added. Total: {len(chats)}")
        #-----------Remove All Channels--------
        elif text.startswith("/clearallch") or text == "➖ Remove All Channels":
            try:
                channels = get_broadcast_chats()
                if not channels:
                    send_message("There is not channel to delete.")
                else:
                    save_broadcast_chats([]) 
                    send_message(chat_id,f"Removed {len(channels)} Channels")
            except Exception as e:
                pass
        # ---------- Remove channel ----------
        elif text.startswith("/remove_channel ") or text == "➖ Remove Channel":
            if text == "➖ Remove Channel":
                send_message(chat_id, "Send channel username like:\n/remove_channel @my_channel")
                return
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
                send_message(chat_id, f"❌ Channel {name} removed.")
            else:
                send_message(chat_id, "Channel not found in the list.")

        # ---------- List channels ----------
        elif text == "/list_channels" or text == "📋 List Channels":
            chats = get_broadcast_chats()
            if chats:
                lines = ["📋 Registered channels:"]
                for cid in chats:
                    display_name = cid if (isinstance(cid, str) and cid.startswith('@')) else get_chat_name(cid)
                    lines.append(f"• {display_name}")
                send_message(chat_id, '\n'.join(lines))
            else:
                send_message(chat_id, "No channels registered. Use /add_channel @username")

        # ---------- Test channel ----------
        elif text.startswith("/test_channel ") or text == "🔍 Test Channel":
            if text == "🔍 Test Channel":
                send_message(chat_id, "Send channel username to test:\n/test_channel @my_channel")
                return
            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /test_channel @channelusername")
                return
            test_id = parts[1]
            try:
                resp = requests.get(f"{BASE_URL}/getChat?chat_id={test_id}", timeout=5)
                data = resp.json()
                if data.get("ok"):
                    chat_info = data["result"]
                    title = chat_info.get("title", "No title")
                    send_message(chat_id, f"✅ Bot can access:\nTitle: {title}\nID: {test_id}")
                else:
                    error_desc = data.get("description", "Unknown")
                    send_message(chat_id, f"❌ Cannot access.\nError: {error_desc}\n\nPossible reasons:\n- Bot not admin\n- Wrong username/ID\n- Channel does not exist")
            except Exception as e:
                send_message(chat_id, f"⚠️ API error: {e}")

        # ---------- Broadcast now ----------
        elif text == "/broadcast_now" or text == "📢 Broadcast Now":
            send_message(chat_id, "🔄 Fetching prices and broadcasting...")
            prices = get_gold_prices()
            msg = format_prices_message(prices)
            channels = get_broadcast_chats()
            if not channels:
                send_message(chat_id, "⚠️ No channels registered. Use /add_channel")
            else:
                success = 0
                for cid in channels:
                    try:
                        send_message(cid, msg)
                        success += 1
                    except Exception as e:
                        print(f"Failed to send to {cid}: {e}")
                send_message(chat_id, f"✅ Sent to {success} of {len(channels)} channels")

        # ---------- Limit Channels/Channel (placeholder) ----------
        elif text == "⛔ Limit Channels/Channel":
            send_message(chat_id, "🔜 این قابلیت به زودی اضافه می‌شود (Done soon)")

        else:
            # Unknown command – ignore
            pass

    except Exception as e:
        print(f"Handler error: {e}")
        send_message(chat_id, "❗ Internal error. Please try again.")

# ------------------------- Run bot -------------------------
if __name__ == "__main__":
    asyncio.run(bot.run())