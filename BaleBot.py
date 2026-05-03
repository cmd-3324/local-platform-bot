from bale import Bot, Message
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json
import os
import re

TOKEN = "181225967:7lVqaxpiGrFXQonLy7BytgNQRynjgejn3A4"
bot = Bot(token=TOKEN)

CONFIG_FILE = "config.json"
BROADCAST_FILE = "broadcast_chats.json"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

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
    data = load_json(BROADCAST_FILE, {})
    if isinstance(data, list):
        new_data = {}
        for ch in data:
            new_data[ch] = {"enabled": True}
        save_broadcast_chats(new_data)  
        return new_data
    return data

def save_broadcast_chats(chats):
    # Ensure we always save a dict
    if not isinstance(chats, dict):
        chats = {}
    save_json(BROADCAST_FILE, chats)
def save_broadcast_chats(chats):
    save_json(BROADCAST_FILE, chats)

def delete_all_channels():
    if os.path.exists(BROADCAST_FILE):
        os.remove(BROADCAST_FILE)
        return True
    return False

def get_chat_name(chat_id):
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

def get_gold_prices():
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        response = requests.get('https://www.tala.ir/', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        currency_names = [
            'انس طلا', 'مظنه', 'طلای ۱۸ عیار', 'سکه جدید', 'نیم سکه',
            'ربع سکه', 'سکه گرمی', 'شمش طلا', 'بیت‌کوین', 'سکه طلا',
            'نفت', 'تتر', 'پارسیان'
        ]
        price_spans = soup.find_all('span', class_='price greeen')
        prices = {}
        for idx, name in enumerate(currency_names):
            if idx < len(price_spans):
                price_text = price_spans[idx].get_text(strip=True)
                price_clean = re.sub(r'[^\d,]', '', price_text)
                prices[name] = price_clean if price_clean else '-'
            else:
                prices[name] = '-'
        if any(v not in ['-', ''] for v in prices.values()):
            return prices
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
            return fallback_prices
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
            for name in currency_names:
                if name not in final_prices:
                    final_prices[name] = '-'
            return final_prices
        return {'error': 'Unable to fetch prices. Website structure may have changed.'}
    except requests.exceptions.Timeout:
        return {'error': 'Connection timeout. Please try again later.'}
    except requests.exceptions.ConnectionError:
        return {'error': 'Cannot reach tala.ir. Check your internet connection.'}
    except Exception as e:
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

def build_reply_markup(buttons):
    return {
        "keyboard": [[{"text": btn} for btn in row] for row in buttons],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

def send_message(chat_id, text, reply_markup=None):
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(f"{BASE_URL}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print(f"API send error: {e}")

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
        channels_dict = get_broadcast_chats()
        for cid, info in channels_dict.items():
            if not info.get("enabled", True):
                continue
            try:
                send_message(cid, msg)
            except Exception as e:
                print(f"Failed to send to {cid}: {e}")
        last_sent['key'] = current_key
        await asyncio.sleep(60)

user_states = {}

@bot.event
async def on_ready():
    print(f"Bot ready – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.create_task(scheduled_broadcast())

@bot.event
async def on_message(message: Message):
    if getattr(message.chat, 'type', '') != 'private':
        return

    text = message.text.strip() if message.text else ""
    chat_id = message.chat.id
    cfg = get_config()
    disabled = cfg.get('disabled', False)

    if disabled and text not in ["/start", "/enable", "✅ Enable bot"]:
        send_message(chat_id, "🔴 Bot is disabled. Use Enable bot from menu.")
        return

    try:
        if text in ["/start", "/menu"]:
            buttons = []
            if disabled:
                buttons.append(["✅ Enable bot"])
            else:
                buttons.append(["❌ Disable bot"])
            buttons.append(["📖 Guide", "⏰ Set Time"])
            buttons.append(["📊 Status", "📢 Broadcast Now"])
            buttons.append(["💢 Delete All Channels"])
            buttons.append(["➕ Add Channel", "➖ Remove Channel"])
            buttons.append(["📋 List Channels", "🔍 Test Channel"])
            buttons.append(["⛔ Limit/Unlimit Channel"])
            markup = build_reply_markup(buttons)
            msg = "🤖 Gold Price Bot – control panel.\n" + ("🔴 DISABLED" if disabled else "🟢 ACTIVE")
            send_message(chat_id, msg, markup)
            return

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
                "➡️ دستورات زیر بدون آرگومان استفاده می‌شوند:\n"
                "   /add_channel – اضافه کردن کانال\n"
                "   /remove_channel – حذف کانال\n"
                "   /toggle_channel – محدود/نامحدود کردن کانال\n"
                "   /test_channel – تست دسترسی\n"
                "/list_channels – لیست کانال‌ها\n"
                "/broadcast_now – ارسال فوری قیمت‌ها"
            )
            send_message(chat_id, help_text)
            return

        elif text in ["/disable", "❌ Disable bot"]:
            cfg['disabled'] = True
            save_config(cfg)
            buttons = [
                ["✅ Enable bot"],
                ["📖 Guide", "⏰ Set Time"],
                ["📊 Status", "📢 Broadcast Now"],
                ["💢 Delete All Channels"],
                ["➕ Add Channel", "➖ Remove Channel"],
                ["📋 List Channels", "🔍 Test Channel"],
                ["⛔ Limit Channel"]
            ]
            markup = build_reply_markup(buttons)
            send_message(chat_id, "🔴 Bot disabled. No messages will be sent.", markup)
            return

        elif text in ["/enable", "✅ Enable bot"]:
            cfg['disabled'] = False
            save_config(cfg)
            buttons = [
                ["❌ Disable bot"],
                ["📖 Guide", "⏰ Set Time"],
                ["📊 Status", "📢 Broadcast Now"],
                ["💢 Delete All Channels"],
                ["➕ Add Channel", "➖ Remove Channel"],
                ["📋 List Channels", "🔍 Test Channel"],
                ["⛔ Limit Channel"]
            ]
            markup = build_reply_markup(buttons)
            send_message(chat_id, "🟢 Bot enabled. Scheduled messages will be sent.", markup)
            return

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
            return

        elif text == "/clear_time":
            if cfg.get('schedule'):
                cfg['schedule'] = None
                save_config(cfg)
                send_message(chat_id, "Schedule cleared.")
            else:
                send_message(chat_id, "No schedule was set.")
            return

        elif text == "/mytime":
            sched = cfg.get('schedule')
            if sched:
                send_message(chat_id, f"Current schedule: {sched['hour']:02d}:{sched['minute']:02d}")
            else:
                send_message(chat_id, "No schedule set.")
            return

        elif text == "/status" or text == "📊 Status":
            sched = cfg.get('schedule')
            schedule_str = f"{sched['hour']:02d}:{sched['minute']:02d}" if sched else "Not set"
            status_str = "DISABLED" if cfg.get('disabled') else "ENABLED"
            channels_dict = get_broadcast_chats()
            lines = [
                f"📊 *Bot Status*",
                f"▶️ Status: {status_str}",
                f"⏰ Schedule: {schedule_str}",
                f"📢 Channels: {len(channels_dict)}"
            ]
            if channels_dict:
                lines.append("📋 Channel list:")
                for cid, info in channels_dict.items():
                    icon = "🟢" if info.get("enabled", True) else "🔴"
                    state = "Sending" if info.get("enabled", True) else "Limited"
                    lines.append(f"  {icon} {cid} [{state}]")
            send_message(chat_id, '\n'.join(lines))
            return

        if chat_id in user_states:
            action = user_states[chat_id]
            del user_states[chat_id]

            channel_identifier = text.strip()
            if not channel_identifier.startswith('@'):
                send_message(chat_id, "❌ Username must start with @ (e.g., @my_channel)")
                return

            if action == "add_channel":
                try:
                    resp = requests.get(f"{BASE_URL}/getChat?chat_id={channel_identifier}", timeout=10)
                    data = resp.json()
                    if not data.get("ok"):
                        send_message(chat_id, f"❌ Cannot access channel.\nError: {data.get('description', 'Unknown')}\n\nMake sure:\n1. Bot is admin\n2. Username is correct")
                        return
                    chat_info = data["result"]
                    channel_title = chat_info.get("title", channel_identifier)
                except Exception as e:
                    send_message(chat_id, f"❌ API error: {e}")
                    return
                chats = get_broadcast_chats()
                if channel_identifier in chats:
                    send_message(chat_id, "❌ This channel is already in the broadcast list.")
                    return
                chats[channel_identifier] = {"enabled": True}
                save_broadcast_chats(chats)
                send_message(chat_id, f"✅ Channel {channel_title} added. Total: {len(chats)}")
                return

            elif action == "remove_channel":
                chats = get_broadcast_chats()
                if channel_identifier in chats:
                    del chats[channel_identifier]
                    save_broadcast_chats(chats)
                    send_message(chat_id, f"❌ Channel {channel_identifier} removed.")
                else:
                    send_message(chat_id, "❌ Channel not found in the list.")
                return

            elif action == "toggle_channel":
                chats = get_broadcast_chats()
                if channel_identifier not in chats:
                    send_message(chat_id, "❌ Channel not found in the list.")
                    return
                current = chats[channel_identifier].get("enabled", True)
                chats[channel_identifier]["enabled"] = not current
                save_broadcast_chats(chats)
                new_status = "UNLIMITED ✅ (will receive messages)" if not current else "LIMITED ❌ (will NOT receive messages)"
                send_message(chat_id, f"Channel {channel_identifier} is now {new_status}")
                
            elif action == "test_channel":
                try:
                    resp = requests.get(f"{BASE_URL}/getChat?chat_id={channel_identifier}", timeout=5)
                    data = resp.json()
                    if data.get("ok"):
                        chat_info = data["result"]
                        title = chat_info.get("title", "No title")
                        send_message(chat_id, f"✅ Bot can access:\nTitle: {title}\nID: {channel_identifier}")
                    else:
                        send_message(chat_id, f"❌ Cannot access.\nError: {data.get('description', 'Unknown')}\n\nPossible reasons:\n- Bot not admin\n- Wrong username/ID\n- Channel does not exist")
                except Exception as e:
                    send_message(chat_id, f"⚠️ API error: {e}")
                return

        elif text == "/add_channel" or text == "➕ Add Channel":
            user_states[chat_id] = "add_channel"
            send_message(chat_id, "Please send the channel username (e.g., @my_channel):")
            return

        elif text == "/remove_channel" or text == "➖ Remove Channel":
            user_states[chat_id] = "remove_channel"
            send_message(chat_id, "Please send the channel username to remove (e.g., @my_channel):")
            return

        elif text == "/toggle_channel" or text == "⛔ Limit Channel":
            user_states[chat_id] = "toggle_channel"
            send_message(chat_id, "Please send the channel username to limit/unlimit (e.g., @my_channel):")
            return

        elif text == "/test_channel" or text == "🔍 Test Channel":
            user_states[chat_id] = "test_channel"
            send_message(chat_id, "Please send the channel username to test (e.g., @my_channel):")
            return

        elif text.startswith("/clearallch") or text == "💢 Delete All Channels":
            chats = get_broadcast_chats()
            if not chats:
                send_message(chat_id, "No channels to delete.")
            else:
                count = len(chats)
                save_broadcast_chats({})
                send_message(chat_id, f"🗑️ Removed {count} channels.")
            return

        elif text == "/list_channels" or text == "📋 List Channels":
            chats = get_broadcast_chats()
            if chats:
                lines = ["📋 Registered channels:"]
                for cid in chats:
                    lines.append(f"• {cid}")
                send_message(chat_id, '\n'.join(lines))
            else:
                send_message(chat_id, "No channels registered. Use /add_channel")
            return

        elif text == "/broadcast_now" or text == "📢 Broadcast Now":
            send_message(chat_id, "🔄 Fetching prices and broadcasting...")
            prices = get_gold_prices()
            msg = format_prices_message(prices)
            channels_dict = get_broadcast_chats()
            if not channels_dict:
                send_message(chat_id, "⚠️ No channels registered. Use /add_channel")
            else:
                success = 0
                for cid, info in channels_dict.items():
                    if not info.get("enabled", True):
                        continue
                    try:
                        send_message(cid, msg)
                        success += 1
                    except Exception as e:
                        print(f"Failed to send to {cid}: {e}")
                send_message(chat_id, f"✅ Sent to {success} of {len(channels_dict)} channels (disabled channels excluded)")
            return

        else:
            pass

    except Exception as e:
        print(f"Handler error: {e}")
        send_message(chat_id, "❗ Internal error. Please try again.")

if __name__ == "__main__":
    asyncio.run(bot.run())