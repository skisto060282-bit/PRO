import telebot
import requests
import socket
import time
import threading
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# توكن البوت - ضعيه هنا
bot = telebot.TeleBot("8468502888:AAGZl6YpdMDMenGthyWT_r-5NLaY_cCymGc")

# تخزين العمليات والنتائج
active_checks = {}
user_results = {}

def create_main_keyboard():
    """لوحة المفاتيح الرئيسية - زرين فقط"""
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    btn_start = KeyboardButton("/start")
    btn_stop = KeyboardButton("/stop")
    
    keyboard.add(btn_start, btn_stop)
    
    return keyboard

def create_check_keyboard():
    """لوحة فحص بعد الضغط على /start"""
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    btn_text = KeyboardButton("فحص نص")
    btn_url = KeyboardButton("فحص رابط")
    btn_back = KeyboardButton("/stop")
    
    keyboard.add(btn_text, btn_url)
    keyboard.add(btn_back)
    
    return keyboard

def optimal_speed_check(proxy_ip, proxy_port):
    """أفضل سرعة للنتائج الإيجابية - 800ms"""
    try:
        proxy_dict = {
            'http': f"http://{proxy_ip}:{proxy_port}",
            'https': f"https://{proxy_ip}:{proxy_port}"
        }
        
        results = {
            'ip': proxy_ip,
            'port': proxy_port,
            'http': '❌',
            'https': '❌', 
            'youtube': '❌',
            'connect': '❌',
            'speed': 0,
            'is_working': False
        }
        
        # فحص HTTP - 800ms
        try:
            start_time = time.time()
            response = requests.get('http://httpbin.org/ip', 
                                  proxies=proxy_dict, timeout=0.8)
            if response.status_code == 200:
                results['http'] = '✅'
            results['speed'] = int((time.time() - start_time) * 1000)
        except: 
            pass
        
        # فحص HTTPS - 800ms
        try:
            response = requests.get('https://httpbin.org/ip',
                                  proxies=proxy_dict, timeout=0.8)
            if response.status_code == 200:
                results['https'] = '✅'
        except: 
            pass
        
        # فحص YouTube - 800ms
        try:
            response = requests.get('https://www.youtube.com/',
                                  proxies=proxy_dict, timeout=0.8,
                                  headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})
            if response.status_code == 200:
                results['youtube'] = '✅'
        except: 
            pass
        
        # فحص CONNECT 80 - 800ms
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.8)
            result = sock.connect_ex((proxy_ip, 80))
            if result == 0:
                results['connect'] = '✅'
            sock.close()
        except: 
            pass
        
        # اعتبار البروكسي شغال إذا نجح في أي فحصين
        working_checks = sum(1 for check in [results['http'], results['https'], results['youtube'], results['connect']] if check == '✅')
        results['is_working'] = working_checks >= 2
        
        return results
        
    except Exception as e:
        print(f"Error in proxy check: {e}")
        return None

@bot.message_handler(commands=['start'])
def start_command(message):
    """عند الضغط على /start"""
    welcome_text = """
🎯 **بوت فحص البروكسيات السريع** ⚡

🚀 **المميزات:**
• فحص YouTube و HTTP/HTTPS
• سرعة فحص 800ms
• واجهة أزرار سهلة
• نتائج فورية

🎮 **اختر نوع الفحص:**
    """
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=create_check_keyboard()
    )

@bot.message_handler(commands=['stop'])
def stop_command(message):
    """عند الضغط على /stop - يتوقف ويعرض النتائج"""
    chat_id = message.chat.id
    
    # إيقاف أي عملية جارية
    if chat_id in active_checks:
        active_checks[chat_id] = False
    
    # عرض النتائج إذا كانت موجودة
    if chat_id in user_results and user_results[chat_id]:
        results = user_results[chat_id]
        show_final_results(chat_id, results)
    else:
        bot.send_message(
            chat_id,
            "🛑 تم إيقاف البحث\n❌ لا توجد نتائج لعرضها",
            reply_markup=create_main_keyboard()
        )

def show_final_results(chat_id, working_proxies):
    """عرض النتائج النهائية"""
    truly_working = [p for p in working_proxies if p.get('is_working', False)]
    
    if not truly_working:
        bot.send_message(
            chat_id,
            "❌ لم أعثر على أي بروكسيات شغالة",
            reply_markup=create_main_keyboard()
        )
        return
    
    results_text = f"📊 **نتائج الفحص السريع** ⚡\n\n"
    results_text += f"✅ **تم العثور على {len(truly_working)} بروكسي شغال**\n\n"
    
    for i, proxy in enumerate(truly_working[:20], 1):
        results_text += f"**{i}. {proxy['ip']}:{proxy['port']}**\n"
        results_text += f"   ┌ HTTP: {proxy['http']}\n"
        results_text += f"   ├ HTTPS: {proxy['https']}\n"
        results_text += f"   ├ YouTube: {proxy['youtube']}\n"
        results_text += f"   ├ CONNECT: {proxy['connect']}\n"
        results_text += f"   └ السرعة: {proxy['speed']}ms\n"
        results_text += "   ──────────────────────\n\n"
    
    if len(truly_working) > 20:
        results_text += f"📁 ... وعرض {len(truly_working) - 20} بروكسي إضافي\n\n"
    
    results_text += "🛑 **تم إيقاف البحث بناءً على طلبك**"
    
    bot.send_message(
        chat_id,
        results_text,
        reply_markup=create_main_keyboard(),
        parse_mode='Markdown'
    )
    
    # مسح النتائج بعد العرض
    if chat_id in user_results:
        del user_results[chat_id]

@bot.message_handler(func=lambda message: message.text == "فحص نص")
def check_text_handler(message):
    """عند الضغط على فحص نص"""
    msg = bot.send_message(
        message.chat.id, 
        "📝 أرسلي IP:Port أو قائمة بروكسيات\n\n**مثال:**\n`192.168.1.1:8080`\n`194.56.78.90:3128`",
        reply_markup=create_check_keyboard(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_text_check)

@bot.message_handler(func=lambda message: message.text == "فحص رابط")
def check_url_handler(message):
    """عند الضغط على فحص رابط"""
    msg = bot.send_message(
        message.chat.id,
        "🔗 أرسلي رابط ملف البروكسيات\n\n**مثال:**\n`https://example.com/proxies.txt`",
        reply_markup=create_check_keyboard(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_url_check)

def process_text_check(message):
    """معالجة فحص النص"""
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []
    
    # تحليل النص المدخل
    proxies = []
    for line in message.text.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                ip = parts[0].strip()
                port = parts[1].strip()
                port = ''.join(filter(str.isdigit, port))
                if port:
                    proxies.append((ip, port))
    
    if not proxies:
        bot.send_message(chat_id, "❌ لم أجد أي بروكسيات صالحة في النص")
        return
    
    if len(proxies) > 50:
        bot.send_message(chat_id, f"⚠️ سيتم فحص أول 50 بروكسي من أصل {len(proxies)}")
        proxies = proxies[:50]
    
    progress_msg = bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies)} بروكسي...\n⚡ السرعة: 800ms")
    
    # فحص جميع البروكسيات
    working_proxies = []
    checked_count = 0
    
    for ip, port in proxies:
        if not active_checks.get(chat_id, True):
            break
        
        checked_count += 1
        if checked_count % 10 == 0:
            try:
                bot.edit_message_text(
                    f"🔍 جاري الفحص... {checked_count}/{len(proxies)}\n✅ وجدنا {len(working_proxies)} بروكسي شغال",
                    chat_id,
                    progress_msg.message_id
                )
            except:
                pass
        
        result = optimal_speed_check(ip, port)
        if result and result['is_working']:
            working_proxies.append(result)
            user_results[chat_id] = working_proxies
        
        time.sleep(0.1)  # تقليل الضغط
    
    # إذا لم يتم إيقاف البحث، عرض النتائج تلقائياً
    if active_checks.get(chat_id, True):
        show_final_results(chat_id, working_proxies)
        active_checks[chat_id] = False
    else:
        bot.send_message(
            chat_id,
            f"🛑 تم إيقاف البحث\n✅ تم فحص {checked_count} بروكسي - وجدنا {len(working_proxies)} شغال",
            reply_markup=create_main_keyboard()
        )

def process_url_check(message):
    """معالجة فحص الرابط"""
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []
    
    try:
        bot.send_message(chat_id, "⏬ جاري تحميل البروكسيات من الرابط...")
        
        response = requests.get(message.text, timeout=10)
        content = response.text
        
        proxies = []
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line and '.' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    port = parts[1].strip()
                    port = ''.join(filter(str.isdigit, port))
                    if port and ip.replace('.', '').isdigit():
                        proxies.append((ip, port))
        
        if not proxies:
            bot.send_message(chat_id, "❌ لم أجد أي بروكسيات في الرابط")
            return
        
        if len(proxies) > 50:
            bot.send_message(chat_id, f"⚠️ سيتم فحص أول 50 بروكسي من أصل {len(proxies)}")
            proxies = proxies[:50]
        
        progress_msg = bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies)} بروكسي...\n⚡ السرعة: 800ms")
        
        working_proxies = []
        checked_count = 0
        
        for ip, port in proxies:
            if not active_checks.get(chat_id, True):
                break
            
            checked_count += 1
            if checked_count % 10 == 0:
                try:
                    bot.edit_message_text(
                        f"🔍 جاري الفحص... {checked_count}/{len(proxies)}\n✅ وجدنا {len(working_proxies)} بروكسي شغال",
                        chat_id,
                        progress_msg.message_id
                    )
                except:
                    pass
            
            result = optimal_speed_check(ip, port)
            if result and result['is_working']:
                working_proxies.append(result)
                user_results[chat_id] = working_proxies
            
            time.sleep(0.1)
        
        # إذا لم يتم إيقاف البحث، عرض النتائج تلقائياً
        if active_checks.get(chat_id, True):
            show_final_results(chat_id, working_proxies)
            active_checks[chat_id] = False
        else:
            bot.send_message(
                chat_id,
                f"🛑 تم إيقاف البحث\n✅ تم فحص {checked_count} بروكسي - وجدنا {len(working_proxies)} شغال",
                reply_markup=create_main_keyboard()
            )
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في تحميل الرابط: {str(e)}")

# تشغيل البوت
if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات السريع...")
    print("⚡ السرعة: 800ms - YouTube/HTTP/HTTPS/CONNECT")
    print("🎯 البوت جاهز لاستقبال الطلبات...")
    bot.infinity_polling()