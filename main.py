import telebot
import requests
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import json
import random
import re
import asyncio
import logging

# ---------- إعدادات السكريبت ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ssh_bot")

# إعدادات SSH
SSH_API_URL = "https://painel.meowssh.shop:5000/test_ssh_public"
SSH_PAYLOAD = {"store_owner_id": 1}
SSH_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# إعدادات البوت
TOKEN = '8468502888:AAGZl6YpdMDMenGthyWT_r-5NLaY_cCymGc'
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

criticalASN = 'AS396982'
defaultPorts = [80, 443, 8080, 8443, 3128]
MAX_FAST_PORTS = 20
MAX_DISPLAY_OPEN = 20
MAX_IPS_PER_MSG = 300
MAX_FILE_IPS = 1000
HTTP_TIMEOUT = 1
SCAN_CONCURRENCY = 200
TOTAL_PORTS = 65535
UPDATE_INTERVAL = 3

# إدارة العمليات
waitingFull = set()
file_upload_mode = set()
user_operations = {}
waiting_proxy_url = set()
custom_youtube_urls = {}
waiting_custom_url = set()

# ---------------- دوال مساعدة ----------------
def validate_ip(ip):
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            p = int(part)
            if not 0 <= p <= 255:
                return False
        return True
    except:
        return False

def create_progress_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    empty = length - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}]"

def start_operation(chat_id, operation_type):
    user_operations[chat_id] = {'stop': False, 'type': operation_type}

def end_operation(chat_id):
    if chat_id in user_operations:
        del user_operations[chat_id]

def stop_user_operations(chat_id):
    if chat_id in user_operations:
        user_operations[chat_id]['stop'] = True
    file_upload_mode.discard(chat_id)
    waitingFull.discard(chat_id)
    waiting_proxy_url.discard(chat_id)
    waiting_custom_url.discard(chat_id)

def should_stop(chat_id):
    if chat_id in user_operations:
        return user_operations[chat_id].get('stop', False)
    return False

def format_custom_url(url_input):
    """تحويل الروابط المختصرة إلى كاملة"""
    url_input = url_input.strip().lower()
    
    if not url_input.startswith(('http://', 'https://')):
        url_input = 'https://' + url_input
        
    if not url_input.startswith('https://www.'):
        popular_domains = ['youtube.com', 'facebook.com', 'twitter.com', 'instagram.com', 
                          'netflix.com', 'tiktok.com', 'whatsapp.com', 'telegram.org']
        for domain in popular_domains:
            if domain in url_input:
                url_input = url_input.replace('https://', 'https://www.')
                break
                
    return url_input

# ---------------- دوال شبكات / API ----------------
def query_ip_api(ip):
    """استعلام عن معلومات IP"""
    try:
        r = requests.get(
            f'http://ip-api.com/json/{ip}?fields=status,message,query,country,regionName,isp,as,org',
            timeout=5
        )
        return r.json()
    except Exception as e:
        logger.debug("query_ip_api error for %s: %s", ip, e)
        return None

def check_connect_protocol(ip, port, target_host="www.youtube.com", target_port=443):
    """فحص بروتوكول CONNECT للبروكسي"""
    try:
        sock = socket.create_connection((ip, port), timeout=10)
        connect_request = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n"
        sock.send(connect_request.encode())
        response = sock.recv(4096).decode()
        sock.close()
        return '200' in response or 'Connection established' in response
    except Exception as e:
        logger.debug(f"CONNECT check failed for {ip}:{port} - {e}")
        return False

def check_http_protocol(ip, port, protocol='http'):
    """فحص بروتوكول HTTP/HTTPS بدقة"""
    try:
        test_urls = {
            'http': f'http://{ip}:{port}',
            'https': f'https://{ip}:{port}'
        }
        
        response = requests.get(
            test_urls[protocol], 
            timeout=HTTP_TIMEOUT,
            verify=False,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        )
        return response.status_code < 400
    except:
        return False

def check_all_protocols(ip, port):
    """فحص جميع البروتوكولات على المنفذ"""
    results = {
        'http': False,
        'https': False, 
        'connect': False
    }
    
    results['http'] = check_http_protocol(ip, port, 'http')
    results['https'] = check_http_protocol(ip, port, 'https')
    results['connect'] = check_connect_protocol(ip, port)
    
    return results

def check_youtube_proxy(proxy_ip, proxy_port, protocol='http', custom_url=None):
    """فحص متقدم لإمكانية الوصول لليوتيوب عبر البروكسي مع دعم الروابط المخصصة"""
    try:
        proxies = {
            'http': f'{protocol}://{proxy_ip}:{proxy_port}',
            'https': f'{protocol}://{proxy_ip}:{proxy_port}'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        target_url = custom_url if custom_url else 'https://www.youtube.com/'
        
        response = requests.get(
            target_url, 
            proxies=proxies, 
            timeout=15,
            headers=headers,
            verify=False
        )
        
        if custom_url:
            return response.status_code == 200
        else:
            youtube_access = (
                response.status_code == 200 and 
                'youtube' in response.text.lower() and
                ('watch' in response.text.lower() or 'video' in response.text.lower())
            )
            return youtube_access
        
    except Exception as e:
        logger.debug(f"YouTube proxy check failed for {proxy_ip}:{proxy_port} - {e}")
        return False

# ---------------- دوال SSH ----------------
def get_ssh_account_sync():
    """استدعاء API جلب SSH"""
    try:
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

def show_ssh_menu(chat_id):
    ssh_message = """
🔷 **SSH Account Generator**

🚀 **مولد حسابات SSH مجانية**

📝 **الأوامر المتاحة:**
• /ssh - لاستخراج حساب SSH جديد

⚡ **انقر على الزر أدناه لاستخراج حساب SSH:**
"""
    inline_kb = telebot.types.InlineKeyboardMarkup()
    inline_kb.row(telebot.types.InlineKeyboardButton("🔑 استخراج SSH", callback_data='ssh_generate'))
    inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع", callback_data='back_main'))
    bot.send_message(chat_id, ssh_message, reply_markup=inline_kb)

def handle_ssh_generate(chat_id):
    """تشغيل استدعاء SSH في Thread لتجنب تعليق البوت"""
    def job():
        bot.send_message(chat_id, "🔑 جاري استخراج حساب SSH...")
        result = get_ssh_account_sync()
        bot.send_message(chat_id, result)
        inline_kb = telebot.types.InlineKeyboardMarkup()
        inline_kb.row(telebot.types.InlineKeyboardButton("🔑 استخراج آخر", callback_data='ssh_generate'))
        inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data='back_main'))
        bot.send_message(chat_id, "🔄 اختر الإجراء التالي:", reply_markup=inline_kb)
    threading.Thread(target=job, daemon=True).start()

# ---------------- الفحص السريع والمحسّن ----------------
def perform_quick_scan(chat_id, ip, ports=None, scan_type="سريع", show_failures=False):
    if ports is None:
        ports = defaultPorts.copy()
    try:
        ip_data = query_ip_api(ip)
        if not ip_data or ip_data.get('status') != 'success':
            return False
            
        as_raw = ip_data.get('as', 'N/A')
        as_code = as_raw.split()[0] if 'AS' in as_raw else 'N/A'
        is_critical = as_code == criticalASN
        results = []
        is_active = False
        youtube_working = False
        working_protocols = []
        
        custom_url = custom_youtube_urls.get(chat_id)
        target_name = "الرابط المخصص" if custom_url else "يوتيوب"
        
        for port in ports:
            if should_stop(chat_id):
                break
                
            protocol_results = check_all_protocols(ip, port)
            
            port_active = any(protocol_results.values())
            if port_active:
                is_active = True
                protocol_info = []
                
                if protocol_results['http']:
                    protocol_info.append("HTTP")
                    working_protocols.append(f"HTTP:{port}")
                if protocol_results['https']:
                    protocol_info.append("HTTPS") 
                    working_protocols.append(f"HTTPS:{port}")
                if protocol_results['connect']:
                    protocol_info.append("CONNECT")
                    working_protocols.append(f"CONNECT:{port}")
                    
                # فحص يوتيوب على البروتوكولات الناجحة
                youtube_results = []
                for protocol in ['http', 'https']:
                    if protocol_results[protocol]:
                        target_status = check_youtube_proxy(ip, port, protocol, custom_url)
                        youtube_status = "✅" if target_status else "❌"
                        if target_status:
                            youtube_working = True
                        youtube_results.append(f"✅ {protocol.upper()} - {target_name} {youtube_status}")
                
                if youtube_results:
                    results.extend(youtube_results)
                            
        if not is_active:
            return False
            
        as_badge = '🔴' if is_critical else '⚪'
        country_flag = "🇺🇸" if ip_data.get('country') == 'United States' else "🌍"
        
        text_out = (
            f"📍 **{ip_data.get('query')}** | {country_flag} {ip_data.get('country')}\n"
            f"🏢 {ip_data.get('isp', 'N/A')} {as_badge}\n\n"
            f"🎯 **البروتوكولات النشطة:**\n" +
            '\n'.join(results)
        )
        
        bot.send_message(chat_id, text_out, parse_mode="Markdown")
        
        if youtube_working:
            alert_target = custom_url if custom_url else "يوتيوب"
            alert_message = f"""
🚨 **بروكسي يعمل مع {alert_target}**

📡 **تفاصيل البروكسي:**
• 🌐 IP: `{ip_data.get("query")}`
• 🚪 المنافذ النشطة: {len(working_protocols)}
• 📡 البروتوكولات: {', '.join(working_protocols)}
• 🌍 Country: `{ip_data.get("country")}`
• 🏢 ISP: `{ip_data.get("isp", "N/A")}`

{'🔗 **الرابط المخصص:** ' + custom_url if custom_url else '⚡ **الهدف:** يوتيوب الافتراضي'}

🎉 **بروكسي نشط!**
"""
            bot.send_message(chat_id, alert_message, parse_mode="Markdown")
            
        if is_critical:
            asn_alert = f"🔥🔥🔥 Google LLC AS396982\n📍 {ip_data.get('query')}:{ports[0] if ports else '?'}"
            bot.send_message(chat_id, asn_alert)
            
        return is_active
        
    except Exception as e:
        logger.debug("perform_quick_scan error: %s", e)
        return False

# ---------------- الفحص الشامل ----------------
def perform_full_scan(chat_id, ip):
    start_operation(chat_id, 'full_scan')
    try:
        status_msg = bot.send_message(chat_id, 
            f'🔍 بدء الفحص الشامل TCP على {ip}...\n'
            f'🎯 **سيتم فحص يوتيوب على جميع المنافذ المفتوحة تلقائياً**\n'
            f'⏳ الرجاء الانتظار — الفحص جاري الآن.'
        )
        open_ports = []
        youtube_ports = []
        scanned_ports = 0
        start_time = time.time()
        stop_requested = False

        def updater():
            last_update = time.time()
            while scanned_ports < TOTAL_PORTS and not should_stop(chat_id):
                current_time = time.time()
                if current_time - last_update >= UPDATE_INTERVAL:
                    remaining = TOTAL_PORTS - scanned_ports
                    preview = ', '.join(map(str, sorted(open_ports)[:MAX_DISPLAY_OPEN]))
                    more = f', ...(+{len(open_ports)-MAX_DISPLAY_OPEN})' if len(open_ports) > MAX_DISPLAY_OPEN else ''
                    
                    youtube_info = f'\n🎯 يوتيوب: {len(youtube_ports)} منفذ' if youtube_ports else ''
                    
                    txt = (
                        f'🔎 الفحص الشامل TCP على {ip}\n'
                        f'🎯 **فحص يوتيوب مفعل على جميع المنافذ**\n\n'
                        f'Scanned: {scanned_ports}/{TOTAL_PORTS}\n'
                        f'Remaining: {remaining}\n'
                        f'Open ports: {len(open_ports)}{youtube_info}\n'
                    )
                    if open_ports:
                        txt += f'Some open: {preview}{more}'
                    else:
                        txt += 'No open ports found so far.'
                    try:
                        bot.edit_message_text(txt, chat_id, status_msg.message_id)
                    except:
                        pass
                    last_update = current_time
                time.sleep(1)

        threading.Thread(target=updater, daemon=True).start()

        def scan_port(p):
            nonlocal scanned_ports
            if not should_stop(chat_id):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((ip, p))
                sock.close()
                if result == 0:
                    open_ports.append(p)
                    custom_url = custom_youtube_urls.get(chat_id)
                    protocol = 'https' if p in [443, 8443] else 'http'
                    if check_youtube_proxy(ip, p, protocol, custom_url):
                        youtube_ports.append(p)
            scanned_ports += 1

        with ThreadPoolExecutor(max_workers=SCAN_CONCURRENCY) as executor:
            batch_size = 2000
            for start in range(1, TOTAL_PORTS + 1, batch_size):
                if should_stop(chat_id):
                    stop_requested = True
                    break
                end = min(start + batch_size - 1, TOTAL_PORTS)
                list(executor.map(scan_port, range(start, end + 1)))

        open_ports.sort()
        youtube_ports.sort()
        total_time = time.time() - start_time

        if stop_requested:
            final = (
                f'⏹️ **تم إيقاف الفحص الشامل**\n\n'
                f'📊 **النتائج حتى الآن:**\n'
                f'⏱️ الوقت: {total_time:.2f} ثانية\n'
                f'Scanned: {scanned_ports}/{TOTAL_PORTS}\n'
                f'Open ports: {len(open_ports)}\n'
                f'🎯 يوتيوب: {len(youtube_ports)} منفذ\n'
            )
        else:
            final = (
                f'✅ **انتهى الفحص الشامل TCP** على {ip}\n\n'
                f'⏱️ الوقت: {total_time:.2f} ثانية\n'
                f'Scanned: {scanned_ports}/{TOTAL_PORTS}\n'
                f'Open ports: {len(open_ports)}\n'
                f'🎯 يوتيوب: {len(youtube_ports)} منفذ\n'
            )

        if open_ports:
            final += f'\n🔓 **المنافذ المفتوحة:**\n'
            final += ', '.join(map(str, open_ports[:MAX_DISPLAY_OPEN]))
            if len(open_ports) > MAX_DISPLAY_OPEN:
                final += f', ...(+{len(open_ports)-MAX_DISPLAY_OPEN})'
                
        if youtube_ports:
            final += f'\n\n🎯 **المنافذ التي تعمل مع يوتيوب:**\n'
            final += ', '.join(map(str, youtube_ports[:10]))
            if len(youtube_ports) > 10:
                final += f', ...(+{len(youtube_ports)-10})'
            
            custom_url = custom_youtube_urls.get(chat_id)
            target_name = "الرابط المخصص" if custom_url else "يوتيوب"
            youtube_alert = f"""
🚨 **اكتشاف هام في الفحص الشامل!**

🎯 **تم العثور على {len(youtube_ports)} منفذ يعمل مع {target_name}**

🌐 **الـIP:** `{ip}`
📊 **إجمالي المنافذ المفتوحة:** {len(open_ports)}
🎯 **منافذ ناجحة:** {len(youtube_ports)}

🔧 **أول 10 منافذ تعمل:**
{', '.join(map(str, youtube_ports[:10]))}

⚡ **يمكن استخدام هذه المنافذ لتجاوز الحظر!**
"""
            bot.send_message(chat_id, youtube_alert, parse_mode="Markdown")
        else:
            final += '\n\n❌ **لا توجد منافذ تعمل مع يوتيوب**'

        try:
            bot.edit_message_text(final, chat_id, status_msg.message_id)
        except:
            bot.send_message(chat_id, final)

    except Exception as e:
        bot.send_message(chat_id, f'❌ خطأ في الفحص الشامل: {str(e)}')
    finally:
        end_operation(chat_id)

# ---------------- معالجة الملفات ----------------
def parse_file_content(file_content):
    try:
        lines = file_content.decode('utf-8').split('\n')
    except:
        lines = file_content.decode('latin-1').split('\n')
    ips = []
    for line in lines:
        if len(ips) >= MAX_FILE_IPS:
            break
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            parts = line.split(':')
            ip = parts[0].strip()
            if validate_ip(ip):
                try:
                    port = int(parts[1].strip())
                    if 1 <= port <= 65535:
                        ips.append({'ip': ip, 'ports': [port]})
                except:
                    ips.append({'ip': ip, 'ports': defaultPorts.copy()})
        else:
            if validate_ip(line):
                ips.append({'ip': line, 'ports': defaultPorts.copy()})
    return ips

def process_file_scan(chat_id, file_content):
    start_operation(chat_id, 'file_scan')
    try:
        ips_to_scan = parse_file_content(file_content)
        if not ips_to_scan:
            bot.send_message(chat_id, "❌ لم يتم العثور على IPs صحيحة في الملف.")
            end_operation(chat_id)
            return
            
        total_ips = len(ips_to_scan)
        progress_msg = bot.send_message(
            chat_id,
            f"📁 **بدء فحص الملف**\n\n"
            f"🎯 **فحص يوتيوب مفعل**\n\n"
            f"🔢 إجمالي الـIPs: {total_ips}\n"
            f"📊 تم فحص: 0/{total_ips}\n"
            f"🟢 النشطة: 0\n"
            f"⏳ الباقي: {total_ips}\n"
            f"📈 النسبة: 0%\n"
            f"[░░░░░░░░░░░░░░░░░░░░]"
        )
        scanned_count = 0
        active_count = 0
        last_update_time = time.time()
        
        for i, item in enumerate(ips_to_scan):
            if should_stop(chat_id):
                try:
                    bot.delete_message(chat_id, progress_msg.message_id)
                except:
                    pass
                summary = f"""
⏹️ **تم إيقاف فحص الملف**

📊 **النتائج حتى الآن:**
• 🔢 تم فحص: {scanned_count}/{total_ips}
• 🟢 النشطة: {active_count}
• 📈 نسبة النجاح: {(active_count/scanned_count)*100:.1f}% إذا كان {scanned_count} > 0 else 0}%
"""
                bot.send_message(chat_id, summary)
                return
                
            ip, ports = item['ip'], item['ports']
            is_active = perform_quick_scan(chat_id, ip, ports, f"ملف", show_failures=False)
            scanned_count = i + 1
            
            if is_active:
                active_count += 1
                
            current_time = time.time()
            if current_time - last_update_time >= 2 or scanned_count == total_ips:
                percentage = (scanned_count / total_ips) * 100
                remaining = total_ips - scanned_count
                progress_bar = create_progress_bar(percentage, 20)
                try:
                    bot.edit_message_text(
                        f"📁 **جاري فحص الملف**\n\n"
                        f"🎯 **فحص يوتيوب مفعل**\n\n"
                        f"🔢 الإجمالي: {total_ips} IP\n"
                        f"📊 تم فحص: {scanned_count}/{total_ips}\n"
                        f"🟢 النشطة: {active_count}\n"
                        f"⏳ الباقي: {remaining}\n"
                        f"📈 النسبة: {percentage:.1f}%\n"
                        f"{progress_bar}",
                        chat_id,
                        progress_msg.message_id
                    )
                    last_update_time = current_time
                except:
                    pass
                    
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
            
        summary = f"""
✅ **تم الانتهاء من فحص الملف**

🎯 **فحص يوتيوب كان مفعلاً على جميع الـIPs**

📊 **النتائج النهائية:**
• 🔢 إجمالي الـIPs: {total_ips}
• 🟢 النشطة: {active_count}
• 🔴 غير النشطة: {total_ips - active_count}
• 📈 نسبة النجاح: {(active_count/total_ips)*100:.1f}%

💡 **تم إرسال تنبيهات منفصلة للبروكسيات التي تعمل مع يوتيوب**
"""
        bot.send_message(chat_id, summary)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في معالجة الملف: {str(e)}")
    finally:
        end_operation(chat_id)

# ---------------- الفحص السريع الجماعي ----------------
def process_bulk_quick_scan(chat_id, ip_list):
    total_ips = len(ip_list)
    progress_msg = bot.send_message(
        chat_id,
        f"⚡ **بدء الفحص السريع**\n\n"
        f"🔢 إجمالي الـIPs: {total_ips}\n"
        f"📊 تم فحص: 0/{total_ips}\n"
        f"🟢 النشطة: 0\n"
        f"⏳ الباقي: {total_ips}\n"
        f"📈 النسبة: 0%\n"
        f"[░░░░░░░░░░░░░░░░░░░░]"
    )
    active_count = 0
    scanned_count = 0
    last_update_time = time.time()
    for i, item in enumerate(ip_list):
        if should_stop(chat_id):
            try:
                bot.delete_message(chat_id, progress_msg.message_id)
            except:
                pass
            summary = f"""
⏹️ **تم إيقاف الفحص السريع**

📊 **النتائج حتى الآن:**
• 🔢 تم فحص: {scanned_count}/{total_ips}
• 🟢 النشطة: {active_count}
• 📈 نسبة النجاح: {(active_count/scanned_count)*100:.1f}% إذا كان {scanned_count} > 0 else 0}%
"""
            bot.send_message(chat_id, summary)
            return active_count
            
        ip, ports = item['ip'], item['ports']
        is_active = perform_quick_scan(chat_id, ip, ports, f"سريع", show_failures=False)
        scanned_count = i + 1
        if is_active:
            active_count += 1
            
        current_time = time.time()
        if current_time - last_update_time >= 2 or scanned_count == total_ips:
            percentage = (scanned_count / total_ips) * 100
            remaining = total_ips - scanned_count
            progress_bar = create_progress_bar(percentage, 20)
            try:
                bot.edit_message_text(
                    f"⚡ **جاري الفحص السريع**\n\n"
                    f"🔢 الإجمالي: {total_ips} IP\n"
                    f"📊 تم فحص: {scanned_count}/{total_ips}\n"
                    f"🟢 النشطة: {active_count}\n"
                    f"⏳ الباقي: {remaining}\n"
                    f"📈 النسبة: {percentage:.1f}%\n"
                    f"{progress_bar}",
                    chat_id,
                    progress_msg.message_id
                )
                last_update_time = current_time
            except:
                try:
                    bot.delete_message(chat_id, progress_msg.message_id)
                except:
                    pass
                progress_msg = bot.send_message(
                    chat_id,
                    f"⚡ **جاري الفحص السريع**\n\n"
                    f"🔢 الإجمالي: {total_ips} IP\n"
                    f"📊 تم فحص: {scanned_count}/{total_ips}\n"
                    f"🟢 النشطة: {active_count}\n"
                    f"⏳ الباقي: {remaining}\n"
                    f"📈 النسبة: {percentage:.1f}%\n"
                    f"{progress_bar}"
                )
                last_update_time = current_time
        if scanned_count % 5 == 0:
            time.sleep(0.02)
    try:
        bot.delete_message(chat_id, progress_msg.message_id)
    except:
        pass
    return active_count

# ---------------- جلب بروكسيات من رابط مخصص ----------------
def fetch_proxies_from_url(url):
    """جلب البروكسيات من رابط مخصص"""
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            proxies = []
            lines = r.text.splitlines()
            for line in lines:
                line = line.strip()
                if ':' in line and '.' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        port = parts[1].strip()
                        if validate_ip(ip) and port.isdigit() and 1 <= int(port) <= 65535:
                            proxies.append(f"{ip}:{port}")
            return list(set(proxies))
    except Exception as e:
        logger.warning("fetch_proxies_from_url error for %s: %s", url, e)
    return []

def process_custom_proxies_scan(chat_id, custom_url):
    """معالجة فحص بروكسيات من رابط مخصص - جميع البروكسيات"""
    start_operation(chat_id, 'custom_proxies_scan')
    try:
        progress_msg = bot.send_message(chat_id, "🔍 جاري جلب البروكسيات من الرابط...")
        
        proxies = fetch_proxies_from_url(custom_url)
        if not proxies:
            bot.send_message(chat_id, "❌ لم يتم العثور على بروكسيات في الرابط المخصص")
            end_operation(chat_id)
            return []
            
        all_proxies = proxies
        
        proxy_text = f"🌐 **تم جلب {len(all_proxies)} بروكسي**\n\n"
        for proxy in all_proxies[:30]:
            proxy_text += f"`{proxy}`\n"
        
        if len(all_proxies) > 30:
            proxy_text += f"\n📊 ... وإجمالي {len(all_proxies)} بروكسي"
        
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
            
        bot.send_message(chat_id, proxy_text, parse_mode="Markdown")
        
        ip_list = []
        for proxy in all_proxies:
            parts = proxy.split(':')
            if len(parts) >= 2:
                ip = parts[0]
                port = parts[1]
                if validate_ip(ip):
                    ip_list.append({'ip': ip, 'ports': [int(port)]})
                    
        if not ip_list:
            bot.send_message(chat_id, "❌ لا توجد بروكسيات صالحة للفحص")
            end_operation(chat_id)
            return []
            
        bot.send_message(chat_id, f"🚀 بدء فحص {len(ip_list)} بروكسي...")
        active_count = process_bulk_quick_scan(chat_id, ip_list)
        
        summary = (
            f"✅ **تم الانتهاء من فحص البروكسيات**\n\n"
            f"📊 **النتائج النهائية:**\n"
            f"• 🔢 الإجمالي: {len(ip_list)} بروكسي\n"
            f"• 🟢 النشطة: {active_count}\n"
            f"• 📈 نسبة النجاح: {(active_count/len(ip_list))*100:.1f}%"
        )
        bot.send_message(chat_id, summary)
        return all_proxies
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في فحص البروكسيات: {str(e)}")
        return []
    finally:
        end_operation(chat_id)

# ---------------- أوامر البوت والمعالجات ----------------
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    stop_user_operations(chat_id)
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.add('/start', '/stop', '/ssh')
    bot.send_message(chat_id, "👋 أهلاً! اختر نوع الفحص:", reply_markup=kb)
    
    current_custom_url = custom_youtube_urls.get(chat_id, 'غير محدد')
    menu_text = f"""
🎯 **بوت فحص البروكسيات المتقدم**

⚡ **المميزات الجديدة:**
• فحص HTTP/HTTPS/CONNECT
• فحص يوتيوب تلقائي
• 🔗 **رابط مخصص: {current_custom_url}**

📊 **اختر نوع الفحص:**
"""
    
    inline_kb = telebot.types.InlineKeyboardMarkup()
    inline_kb.row(
        telebot.types.InlineKeyboardButton("⚡ فحص سريع", callback_data='fx_fast'),
        telebot.types.InlineKeyboardButton("🔍 فحص شامل", callback_data='fx_full')
    )
    inline_kb.row(
        telebot.types.InlineKeyboardButton("📁 فحص ملف", callback_data='upload_file'),
        telebot.types.InlineKeyboardButton("🌐 جلب بروكسيات", callback_data='fetch_proxies')
    )
    inline_kb.row(
        telebot.types.InlineKeyboardButton("🔗 إعداد رابط مخصص", callback_data='custom_youtube_url'),
        telebot.types.InlineKeyboardButton("🔑 استخراج SSH", callback_data='ssh_menu')
    )
    
    if chat_id in custom_youtube_urls:
        inline_kb.row(
            telebot.types.InlineKeyboardButton("🗑️ مسح الرابط المخصص", callback_data='clear_custom_url')
        )
    
    bot.send_message(chat_id, menu_text, reply_markup=inline_kb)

@bot.message_handler(commands=['ssh'])
def ssh_command(message):
    chat_id = message.chat.id
    show_ssh_menu(chat_id)

@bot.message_handler(commands=['stop'])
def stop_message(message):
    chat_id = message.chat.id
    stop_user_operations(chat_id)
    bot.send_message(chat_id, "⏹️ تم إيقاف جميع العمليات الجارية.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    if call.data == 'fx_fast':
        bot.send_message(chat_id,
            '⚡ **الفحص السريع**\n\n'
            '🎯 **سيتم فحص يوتيوب تلقائياً على جميع البروكسيات**\n\n'
            'أرسل الآن IP أو قائمة IPs\n\n'
            '📝 **التنسيقات:**\n'
            '• IP:Port\n'
            '• IP:Port1,Port2,Port3\n'
            '• IP فقط\n\n'
            '🔔 **سيصلك تنبيه لكل بروكسي يعمل مع يوتيوب!**'
        )
    elif call.data == 'fx_full':
        waitingFull.add(chat_id)
        bot.send_message(chat_id, 
            '🔍 **الفحص الشامل**\n\n'
            '🎯 **سيتم فحص يوتيوب تلقائياً على جميع المنافذ المفتوحة**\n\n'
            'أرسل الآن IP للفحص الشامل TCP 1–65535.\n\n'
            '⚡ **مميزات هذه النسخة:**\n'
            '• فحص جميع المنافذ\n'
            '• فحص يوتيوب تلقائي\n'
            '• تقرير مفصل عن منافذ يوتيوب\n'
            '• تنبيهات فورية'
        )
    elif call.data == 'ssh_menu':
        show_ssh_menu(chat_id)
    elif call.data == 'ssh_generate':
        handle_ssh_generate(chat_id)
    elif call.data == 'back_main':
        start_message(call.message)
    elif call.data == 'upload_file':
        file_upload_mode.add(chat_id)
        bot.send_message(chat_id,
            '📁 **رفع ملف txt**\n\n'
            'ارفع ملف txt يحتوي على IPs (حتى 1000 IP)\n\n'
            '📝 **التنسيقات المدعومة:**\n'
            '• IP:Port\n'
            '• IP فقط\n'
            '• سطر واحد لكل IP\n\n'
            '📎 **ارفع الملف الآن...**\n\n'
            '⚡ **الآن بسرعة فائقة مع العداد الحي**'
        )
    elif call.data == 'fetch_proxies':
        inline_kb = telebot.types.InlineKeyboardMarkup()
        inline_kb.row(
            telebot.types.InlineKeyboardButton("📝 رابط مخصص", callback_data='fetch_custom_proxies')
        )
        inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع", callback_data='back_main'))
        bot.send_message(chat_id,
            '🌐 **جلب بروكسيات**\n\n'
            '🔍 سأجلب جميع البروكسيات من الرابط وأفحصها\n\n'
            '📥 أدخل رابط البروكسيات:',
            reply_markup=inline_kb
        )
    elif call.data == 'fetch_custom_proxies':
        waiting_proxy_url.add(chat_id)
        bot.send_message(chat_id,
            '📝 **أدخل رابط البروكسيات**\n\n'
            '🌐 مثال:\n'
            'https://raw.githubusercontent.com/user/proxy-list/master/http.txt\n\n'
            '📥 سأجلب جميع البروكسيات من هذا الرابط وأفحصها'
        )
    elif call.data == 'custom_youtube_url':
        waiting_custom_url.add(chat_id)
        bot.send_message(chat_id,
            '🌐 **إعداد رابط مخصص لفحص يوتيوب**\n\n'
            '🔗 **أرسل الرابط الذي تريدين فحصه عبر البروكسي:**\n\n'
            '📝 **أمثلة:**\n'
            '• youtube.com\n'
            '• facebook.com\n' 
            '• netflix.com\n'
            '• أو أي رابط آخر تريدين فحصه\n\n'
            '⚡ **سيتم فحص هذا الرابط عبر جميع البروكسيات**\n'
            '🎯 **وستصلك تنبيهات عندما يعمل البروكسي مع هذا الرابط**'
        )
    elif call.data == 'clear_custom_url':
        if chat_id in custom_youtube_urls:
            del custom_youtube_urls[chat_id]
        bot.send_message(chat_id, '✅ تم مسح الرابط المخصص، سيتم استخدام يوتيوب الافتراضي')
        start_message(call.message)

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    if chat_id not in file_upload_mode:
        return
    file_upload_mode.discard(chat_id)
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(chat_id, "❌ يرجى رفع ملف txt فقط.")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot.send_message(chat_id, "📁 جاري معالجة الملف...")
        threading.Thread(target=process_file_scan, args=(chat_id, downloaded_file), daemon=True).start()
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في تحميل الملف: {str(e)}")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    if not text or text.startswith('/'):
        return
        
    if chat_id in waitingFull:
        waitingFull.remove(chat_id)
        ip = text
        threading.Thread(target=perform_full_scan, args=(chat_id, ip), daemon=True).start()
        return
        
    if chat_id in waiting_proxy_url:
        waiting_proxy_url.discard(chat_id)
        if text.startswith('http'):
            bot.send_message(chat_id, f"📥 جاري جلب البروكسيات من الرابط...")
            threading.Thread(target=process_custom_proxies_scan, args=(chat_id, text), daemon=True).start()
        else:
            bot.send_message(chat_id, "❌ الرابط غير صالح. يرجى إدخال رابط يبدأ بـ http أو https")
        return
        
    if chat_id in waiting_custom_url:
        waiting_custom_url.discard(chat_id)
        if text.startswith('http') or '.' in text:
            formatted_url = format_custom_url(text)
            custom_youtube_urls[chat_id] = formatted_url
            bot.send_message(chat_id, 
                f'✅ **تم تعيين الرابط المخصص بنجاح!**\n\n'
                f'🔗 {formatted_url}\n\n'
                f'🎯 الآن سيتم فحص هذا الرابط عبر جميع البروكسيات\n'
                f'🚨 وستصلك تنبيهات عندما يعمل أي بروكسي مع هذا الرابط'
            )
            start_message(message)
        else:
            bot.send_message(chat_id, "❌ الرابط غير صالح. يرجى إدخال رابط صحيح")
        return
        
    raw_ips = [t.strip() for t in text.replace(',', '\n').split('\n') if t.strip()]
    ip_list = []
    for ip_text in raw_ips[:MAX_IPS_PER_MSG]:
        parts = ip_text.split(':')
        ip = parts[0].strip()
        if not validate_ip(ip):
            continue
        if len(parts) > 1 and parts[1].strip():
            try:
                ports = list(map(int, parts[1].split(',')))
                ports = [p for p in ports if 1 <= p <= 65535]
                if len(ports) > MAX_FAST_PORTS:
                    ports = ports[:MAX_FAST_PORTS]
            except:
                ports = defaultPorts.copy()
        else:
            ports = defaultPorts.copy()
        ip_list.append({'ip': ip, 'ports': ports})
    if not ip_list:
        bot.send_message(chat_id, "❌ لم يتم التعرف على أي IP صالح في النص.")
        return
    if len(ip_list) >= 1:
        if len(ip_list) > 1:
            bot.send_message(chat_id, f"🔍 بدء فحص {len(ip_list)} IP...")
        else:
            bot.send_message(chat_id, f"🔍 جاري فحص IP...")
        threading.Thread(target=lambda: process_bulk_quick_scan(chat_id, ip_list), daemon=True).start()

# ---------------- تشغيل البوت ----------------
if __name__ == "__main__":
    print("🚀 بدء تشغيل البوت المحسن...")
    print(f"⚡ الإعدادات: MAX_IPS_PER_MSG={MAX_IPS_PER_MSG}, MAX_FILE_IPS={MAX_FILE_IPS}")
    
    try:
        bot.remove_webhook()
        time.sleep(1)
        print("✅ تم إلغاء الويب هوك بنجاح")
    except Exception as e:
        print(f"⚠️ ملاحظة: {e}")
    
    bot.infinity_polling()