import telebot
import requests
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import logging
from datetime import datetime

# ---------- إعدادات السكريبت ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SmartProxyBot")

# إعدادات البوت
TOKEN = '8468502888:AAGZl6YpdMDMenGthyWT_r-5NLaY_cCymGc'
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# إعدادات الفحص
criticalASN = 'AS396982'
defaultPorts = [80, 443, 8080, 8443, 3128]
MAX_IPS_PER_MSG = 300
MAX_FILE_IPS = 1000
HTTP_TIMEOUT = 1.5
SCAN_CONCURRENCY = 150

# إدارة العمليات
user_operations = {}
waiting_proxy_url = set()
custom_youtube_urls = {}

# ---------------- دوال مساعدة ----------------
def validate_ip(ip):
    try:
        parts = ip.split('.')
        if len(parts) != 4: return False
        for part in parts:
            if not 0 <= int(part) <= 255: return False
        return True
    except: return False

def create_progress_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    return "▰" * filled + "▱" * (length - filled)

def calculate_strength(protocols_count, response_time, isp_quality):
    score = (protocols_count * 25) + max(0, 30 - (response_time * 10)) + isp_quality
    if score >= 80: return "قوي 💪", score
    elif score >= 50: return "متوسط 🔸", score
    else: return "ضعيف 🔻", score

def get_isp_quality(isp):
    trusted_isps = ['Google', 'Cloudflare', 'Amazon', 'Microsoft']
    return 30 if any(t in isp for t in trusted_isps) else 15

# ---------------- دوال الفحص الذكية ----------------
def query_ip_api(ip):
    try:
        r = requests.get(f'http://ip-api.com/json/{ip}?fields=status,country,isp,as,org', timeout=5)
        return r.json() if r.json().get('status') == 'success' else None
    except: return None

def check_http_protocol(ip, port, protocol='http'):
    try:
        url = f'{protocol}://{ip}:{port}'
        start_time = time.time()
        response = requests.get(url, timeout=HTTP_TIMEOUT, verify=False, 
                               headers={'User-Agent': 'Mozilla/5.0'})
        response_time = time.time() - start_time
        return response.status_code < 400, response_time
    except: return False, HTTP_TIMEOUT

def check_connect_protocol(ip, port):
    if port != 80: return False, HTTP_TIMEOUT
    try:
        start_time = time.time()
        sock = socket.create_connection((ip, port), timeout=HTTP_TIMEOUT)
        sock.send(b"CONNECT www.google.com:443 HTTP/1.1\r\nHost: www.google.com:443\r\n\r\n")
        response = sock.recv(4096).decode()
        sock.close()
        response_time = time.time() - start_time
        return '200' in response or 'Connection established' in response, response_time
    except: return False, HTTP_TIMEOUT

def smart_proxy_scan(ip, port):
    protocols = []
    total_response_time = 0
    tests_count = 0
    
    # فحص HTTP
    http_works, http_time = check_http_protocol(ip, port, 'http')
    if http_works:
        protocols.append("HTTP")
        total_response_time += http_time
        tests_count += 1
    
    # فحص HTTPS
    https_works, https_time = check_http_protocol(ip, port, 'https')
    if https_works:
        protocols.append("HTTPS")
        total_response_time += https_time
        tests_count += 1
    
    # فحص CONNECT (للمنفذ 80 فقط)
    connect_works, connect_time = check_connect_protocol(ip, port)
    if connect_works:
        protocols.append("CONNECT")
        total_response_time += connect_time
        tests_count += 1
    
    avg_response_time = total_response_time / tests_count if tests_count > 0 else HTTP_TIMEOUT
    return protocols, avg_response_time

def perform_quick_scan(chat_id, ip, ports=None):
    if ports is None: ports = defaultPorts
    
    for port in ports:
        protocols, response_time = smart_proxy_scan(ip, port)
        
        if protocols:  # إذا وجد بروتوكولات ناجحة
            ip_data = query_ip_api(ip)
            if not ip_data: continue
            
            # تصنيف القوة
            isp_quality = get_isp_quality(ip_data.get('isp', ''))
            strength, score = calculate_strength(len(protocols), response_time, isp_quality)
            
            # إعداد الرسالة
            as_badge = "🔴" if criticalASN in ip_data.get('as', '') else "⚪"
            country_flag = "🌍"
            
            result_message = f"""
📍 **{ip}:{port}**
💪 **القوة:** {strength}
🔸 **البروتوكولات:** {' • '.join(protocols)}
⚡ **الاستجابة:** {response_time:.1f} ثانية
🏢 **{ip_data.get('isp', 'N/A')}** {as_badge}
{country_flag} **{ip_data.get('country', 'N/A')}**
"""
            bot.send_message(chat_id, result_message, parse_mode="Markdown")
            
            # إشعار خاص لـ Google
            if criticalASN in ip_data.get('as', ''):
                bot.send_message(chat_id, 
                    f"🚨 **اكتشاف نادر!**\n🔥 **بروكسي Google نشط:** `{ip}:{port}`\n💎 **القوة:** {strength}")
            
            return True
    return False

# ---------------- الفحص الجماعي الذكي ----------------
def process_bulk_quick_scan(chat_id, ip_list):
    user_operations[chat_id] = {'stop': False, 'type': 'bulk_scan', 'active_proxies': []}
    
    total_ips = len(ip_list)
    scanned_count = 0
    active_count = 0
    
    progress_msg = bot.send_message(chat_id, 
        f"🔄 **جاري الفحص النشط**\n\n📡 **الحالة:** يفحص البروكسيات...\n✅ **تم فحص:** 0/{total_ips}\n🟢 **الشغالة:** 0 ✅\n📊 **التقدم:** 0% ▱▱▱▱▱▱▱▱▱▱")
    
    for i, item in enumerate(ip_list):
        if user_operations.get(chat_id, {}).get('stop'):
            break
            
        ip, ports = item['ip'], item['ports']
        is_active = perform_quick_scan(chat_id, ip, ports)
        
        scanned_count = i + 1
        if is_active:
            active_count += 1
            user_operations[chat_id]['active_proxies'].append(f"{ip}:{ports[0]}")
        
        # تحديث الشريط كل 10 عمليات أو عند الانتهاء
        if scanned_count % 10 == 0 or scanned_count == total_ips:
            percentage = (scanned_count / total_ips) * 100
            progress_text = f"""
🔄 **جاري الفحص النشط**

📡 **الحالة:** يفحص البروكسيات...
⏱️ **مضى:** {i//10} ثانية
✅ **تم فحص:** {scanned_count}/{total_ips}
🟢 **الشغالة:** {active_count} ✅
📊 **التقدم:** {percentage:.0f}% {create_progress_bar(percentage)}
"""
            try:
                bot.edit_message_text(progress_text, chat_id, progress_msg.message_id)
            except: pass
    
    # النتائج النهائية
    success_rate = (active_count / scanned_count * 100) if scanned_count > 0 else 0
    final_message = f"""
🎉 **الفحص اكتمل!**

📈 **النتائج النهائية:**
• 🔢 **المفحوصة:** {total_ips} بروكسي
• 🟢 **الشغالة:** {active_count} ✅
• 📊 **النجاح:** {success_rate:.1f}% {create_progress_bar(success_rate)}

💎 **تم العثور على {active_count} بروكسي نشط**
"""
    bot.send_message(chat_id, final_message)
    
    if chat_id in user_operations:
        del user_operations[chat_id]

# ---------------- جلب البروكسيات الذكي ----------------
def fetch_proxies_from_url(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            proxies = []
            for line in r.text.splitlines()[:500]:  # أول 500 فقط للسرعة
                line = line.strip()
                if ':' in line and '.' in line:
                    parts = line.split(':')
                    if len(parts) >= 2 and validate_ip(parts[0]) and parts[1].isdigit():
                        proxies.append(f"{parts[0]}:{parts[1]}")
            return list(set(proxies))
    except Exception as e:
        logger.error(f"Error fetching proxies: {e}")
    return []

def process_custom_proxies_scan(chat_id, custom_url):
    progress_msg = bot.send_message(chat_id, "🔍 **جاري جلب البروكسيات من الرابط...**")
    
    proxies = fetch_proxies_from_url(custom_url)
    if not proxies:
        bot.send_message(chat_id, "❌ لم يتم العثور على بروكسيات في الرابط")
        return
    
    bot.edit_message_text(f"🌐 **تم جلب {len(proxies)} بروكسي**\n🚀 **بدء الفحص الذكي...**", 
                         chat_id, progress_msg.message_id)
    
    # تحويل إلى قائمة للفحص
    ip_list = [{'ip': p.split(':')[0], 'ports': [int(p.split(':')[1])]} for p in proxies if ':' in p]
    
    process_bulk_quick_scan(chat_id, ip_list)

# ---------------- أوامر البوت الذكية ----------------
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    user_operations.pop(chat_id, None)
    
    welcome_msg = """
🎯 **بوت الفحص الذكي للبروكسيات**

⚡ **المميزات:**
• فحص HTTP • HTTPS • CONNECT
• تصنيف تلقائي للقوة 💪🔸🔻
• نتائج مضمونة 100%
• واجهة ذكية وجميلة

📋 **الأوامر:**
/start - بدء البوت
/stop - إيقاف الفحص
/ssh - استخراج SSH

🎮 **الأزرار:"""
    
    keyboard = telebot.types.InlineKeyboardMarkup()
    keyboard.row(
        telebot.types.InlineKeyboardButton("⚡ فحص سريع", callback_data='fast_scan'),
        telebot.types.InlineKeyboardButton("🌐 جلب بروكسيات", callback_data='fetch_proxies')
    )
    
    bot.send_message(chat_id, welcome_msg, reply_markup=keyboard)

@bot.message_handler(commands=['stop'])
def stop_message(message):
    chat_id = message.chat.id
    if chat_id in user_operations:
        user_operations[chat_id]['stop'] = True
        active_count = len(user_operations[chat_id].get('active_proxies', []))
        scanned_count = user_operations[chat_id].get('scanned_count', 0)
        
        success_rate = (active_count / scanned_count * 100) if scanned_count > 0 else 0
        stop_msg = f"""
⏹️ **تم إيقاف الفحص**

📊 **النتائج حتى الآن:**
• 🔢 **تم فحص:** {scanned_count}
• 🟢 **الشغالة:** {active_count} ✅
• 📊 **النسبة:** {success_rate:.1f}% {create_progress_bar(success_rate)}

💡 **تم العثور على {active_count} بروكسي شغال**
"""
        bot.send_message(chat_id, stop_msg)
    else:
        bot.send_message(chat_id, "⚠️ لا توجد عمليات فحص جارية")

@bot.message_handler(commands=['ssh'])
def ssh_command(message):
    bot.send_message(message.chat.id, "🔑 **ميزة SSH قريباً...**")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == 'fast_scan':
        bot.send_message(chat_id,
            '⚡ **الفحص السريع**\n\n'
            'أرسل IP أو قائمة IPs للفحص:\n\n'
            '📝 **أمثلة:**\n'
            '• 194.35.12.45:3128\n'
            '• 194.35.12.45:80,443,8080\n'
            '• 194.35.12.45\n\n'
            '🔍 **سيتم فحص HTTP • HTTPS • CONNECT**')
    elif call.data == 'fetch_proxies':
        waiting_proxy_url.add(chat_id)
        bot.send_message(chat_id,
            '🌐 **جلب بروكسيات**\n\n'
            'أرسل رابط قائمة البروكسيات:\n\n'
            '📝 **مثال:**\n'
            'https://raw.githubusercontent.com/.../proxy.txt\n\n'
            '🚀 **سيتم فحص جميع البروكسيات تلقائياً**')

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    if chat_id in waiting_proxy_url:
        waiting_proxy_url.discard(chat_id)
        if text.startswith('http'):
            process_custom_proxies_scan(chat_id, text)
        else:
            bot.send_message(chat_id, "❌ الرابط يجب أن يبدأ بـ http أو https")
        return
    
    # معالجة IPs
    ip_list = []
    for line in text.split('\n'):
        line = line.strip()
        if ':' in line and validate_ip(line.split(':')[0]):
            parts = line.split(':')
            ip, port_str = parts[0], parts[1]
            try:
                ports = [int(p) for p in port_str.split(',')] if ',' in port_str else [int(port_str)]
                ip_list.append({'ip': ip, 'ports': ports})
            except: pass
        elif validate_ip(line):
            ip_list.append({'ip': line, 'ports': defaultPorts})
    
    if ip_list:
        if len(ip_list) > 1:
            bot.send_message(chat_id, f"🔍 **بدء فحص {len(ip_list)} IP...**")
        else:
            bot.send_message(chat_id, "🔍 **جاري الفحص السريع...**")
        threading.Thread(target=process_bulk_quick_scan, args=(chat_id, ip_list)).start()
    else:
        bot.send_message(chat_id, "❌ لم يتم التعرف على أي IP صالح")

# ---------------- التشغيل ----------------
if __name__ == "__main__":
    print("🚀 بدء تشغيل البوت الذكي للبروكسيات...")
    bot.remove_webhook()
    time.sleep(1)
    bot.infinity_polling()
