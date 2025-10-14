import telebot
import requests
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import logging
import warnings

# إخفاء التحذيرات
warnings.filterwarnings("ignore")

# ---------- إعدادات السكربت ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ProxyBot")

# إعدادات البوت
TOKEN = '8468502888:AAGZl6YpdMDMenGthyWT_r-5NLaY_cCymGc'
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# إعدادات الفحص
criticalASN = 'AS396982'
defaultPorts = [80, 443, 8080, 3128]
MAX_IPS_PER_MSG = 300
HTTP_TIMEOUT = 2
SCAN_CONCURRENCY = 200

# إدارة العمليات
user_operations = {}
waiting_proxy_url = set()

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

def calculate_strength(protocols_count, response_time):
    if protocols_count == 3 and response_time < 1.5: return "قوي 💪"
    elif protocols_count >= 2 and response_time < 2.5: return "متوسط 🔸"  
    else: return "ضعيف 🔻"

def query_ip_api(ip):
    try:
        r = requests.get(f'http://ip-api.com/json/{ip}?fields=status,country,isp,as,org', timeout=5)
        data = r.json()
        return data if data.get('status') == 'success' else None
    except: return None

# ---------------- دوال الفحص (النسخة المحسنة) ----------------
def check_http(ip, port):
    """فحص HTTP - مرن مثل السكربت الأساسي"""
    try:
        response = requests.get(
            f'http://{ip}:{port}',
            timeout=HTTP_TIMEOUT,
            headers={'User-Agent': 'Mozilla/5.0'},
            allow_redirects=True
        )
        return response.status_code < 500
    except: return False

def check_https(ip, port):
    """فحص HTTPS - مرن مثل السكربت الأساسي"""
    try:
        response = requests.get(
            f'https://{ip}:{port}',
            timeout=HTTP_TIMEOUT,
            headers={'User-Agent': 'Mozilla/5.0'},
            allow_redirects=True,
            verify=False
        )
        return response.status_code < 500
    except: return False

def check_connect(ip, port):
    """فحص CONNECT - لـ port 80 فقط"""
    if port != 80: return False
    try:
        sock = socket.create_connection((ip, port), timeout=HTTP_TIMEOUT)
        sock.send(b"CONNECT www.google.com:443 HTTP/1.1\r\nHost: www.google.com:443\r\n\r\n")
        response = sock.recv(1024).decode()
        sock.close()
        return '200' in response or 'Connection established' in response
    except: return False

def smart_proxy_scan(ip, port):
    """الفحص الرئيسي - مرن وفعال مثل الأساسي"""
    protocols = []
    start_time = time.time()
    
    # فحص HTTP
    if check_http(ip, port):
        protocols.append("HTTP")
    
    # فحص HTTPS
    if check_https(ip, port):
        protocols.append("HTTPS")
    
    # فحص CONNECT (لـ port 80 فقط)
    if check_connect(ip, port):
        protocols.append("CONNECT")
    
    response_time = time.time() - start_time
    return protocols, response_time

def perform_quick_scan(chat_id, ip, ports=None):
    """فحص سريع - يعرض كل النتائج الناجحة"""
    if ports is None: ports = defaultPorts
    
    for port in ports:
        protocols, response_time = smart_proxy_scan(ip, port)
        
        if protocols:  # ✅ يعرض إذا وجد أي بروتوكول ناجح
            ip_data = query_ip_api(ip)
            country = ip_data.get('country', 'N/A') if ip_data else 'N/A'
            isp = ip_data.get('isp', 'N/A') if ip_data else 'N/A'
            
            # تصنيف القوة
            strength = calculate_strength(len(protocols), response_time)
            
            # إعداد الرسالة
            as_badge = "🔴" if ip_data and criticalASN in ip_data.get('as', '') else "⚪"
            
            result_message = f"""
📍 **{ip}:{port}**
💪 **القوة:** {strength}
🔸 **البروتوكولات:** {' • '.join(protocols)}
⚡ **الاستجابة:** {response_time:.1f} ثانية
✅ **مفتوح:** {', '.join(protocols)}
🏢 **{isp}** {as_badge}
🌍 **{country}**
"""
            bot.send_message(chat_id, result_message, parse_mode="Markdown")
            
            # ✅ رسالة تنبيه Google المختصرة
            if ip_data and criticalASN in ip_data.get('as', ''):
                google_alert = f"🚨🚨 تنبيه عاجل! وجد بروكسي ضمن ASN المهم جداً {criticalASN} — IP: {ip}"
                bot.send_message(chat_id, google_alert)
            
            return True
    return False

# ---------------- الفحص الجماعي الذكي ----------------
def process_bulk_quick_scan(chat_id, ip_list):
    user_operations[chat_id] = {'stop': False, 'active_proxies': []}
    
    total_ips = len(ip_list)
    scanned_count = 0
    active_count = 0
    
    progress_msg = bot.send_message(chat_id, 
        f"🔄 **جاري الفحص النشط**\n\n✅ **تم فحص:** 0/{total_ips}\n🟢 **الشغالة:** 0 ✅\n📊 **التقدم:** 0% ▱▱▱▱▱▱▱▱▱▱")

    # فحص متوازي حقيقي
    with ThreadPoolExecutor(max_workers=SCAN_CONCURRENCY) as executor:
        futures = []
        for item in ip_list:
            if user_operations[chat_id]['stop']:
                break
            future = executor.submit(perform_quick_scan, chat_id, item['ip'], item['ports'])
            futures.append(future)
        
        for i, future in enumerate(futures):
            if user_operations[chat_id]['stop']:
                break
                
            try:
                is_active = future.result(timeout=10)
                scanned_count = i + 1
                if is_active:
                    active_count += 1
                
                # تحديث الشريط كل 10 عمليات
                if scanned_count % 10 == 0 or scanned_count == total_ips:
                    percentage = (scanned_count / total_ips) * 100
                    progress_text = f"""
🔄 **جاري الفحص النشط**

✅ **تم فحص:** {scanned_count}/{total_ips}
🟢 **الشغالة:** {active_count} ✅
📊 **التقدم:** {percentage:.0f}% {create_progress_bar(percentage)}
"""
                    try:
                        bot.edit_message_text(progress_text, chat_id, progress_msg.message_id)
                    except: pass
                    
            except: 
                scanned_count += 1
    
    # النتائج النهائية
    success_rate = (active_count / scanned_count * 100) if scanned_count > 0 else 0
    final_message = f"""
🎉 **الفحص اكتمل!**

📈 **النتائج النهائية:**
• 🔢 **المفحوصة:** {total_ips} بروكسي
• 🟢 **الشغالة:** {active_count} ✅
• 📊 **النجاح:** {success_rate:.1f}% {create_progress_bar(success_rate)}
"""
    bot.send_message(chat_id, final_message)
    
    if chat_id in user_operations:
        del user_operations[chat_id]

# ---------------- جلب البروكسيات ----------------
def fetch_proxies_from_url(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            proxies = []
            for line in r.text.splitlines()[:500]:
                line = line.strip()
                if ':' in line and '.' in line:
                    parts = line.split(':')
                    if len(parts) >= 2 and validate_ip(parts[0]) and parts[1].isdigit():
                        proxies.append(f"{parts[0]}:{parts[1]}")
            return proxies
    except: return []
    return []

def process_custom_proxies_scan(chat_id, custom_url):
    progress_msg = bot.send_message(chat_id, "🔍 **جاري جلب البروكسيات...**")
    
    proxies = fetch_proxies_from_url(custom_url)
    if not proxies:
        bot.send_message(chat_id, "❌ لم يتم العثور على بروكسيات")
        return
    
    bot.edit_message_text(f"🌐 **تم جلب {len(proxies)} بروكسي**\n🚀 **بدء الفحص...**", 
                         chat_id, progress_msg.message_id)
    
    ip_list = [{'ip': p.split(':')[0], 'ports': [int(p.split(':')[1])]} for p in proxies if ':' in p]
    process_bulk_quick_scan(chat_id, ip_list)

# ---------------- دوال SSH ----------------
def get_ssh_account_sync():
    """استدعاء API جلب SSH"""
    try:
        SSH_API_URL = "https://painel.meowssh.shop:5000/test_ssh_public"
        SSH_PAYLOAD = {"store_owner_id": 1}
        SSH_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
        
        r = requests.post(SSH_API_URL, json=SSH_PAYLOAD, headers=SSH_HEADERS, timeout=10)
        if r.status_code in [200, 201]:
            data = r.json()
            usuario = data.get("Usuario")
            senha = data.get("Senha")
            return f"👤 <b>Usuario:</b> <code>{usuario}</code>\n🔑 <b>Senha:</b> <code>{senha}</code>"
        else:
            return f"❌ خطأ {r.status_code}"
    except Exception as e:
        return f"🚨 خطأ بالاتصال:\n{str(e)}"

def handle_ssh_generate(chat_id):
    """تشغيل استدعاء SSH في Thread"""
    def job():
        bot.send_message(chat_id, "🔑 جاري استخراج حساب SSH...")
        result = get_ssh_account_sync()
        bot.send_message(chat_id, result)
        inline_kb = telebot.types.InlineKeyboardMarkup()
        inline_kb.row(telebot.types.InlineKeyboardButton("🔑 استخراج آخر", callback_data='ssh_generate'))
        inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data='back_main'))
        bot.send_message(chat_id, "🔄 اختر الإجراء التالي:", reply_markup=inline_kb)
    threading.Thread(target=job, daemon=True).start()

# ---------------- أوامر البوت ----------------
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    user_operations.pop(chat_id, None)
    
    welcome_msg = """
🎯 **بوت الفحص الذكي للبروكسيات**

⚡ **المميزات:**
• فحص HTTP • HTTPS • CONNECT
• تصنيف تلقائي للقوة 💪🔸🔻  
• نتائج سريعة وموثوقة

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
        bot.send_message(chat_id, "⏹️ **تم إيقاف الفحص**\n\n📊 **جاري جمع النتائج...**")
    else:
        bot.send_message(chat_id, "⚠️ لا توجد عمليات فحص جارية")

@bot.message_handler(commands=['ssh'])
def ssh_command(message):
    handle_ssh_generate(message.chat.id)

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    if call.data == 'fast_scan':
        bot.send_message(chat_id,
            '⚡ **الفحص السريع**\n\n'
            'أرسل IP أو قائمة IPs:\n\n'
            '📝 **أمثلة:**\n'
            '• 194.35.12.45:3128\n'
            '• 194.35.12.45:80,443\n'
            '• 194.35.12.45\n\n'
            '🔍 **سيتم فحص HTTP • HTTPS • CONNECT**')
    elif call.data == 'fetch_proxies':
        waiting_proxy_url.add(chat_id)
        bot.send_message(chat_id,
            '🌐 **جلب بروكسيات**\n\n'
            'أرسل رابط قائمة البروكسيات:\n\n'
            '📝 **مثال:**\n'
            'https://raw.githubusercontent.com/.../proxy.txt')
    elif call.data == 'ssh_generate':
        handle_ssh_generate(chat_id)
    elif call.data == 'back_main':
        start_message(call.message)

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
            except: 
                ip_list.append({'ip': ip, 'ports': defaultPorts})
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