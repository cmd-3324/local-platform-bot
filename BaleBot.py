# Gold Price Bot - Bale Messenger - Scrapes tgju.org, broadcasts to channels
from bale import Bot, Message
import asyncio
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import json 
import os
from time import sleep
import re
from openai import OpenAI
import matplotlib
matplotlib.use('Agg')          # non-interactive backend, essential for VPS
import matplotlib.pyplot as plt
import io
from dotenv import load_dotenv
import csv
load_dotenv()
TOKEN = os.getenv("TOKEN")
bot = Bot(token=TOKEN)
FALLBACK_CSV = os.path.join(os.path.dirname(__file__), "fallback.csv")
CONFIG_FILE = "config.json"
BROADCAST_DIR = "broadcast_chats"
BASE_URL = f"https://tapi.bale.ai/bot{TOKEN}"

SYSTEM_PROMPT = """
You are a financial statistics assistant on Bale messenger. 
Your job is to analyze current prices and provide clear, concise summaries in Persian.
When given price data, you:
- Highlight the most important changes (sharp rises or drops)
- Compare prices when relevant
- Explain what the numbers mean in simple terms
- Keep responses under 200 words unless asked for details
- Always mention the source of the data briefly
"""

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"


def ensure_dir():
    if not os.path.exists(BROADCAST_DIR):
        os.makedirs(BROADCAST_DIR)
def check_internet():
    try:
        requests.get("https://google.com", timeout=5)
        return True
    except:
        return False

def load_json(path, default):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if not content:
                    return default
                return json.loads(content)
        except (json.JSONDecodeError, ValueError):
            return default
    return default

def save_json(path, info):
    if not isinstance(info, dict):
        raise TypeError(f"Expected dict, got {type(info)}")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1, ensure_ascii=False)

def get_config():
    data = load_json(CONFIG_FILE, {"disabled": False, "schedule": None})
    if data is None:
        return {"disabled": False, "schedule": None}
    return data

def save_config(cfg):
    save_json(CONFIG_FILE, cfg)

def get_broadcast_chats(chat_id):
    ensure_dir()
    filepath = os.path.join(BROADCAST_DIR, f"user_{chat_id}.json")
    return load_json(filepath, {})

def save_broadcast_chats(chat_id, channels):
    ensure_dir()
    filepath = os.path.join(BROADCAST_DIR, f"user_{chat_id}.json")
    save_json(filepath, channels)

def get_chat_name(channel_id):
    if isinstance(channel_id, str) and channel_id.startswith("@"):
        return str(channel_id)
    try:
        response = requests.get(f"{BASE_URL}/getChat?chat_id={channel_id}", timeout=5)
        if response.status_code == 200:
            data = response.json()
            if data.get("ok"):
                chat_metadata = data['result']
                return chat_metadata.get("title", str(channel_id))
            else:
                return data.get("description", "Unknown Error Occured")
    except Exception as e:
        return f"Error Occured : {e}"
    return str(channel_id)

def get_gold_prices():
    """Scrape gold and currency prices from tgju.org"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        
        prices = {}
        
        #currency page
        response = requests.get('https://www.tgju.org/currency', headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # currency rows
        for row in soup.find_all('tr', {'data-market-row': True}):
            name_tag = row.find('th')
            price_tag = row.find('td', class_='nf')
            
            if name_tag and price_tag:
                name = name_tag.get_text(strip=True)
                price_raw = price_tag.get_text(strip=True)
                price_clean = re.sub(r'[^\d]', '', price_raw)
                
                if price_clean:
                    prices[name] = price_clean
        
        # Scrape gold page for additional items
        gold_response = requests.get('https://www.tgju.org/gold-chart', headers=headers, timeout=15)
        gold_soup = BeautifulSoup(gold_response.text, 'html.parser')
        
        for row in gold_soup.find_all('tr', {'data-market-row': True}):
            name_tag = row.find('th')
            price_tag = row.find('td', class_='nf')
            
            if name_tag and price_tag:
                name = name_tag.get_text(strip=True)
                price_raw = price_tag.get_text(strip=True)
                price_clean = re.sub(r'[^\d]', '', price_raw)
                
                if price_clean and name not in prices:
                    prices[name] = price_clean
        
        if prices:
            return prices
        
        return {'error': 'Unable to fetch prices from tgju.org'}
        
    except Exception as e:
        return {'error': f'Scraping error: {str(e)[:50]}...'}
    
    
def is_channel_used(channel_identiy):
    ensure_dir()
    for filename in os.listdir(BROADCAST_DIR):
        if filename.startswith("user_") and filename.endswith(".json"):
            filepath = os.path.join(BROADCAST_DIR,filename)
            data = load_json(filepath, "")
            if channel_identiy in data:
                return True
    return False
def format_prices_message(prices):
    if not prices:
        return "⚠️ خطا در دریافت قیمت از tala.ir\nلطفاً چند دقیقه دیگر تلاش کنید."
    if 'error' in prices:
        return f"⚠️ {prices['error']}"
    lines = ["🏆 قیمت طلا و سکه – tgju.org\n"]
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
        current_key = datetime.now().strftime('%Y%m%d%H%M')
        cfg = get_config()
        if cfg['disabled']:
            await asyncio.sleep(60)
            continue
        sched = cfg.get('schedule')
        if not sched or sched['hour'] != datetime.now().hour or sched['minute'] != datetime.now().minute:
            await asyncio.sleep(60)
            continue
        if last_sent.get('key') == current_key:
            await asyncio.sleep(60)
            continue

        prices = get_gold_prices()
        msg = format_prices_message(prices)
        
        ensure_dir()
        
        for filename in os.listdir(BROADCAST_DIR):
            if not filename.startswith("user_") or not filename.endswith(".json"):
                continue
            try:
                user_id_str = filename[5:-5]  
                user_id = int(user_id_str)
            except ValueError:
                continue
            channels_dict = get_broadcast_chats(user_id)
            for cid, info in channels_dict.items():
                if not info.get("enabled", True):
                    continue
                try:
                    send_message(cid, msg)
                except Exception as e:
                    print(f"Failed to send to {cid}: {e}")
        last_sent['key'] = current_key
        await asyncio.sleep(60)

def load_fallback_prices():
    if not os.path.exists(FALLBACK_CSV):
        return {'error': f'CSV file not found: {FALLBACK_CSV}'}
    
    try:
        with open(FALLBACK_CSV, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
        
        if len(lines) < 2:
            return {'error': 'CSV has no data rows'}
        
        headers = lines[0].strip().split(',')
        
        item_index = 0
        price_index = 1
        
        for i, header in enumerate(headers):
            if 'item' in header.lower():
                item_index = i
            if 'price' in header.lower():
                price_index = i
        
        prices = {}
        
        for line_num, line in enumerate(lines[1:], start=2):
            line = line.strip()
            if not line:
                continue
            
            parts = line.split(',')
            
            if len(parts) <= max(item_index, price_index):
                continue
            
            item_name = parts[item_index].strip()
            price_value = parts[price_index].strip()
            
            if item_name and price_value:
                prices[item_name] = price_value
        
        if not prices:
            return {'error': f'No valid data parsed. Found headers: {headers}'}
        
        return prices
        
    except Exception as e:
        return {'error': f'CSV read error: {str(e)}'}

def ai_examine():
    """
    Get price data (live or fallback CSV) and send it to DeepSeek for a Persian analysis.
    Follows the same fallback logic as the chart method.
    """
    # --- 1. Get prices (exact same pattern as /chart handler) ---
    prices = None
    source = None
    
    if check_internet():
        prices = get_gold_prices()
        if prices and 'error' not in prices and not all(v == '-' for v in prices.values()):
            source = "tala.ir (live)"
    
    if not prices or 'error' in prices or all(v == '-' for v in prices.values() if v != 'error'):
        # Fallback to CSV, just like the chart does
        prices = load_fallback_prices()
        if prices and 'error' not in prices:
            source = "CSV  (latest saved)"
    
    if not prices or 'error' in prices:
        return "⚠️ Unable to fetch price data from any source. Please try again later."
    
    # --- 2. Format prices into readable text ---
    price_lines = []
    for name, value in prices.items():
        if value and value != '-' and value != 'error':
            price_lines.append(f"- {name}: {value} Rial")
    
    if not price_lines:
        return "⚠️ No valid price data available for analysis."
    
    price_text = "\n".join(price_lines)
    
    # --- 3. Build the request to DeepSeek ---
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Here is the latest market data from {source}:\n\n{price_text}\n\nPlease provide a concise Persian summary of the market situation."}
    ]
    
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "deepseek-chat",
        "messages": messages,
        "stream": False
    }
    
    # --- 4. Call the API (using requests directly to avoid 'governor' bug) ---
    try:
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            analysis = data["choices"][0]["message"]["content"]
            source_note = "📡 Live analysis" if "live" in source else "💾 Offline analysis (CSV backup)"
            return f"{source_note}\n\n📊 AI Market Analysis:\n\n{analysis}\n\n📅 {datetime.now().strftime('%Y/%m/%d %H:%M')}"
        else:
            return f"⚠️ AI service error (Code: {resp.status_code}). Please try again later."
    except requests.exceptions.Timeout:
        return "⚠️ AI service timeout. Please try again."
    except Exception as e:
        return f"⚠️ AI analysis error: {str(e)[:100]}"
    
    
def generate_price_chart(prices):
    if not isinstance(prices, dict):
        return None, 'Prices is not a dictionary'
    
    if 'error' in prices:
        return None, prices['error']
    
    valid_items = []
    valid_values = []
    
    for name, value in prices.items():
        if not value or value == '-':
            continue
        
        try:
            clean = value.replace(',', '').replace(' ', '').strip()
            num = int(clean)
            valid_items.append(name)
            valid_values.append(num)
        except ValueError:
            continue
    
    if not valid_items:
        return None, f'No numeric values found'
    
    try:
        fig, ax = plt.subplots(figsize=(14, max(8, len(valid_items) * 0.5)))
        
        colors = plt.cm.viridis([i/len(valid_values) for i in range(len(valid_values))])
        
        bars = ax.bar(valid_items, valid_values, color=colors, edgecolor='black', linewidth=1)
        
        ax.set_ylabel('Price (IRR)', fontsize=14, fontweight='bold')
        ax.set_xlabel('Currency', fontsize=14, fontweight='bold', color="red")
        ax.set_title('Gold & Currency Market Prices - 26/5/25', fontsize=18, fontweight='bold', pad=20)
        
        ax.set_xticks(range(len(valid_items)))
        ax.set_xticklabels(valid_items, fontsize=11, fontweight='bold', rotation=0, ha='right')
        plt.yticks(fontsize=11, fontweight='medium')
        
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        for bar, value in zip(bars, valid_values):
            if value >= 1_000_000_000:
                label = f'{value/1_000_000_000:.1f}B'
            elif value >= 1_000_000:
                label = f'{value/1_000_000:.1f}M'
            else:
                label = f'{value:,}'
            
            ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + (bar.get_height() * 0.01),
                   label, ha='center', va='bottom', fontsize=10, fontweight='bold', rotation=0)
        
        plt.tight_layout()
        
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=120, bbox_inches='tight')
        buf.seek(0)
        plt.close(fig)
        
        return buf, None
    except Exception as e:
        return None, f'Chart creation error: {str(e)}'
def send_photo(chat_id, photo_bytes):
    url = f"{BASE_URL}/sendPhoto"
    photo_bytes.seek(0)
    files = {'photo': ('chart.png', photo_bytes, 'image/png')}
    data = {'chat_id': chat_id}
    
    try:
        response = requests.post(url, files=files, data=data, timeout=30)
        result = response.json()
        return result.get('ok', False), result.get('description', '')
    except Exception as e:
        return False, str(e)
user_states = {}


@bot.event
async def on_ready():
    print(f"Bot ready – {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    asyncio.create_task(scheduled_broadcast())

@bot.event
async def on_message(message: Message):
    if getattr(message.chat, 'type', '') != 'private':
        return
    chat_id = message.chat.id
    chats = get_broadcast_chats(chat_id)
    text = message.text.strip() if message.text else ""
    
    cfg = get_config()
    disabled = cfg.get('disabled', False)
    channel_identifier = text.strip()
    if chat_id in user_states:
        action = user_states[chat_id]
        del user_states[chat_id]

        if action == "Confirm_shot":
            if text.upper() == "Y":
                save_broadcast_chats(chat_id, {})
                send_message(chat_id, "All channels deleted.")
            else:
                send_message(chat_id, "Cancelled.")
            return
        
 

        if action == "add_channel":  
            
            if not channel_identifier.startswith('@'):
                send_message(chat_id, "❌ Username must start with @ (e.g., @my_channel)")
                return
            if is_channel_used(channel_identifier):
                send_message(chat_id,"❌ Bot is Already added to this channel ")
                return 
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
            if channel_identifier in chats:
                send_message(chat_id, "❌ This channel is already in the broadcast list.")
                return
            chats[channel_identifier] = {"enabled": True}
            save_broadcast_chats(chat_id, chats)
            send_message(chat_id, f"✅ Channel {channel_title} added. Total: {len(chats)}")
            return
        elif action == "set_time":
            try:
                hour, minute = map(int, text.split(':'))
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    cfg = get_config()
                    cfg['schedule'] = {'hour': hour, 'minute': minute}
                    save_config(cfg)
                    send_message(chat_id, f"✅ Broadcast set to {hour:02d}:{minute:02d}")
                else:
                    send_message(chat_id, "❌ Invalid time. Use HH:MM (0-23, 0-59)")
            except:
                send_message(chat_id, "❌ Send time as HH:MM (e.g., 14:30)")
            return
        elif action == "remove_channel":
            if channel_identifier in chats:
                del chats[channel_identifier]
                save_broadcast_chats(chat_id, chats)
                send_message(chat_id, f"❌ Channel {channel_identifier} removed.")
            else:
                send_message(chat_id, "❌ Channel not found in the list.")
            return

        elif action == "toggle_channel":
            chats = get_broadcast_chats(chat_id)
            if channel_identifier not in chats:
                send_message(chat_id, "❌ Channel not found in the list.")
                return
            current = chats[channel_identifier].get("enabled", True)
            chats[channel_identifier]["enabled"] = not current
            save_broadcast_chats(chat_id, chats)
            new_status = "UNLIMITED ✅ (will receive messages)" if not current else "LIMITED ❌ (will NOT receive messages)"
            send_message(chat_id, f"Channel {channel_identifier} is now {new_status}")
            return

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

    if disabled and text not in ["/start", "/enable", "✅ Enable bot", "/support"]:
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
            buttons.append(["📊 Chart"])
            buttons.append(["🎡AI Examine"])
            buttons.append(["⛔ Limit/Unlimit Channel"])
            buttons.append(["Access Support"])
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
                "/status – وضعیت بات + لیست کانال‌ها\n"
                "/add_channel – اضافه کردن کانال\n"
                "/remove_channel – حذف کانال\n"
                "/toggle_channel – محدود/نامحدود کردن کانال\n"
                "/test_channel – تست دسترسی\n"
                "/chart - نمودار نرخ\n"
                "/AI_Examine - نحلیل هوش مصنوعی "
                "/list_channels – لیست کانال‌ها\n"
                "/support – پشتیبانی\n"
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
                ['📊 Chart'],
                ["⛔ Limit/Unlimit Channel"],
                ["Access Support"]
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
                ["🎡AI Examine"],
                ["⛔ Limit/Unlimit Channel"],
                ["Access Support"]
            ]
            markup = build_reply_markup(buttons)
            send_message(chat_id, "🟢 Bot enabled. Scheduled messages will be sent.", markup)
            return

        elif text in ["Access Support", "/support"]:
            send_message(chat_id, "Email: mh135411@mail.ir\nPhone: +98-903-196-08-60")
            return
        elif text == "AI_Examine" or text == "🎡AI Examine":
            analysis_result = ""
            if not check_internet():
                send_message(chat_id, "🌍 International internet timeout. Cannot perform AI analysis.")
                await asyncio.sleep(3) 
                if os.path.exists(FALLBACK_CSV):
                    send_message(chat_id, "Latest analysis is about to be shared!")
                    analysis_result = ai_examine()
                return
            
            send_message(chat_id, "🔍 Analyzing market data with AI, please wait...")
            analysis_result = ai_examine()
            send_message(chat_id, analysis_result)
            return
        elif text == "⏰ Set Time":
            if text == "⏰ Set Time":
                user_states[chat_id] = "set_time"  
                send_message(chat_id, "⏰ Send time as HH:MM (e.g., 09:15)")
                return
            parts = text.split()
            if len(parts) != 2:
                send_message(chat_id, "Usage: /set_time HH:MM")
                return
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
            channels_dict = get_broadcast_chats(chat_id)
            line = "" if check_internet() else "🌍 International internet timeout. Can not broadcast due to used source/."
            lines = [
                line,
                f"📊 *Bot Status*",
                f"▶️ Status: {status_str}",
                f"⏰ Schedule: {schedule_str}",
                f"📢 Channels: {len(channels_dict)}"
            ]
            state_text = "Sending" if check_internet() else "Paused Sends"
            if channels_dict:
                lines.append("📋 Channel list:")
                for cid, info in channels_dict.items():
                    icon = "🟢" if info.get("enabled", True) else "🔴"
                    state = state_text if info.get("enabled", True) else "Limited"
                    lines.append(f"  {icon} {cid} [{state}]")
            send_message(chat_id, '\n'.join(lines))
            return

        elif text == "/add_channel" or text == "➕ Add Channel":
            chats = get_broadcast_chats(chat_id)
            if len(chats) >= 12:
                send_message(chat_id, "❌ Maximum 12 channels allowed. Remove one first.")
                return
            user_states[chat_id] = "add_channel"
            send_message(chat_id, "Please send the channel username (e.g., @my_channel):")
            return

        elif text == "/remove_channel" or text == "➖ Remove Channel":
            user_states[chat_id] = "remove_channel"
            send_message(chat_id, "Please send the channel username to remove (e.g., @my_channel):")
            return
        elif text == "/chart" or text == "📊 Chart":
            send_message(chat_id, "Reading data...")
            
            prices = None
            
            if check_internet():
                prices = get_gold_prices()
                
            if not prices or 'error' in prices or all(v == '-' for v in prices.values() if v != 'error'):
                send_message(chat_id, "Internet scrape failed or all values empty. Loading from CSV...")
                prices = load_fallback_prices()
            
            chart_buffer, error = generate_price_chart(prices)
            
            if error:
                send_message(chat_id, f"Chart error: {error}")
                return
            
            success, api_error = send_photo(chat_id, chart_buffer)
            
            if success:
                send_message(chat_id, "Chart sent successfully")
            else:
                send_message(chat_id, f"Send failed: {api_error}")

        elif text == "/test_channel" or text == "🔍 Test Channel":
            user_states[chat_id] = "test_channel"
            send_message(chat_id, "Please send the channel username to test (e.g., @my_channel):")
            return

        elif text.startswith("/clearallch") or text == "💢 Delete All Channels":
            chats = get_broadcast_chats(chat_id)
            if not chats:
                send_message(chat_id, "No channels to delete.")
            else:
                user_states[chat_id] = "Confirm_shot"
                send_message(chat_id, "Are you sure you want to delete ALL channels? Send Y")
            return

        elif text == "/list_channels" or text == "📋 List Channels":
            chats = get_broadcast_chats(chat_id)
            if chats:
                lines = ["📋 Registered channels:"]
                for cid in chats:
                    lines.append(f"• {cid}")
                send_message(chat_id, '\n'.join(lines))
            else:
                send_message(chat_id, "No channels registered. Use /add_channel")
            return

        elif text == "/broadcast_now" or text == "📢 Broadcast Now":
            
            if not check_internet():
                send_message(chat_id, "🌍 International internet timeout.\nPlease try again later.")
                return 
            prices = get_gold_prices()
            msg = format_prices_message(prices)
            channels_dict = get_broadcast_chats(chat_id)
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
                send_message(chat_id, f"✅ Sent to {success} of {len(channels_dict)} channels (Limited channels excluded)")
            return

        else:
            pass

    except Exception as e:
        print(f"Handler error: {e}")
        send_message(chat_id, "❗ Internal error. Please try again.")

if __name__ == "__main__":
    asyncio.run(bot.run())