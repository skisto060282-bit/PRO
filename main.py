import telebot
import requests
import socket
import threading
import time
from datetime import datetime
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# توكن البوت - ضعيه هنا
bot = telebot.TeleBot("8468502888:AAGZl6YpdMDMenGthyWT_r-5NLaY_cCymGc")

# تخزين العمليات الجارية
active_checks = {}

def get_ip_info(ip):
    """جلب معلومات IP متقدمة"""
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        data = response.json()
        
        asn = data.get('as', 'غير معروف')
        isp = data.get('isp', 'غير معروف')
        country = data.get('country', 'غير معروف')
        city = data.get('city', 'غير معروف')
        
        return {
            'asn': asn,
            'isp': isp,
            'country': country,
            'city': city,
            'status': data.get('status', 'fail')
        }
    except:
        return None

def check_single_proxy(proxy_ip, proxy_port, chat_id):
    """فحص بروكسي واحد بسرعة 150ms"""
    try:
        # فحص سريع (150ms timeout)
        proxy_dict = {
            'http': f"http://{proxy_ip}:{proxy_port}",
            'https': f"https://{proxy_ip}:{proxy_port}"
        }
        
        # فحص HTTP سريع
        start_time = time.time()
        try:
            response = requests.get('http://httpbin.org/ip', 
                                  proxies=proxy_dict, timeout=0.15)
            http_working = response.status_code == 200
            http_speed = int((time.time() - start_time) * 1000)
        except:
            http_working = False
            http_speed = 0
        
        # فحص CONNECT سريع
        connect_working = False
        connect_speed = 0
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.15)
            result = sock.connect_ex((proxy_ip, int(proxy_port)))
            connect_working = result == 0
            connect_speed = int((time.time() - start_time) * 1000)
            sock.close()
        except:
            pass
        
        # جلب معلومات IP
        ip_info = get_ip_info(proxy_ip)
        
        return {
            'ip': proxy_ip,
            'port': proxy_port,
            'http': http_working,
            'http_speed': http_speed,
            'connect': connect_working,
            'connect_speed': connect_speed,
            'ip_info': ip_info
        }
        
    except Exception as e:
        return None

def get_warning_emoji(isp, asn):
    """إرجاع إشارات تحذير حسب ISP و ASN"""
    warning = ""
    
    if "Google" in str(isp) or "Google" in str(asn):
        warning = "🔴🚨"
    elif "Amazon" in str(isp) or "AWS" in str(asn):
        warning = "🟡⚠️"
    elif "Microsoft" in str(isp):
        warning = "🔵ℹ️"
    elif any(word in str(isp) for word in ["Cloud", "Host", "Data Center"]):
        warning = "🟠📡"
    
    return warning

def create_main_keyboard():
    """إنشاء لوحة المفاتيح الرئيسية"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    btn1 = InlineKeyboardButton("🔍 فحص النص", callback_data="check_text")
    btn2 = InlineKeyboardButton("🌐 فحص رابط", callback_data="check_url")
    btn3 = InlineKeyboardButton("🛑 إيقاف البحث", callback_data="stop_check")
    
    keyboard.add(btn1, btn2)
    keyboard.add(btn3)
    
    return keyboard

@bot.message_handler(commands=['start', 'help'])
def start_command(message):
    """عند استخدام /start أو /help"""
    welcome_text = """
🛡️ **بوت فحص البروكسيات المتقدم** 🛡️

⚡ **سرعة الفحص:** 150ms
🔍 **أنواع الفحص:** HTTP / CONNECT
🚨 **كشف مزودي الخدمة:** Google, Amazon, etc

🎯 **اختر طريقة الفحص:**
    """
    
    bot.send_message(
        message.chat.id, 
        welcome_text,
        reply_markup=create_main_keyboard(),
        parse_mode='Markdown'
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    """معالجة الضغط على الأزرار"""
    chat_id = call.message.chat.id
    
    if call.data == "check_text":
        msg = bot.send_message(chat_id, "📝 أرسلي IP:Port أو قائمة بروكسيات:\nمثال: `192.168.1.1:8080`\nأو قائمة:\n`192.168.1.1:8080\n192.168.1.2:8080`", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_text_check)
        
    elif call.data == "check_url":
        msg = bot.send_message(chat_id, "🔗 أرسلي رابط يحتوي على بروكسيات:\nمثال: `https://example.com/proxies.txt`")
        bot.register_next_step_handler(msg, process_url_check)
        
    elif call.data == "stop_check":
        if chat_id in active_checks:
            active_checks[chat_id] = False
            bot.send_message(chat_id, "🛑 تم إيقاف البحث بنجاح!")
        else:
            bot.send_message(chat_id, "ℹ️ لا يوجد بحث جاري لإيقافه")
    
    elif call.data == "main_menu":
        start_command(call.message)

def process_text_check(message):
    """معالجة فحص النص"""
    chat_id = message.chat.id
    active_checks[chat_id] = True
    
    # تحليل النص المدخل
    proxies = []
    for line in message.text.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                ip = parts[0]
                port = parts[1]
                proxies.append((ip, port))
    
    if not proxies:
        bot.send_message(chat_id, "❌ لم أجد أي بروكسيات صالحة في النص")
        return
    
    bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies)} بروكسي...")
    
    # فحص جميع البروكسيات
    working_proxies = []
    
    for ip, port in proxies:
        if not active_checks.get(chat_id, True):
            break
            
        result = check_single_proxy(ip, port, chat_id)
        if result and (result['http'] or result['connect']):
            working_proxies.append(result)
    
    # عرض النتائج
    show_results(chat_id, working_proxies)

def process_url_check(message):
    """معالجة فحص الرابط"""
    chat_id = message.chat.id
    active_checks[chat_id] = True
    
    try:
        bot.send_message(chat_id, "⏬ جاري تحميل البروكسيات من الرابط...")
        
        # تحميل المحتوى من الرابط
        response = requests.get(message.text, timeout=10)
        content = response.text
        
        # استخراج البروكسيات
        proxies = []
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line and '.' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    ip = parts[0]
                    port = parts[1]
                    proxies.append((ip, port))
        
        if not proxies:
            bot.send_message(chat_id, "❌ لم أجد أي بروكسيات في الرابط")
            return
        
        bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies)} بروكسي...")
        
        # فحص البروكسيات
        working_proxies = []
        
        for ip, port in proxies:
            if not active_checks.get(chat_id, True):
                break
                
            result = check_single_proxy(ip, port, chat_id)
            if result and (result['http'] or result['connect']):
                working_proxies.append(result)
        
        # عرض النتائج
        show_results(chat_id, working_proxies)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في تحميل الرابط: {str(e)}")

def show_results(chat_id, working_proxies):
    """عرض البروكسيات الشغالة فقط"""
    if not working_proxies:
        bot.send_message(chat_id, "❌ لم أعثر على أي بروكسيات شغالة")
        return
    
    results_text = f"✅ **تم العثور على {len(working_proxies)} بروكسي شغال**\n\n"
    
    for proxy in working_proxies:
        warning = get_warning_emoji(
            proxy['ip_info']['isp'] if proxy['ip_info'] else "",
            proxy['ip_info']['asn'] if proxy['ip_info'] else ""
        )
        
        results_text += f"📍 `{proxy['ip']}:{proxy['port']}`\n"
        
        if proxy['ip_info']:
            results_text += f"🆔 ASN: {proxy['ip_info']['asn']} {warning}\n"
            results_text += f"🌐 ISP: {proxy['ip_info']['isp']}\n"
            results_text += f"🇺🇸 الدولة: {proxy['ip_info']['country']}\n"
        
        results_text += f"⚡ HTTP: {'✅' if proxy['http'] else '❌'} ({proxy['http_speed']}ms)\n"
        results_text += f"🔌 CONNECT: {'✅' if proxy['connect'] else '❌'} ({proxy['connect_speed']}ms)\n"
        results_text += "─" * 30 + "\n"
    
    # إرسال النتائج مع الأزرار
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton("🔙 العودة للرئيسية", callback_data="main_menu"))
    
    bot.send_message(
        chat_id,
        results_text,
        reply_markup=keyboard,
        parse_mode='Markdown'
    )

# التشغيل الرئيسي
if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات...")
    print("⚡ السرعة: 150ms")
    print("🔍 جاهز لاستقبال الطلبات...")
    bot.infinity_polling()
