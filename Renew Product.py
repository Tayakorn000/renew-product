import tkinter as tk
from tkinter import ttk, messagebox, filedialog
try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.keys import Keys
except ImportError:
    # selenium ไม่มีในเครื่อง (เช่น ตอนรัน test เฉพาะ logic จับคู่โฟลเดอร์บนเครื่องที่ไม่ได้ตั้ง dev env)
    # โปรแกรมจริงต้องมี selenium เสมอ ส่วนที่ใช้ driver จะพังถ้าเรียกตอนไม่มี
    uc = By = WebDriverWait = EC = ActionChains = Keys = None
import time
import os
import sys
import re
import configparser
import threading
import json
import base64
import random
import urllib.request
import urllib.parse

# ค่าเริ่มต้นของบอทแจ้งเตือน ให้ exe มีมาในตัว ไม่ต้องให้ลูกค้ากรอก
# อยู่ในไฟล์แยกที่ gitignore ไว้ — repo นี้ public ห้ามฝัง token ลงไฟล์ที่ขึ้น git
# ไม่มีไฟล์นี้ = ช่องในโปรแกรมว่าง กรอกเองได้ตามปกติ
try:
    from telegram_default import TELEGRAM_TOKEN as DEFAULT_TELEGRAM_TOKEN
    from telegram_default import TELEGRAM_CHAT_ID as DEFAULT_TELEGRAM_CHAT_ID
except Exception:
    DEFAULT_TELEGRAM_TOKEN = ''
    DEFAULT_TELEGRAM_CHAT_ID = ''

# เพิ่มเลขนี้แล้ว push = exe ของลูกค้าโหลดไฟล์นี้จาก GitHub ไปรันแทนตัวที่ฝังมา ตอนเปิดโปรแกรมรอบหน้า
# ไม่เพิ่มเลข = push ได้ตามปกติ ลูกค้ายังไม่ได้ของใหม่
APP_VERSION = 5
UPDATE_URL = "https://raw.githubusercontent.com/Tayakorn000/renew-product/main/Renew%20Product.py"
UPDATE_FILE = "renew_update.py"

class FacebookMarketplaceRenewer:
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
    VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    REVIEW_KEYWORDS = ['รีวิว']
    EXTRA_KEYWORDS = ['เพิ่มเติม']

    # worker ของทุก Profile เขียน reply_settings.json ไฟล์เดียวกัน ต้องกันเขียนทับกันเอง
    # ไม่มี lock = ไฟล์ขาดกลาง โหลดรอบหน้าไม่ขึ้น แล้วส่งข้อมูลหลักซ้ำให้ลูกค้าเก่าทุกคน
    SETTINGS_LOCK = threading.Lock()
    # แจ้งเตือนยิงพร้อมกันได้หลาย Profile เจอคนทักบอทคนเดียวกันพร้อมกัน ต้องเพิ่มแค่ครั้งเดียว
    TELEGRAM_LOCK = threading.Lock()

    # ลำดับโฟลเดอร์ที่ส่งตามหลัง main ทุกครั้งที่ลูกค้าทักกลับมา (stage 1 = ส่ง main ไปแล้ว)
    REPLY_STAGES = ['review', 'extra']
    STAGE_LABELS = {'main': 'แชทหลัก', 'review': 'รีวิวสินค้า', 'extra': 'รูปภาพเพิ่มเติม'}
    ALL_STAGES = ['main'] + REPLY_STAGES
    # ค่าเริ่มต้น: ทักครั้งแรกตอบข้อมูลหลักให้ ทักกลับมาถามอะไรแค่แจ้งเตือน ไม่ตอบเอง
    # (ลูกค้าถาม "จ่ายปลายทางได้มั้ย" แล้วโดนยิงรีวิวกลับ = ไม่ตอบคำถาม) ติ๊กเปิดเองได้
    DEFAULT_STAGE_ENABLED = {'main': True, 'review': False, 'extra': False}

    # ต่ออายุสินค้าคั่นระหว่างเฝ้าแชท — ใช้ Chrome ตัวเดิมของ Profile นั้น
    # (เปิด Chrome โปรไฟล์เดียวซ้อน 2 ตัวไม่ได้ เลยต้องสลับกันใช้ตัวเดียว)
    RENEW_PAGE_URL = "https://www.facebook.com/marketplace/selling/renew_listings/"
    DEFAULT_RENEW_INTERVAL_MIN = 30

    # FB เติมคำนำหน้าใน preview เมื่อข้อความล่าสุดเป็นของเราเอง ("คุณ: ..." / "คุณส่งรูปภาพ")
    PREVIEW_SELF_PREFIXES = ('คุณ:', 'you:', 'คุณส่ง', 'you sent')

    # ตัวเลข/คำบอกเวลาใน preview ของแถว inbox ("2 นาที", "6 ต.ค.") ขยับเองแม้ไม่มีข้อความใหม่
    # ตัดออกก่อนเทียบ — ตัดเกินดีกว่าตัดขาด เพราะตัดขาด = ส่งรีวิวทับลูกค้าที่ไม่ได้ทักอะไร
    ROW_TIME_NOISE = re.compile(
        r'\d+|นาที|ชั่วโมง|ชม\.?|วินาที|วัน|สัปดาห์|เดือน|ปี|น\.|[ก-ฮ]\.[ก-ฮ]\.'
        r'|min(?:ute)?s?|hours?|hrs?|days?|weeks?|months?|years?|ago|[ap]m|\s+',
        re.IGNORECASE)

    def __init__(self):
        self.root = tk.Tk()
        self.root.title(f"ต่ออายุสินค้า Facebook Marketplace v{APP_VERSION}")
        # ไม่ล็อกขนาดหน้าต่าง ปล่อยให้พอดีของข้างใน เคยล็อก 600x650 แล้วของสูง 825 ครึ่งล่างโดนตัดมองไม่เห็น

        self.is_running = False
        self.settings_file = "renew_settings.json"
        self.profiles = {}
        self.current_profile = None

        # ตอบแชทอัตโนมัติ (Marketplace inbox)
        self.reply_settings_file = "reply_settings.json"
        self.reply_root_folder = None
        self.reply_state = {}  # {profile_name: {thread_id: {...}}}
        # โฟลเดอร์ไหนให้ตอบออโต้บ้าง (ติ๊กใน GUI) — ปิดอันไหน ออโต้ข้ามอันนั้น ส่งด้วยมือได้เหมือนเดิม
        self.stage_enabled = dict(self.DEFAULT_STAGE_ENABLED)
        # ต่ออายุสินค้าไปด้วยระหว่างเฝ้าแชท (ปิดไว้ก่อน ลูกค้าเปิดเองใน GUI)
        self.renew_while_reply = False
        self.renew_interval_min = self.DEFAULT_RENEW_INTERVAL_MIN
        self.telegram_token = DEFAULT_TELEGRAM_TOKEN
        self.telegram_chat_id = DEFAULT_TELEGRAM_CHAT_ID
        self.telegram_seen = 0  # เวลาของข้อความล่าสุดที่คนทักบอท ที่เก็บเข้าช่อง Chat ID ไปแล้ว
        self.auto_reply_active = False
        self.reply_drivers = {}  # profile_name -> driver ที่ยังเปิดอยู่ระหว่างตอบแชท
        # Chrome 1 ตัวโดน 2 thread สั่งพร้อมกันไม่ได้ (ลูปเฝ้าแชท กับ ปุ่มส่งด้วยมือ) ไม่งั้นส่งผิดห้องแชท
        self.driver_locks = {}  # profile_name -> Lock
        self._reply_list_index = []  # index ของ reply_listbox -> (profile_name, thread_id)

        # ตั้งค่าให้ปิด Chrome ทั้งหมดเมื่อปิดหน้าต่าง GUI
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # โหลดการตั้งค่าที่บันทึกไว้
        self.load_settings()
        self.fix_ini_cookie_format()
        self.load_reply_settings()
        self.setup_gui()
        # รอ mainloop ขึ้นก่อน thread ถึงเรียก root.after ได้
        self.root.after(1000, lambda: threading.Thread(target=self.add_new_telegram_chats, daemon=True).start())

    def on_closing(self):
        """ฟังก์ชันที่ทำงานเมื่อปิดหน้าต่าง GUI"""
        try:
            # แสดง messagebox ยืนยัน
            if messagebox.askokcancel("ปิดโปรแกรม", "ต้องการปิดโปรแกรมและ Chrome ทั้งหมดหรือไม่?"):
                # บอกลูปเฝ้าแชทว่าตั้งใจปิด ไม่งั้นมันเห็น Chrome หายแล้วยิงแจ้งเตือนว่าเฟสมีปัญหา
                self.auto_reply_active = False
                # ปิด Chrome ทั้งหมด
                self.close_all_chrome()
                
                # ปิดหน้าต่าง GUI
                self.root.destroy()
        except Exception as e:
            print(f"Error in on_closing: {e}")
            # ปิดหน้าต่างแม้มี error
            self.root.destroy()
    
    def close_all_chrome(self):
        """ปิด Chrome ทั้งหมดที่เปิดอยู่"""
        closed_count = 0
        
        print("กำลังปิด Chrome ทั้งหมด...")
        
        try:
            import psutil
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    # หา Chrome ที่เปิดโดย Selenium (มี --test-type ใน cmdline)
                    if proc.info['name'] and 'chrome.exe' in proc.info['name'].lower():
                        cmdline = proc.info['cmdline']
                        if cmdline and any('--test-type' in str(arg) for arg in cmdline):
                            print(f"พบ Chrome process (PID: {proc.info['pid']}) ที่เปิดโดย Selenium")
                            proc.kill()
                            closed_count += 1
                            print(f"ปิด Chrome process (PID: {proc.info['pid']}) สำเร็จ")
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    pass
            
            if closed_count > 0:
                print(f"ปิด Chrome ทั้งหมด {closed_count} หน้าต่าง")
            else:
                print("ไม่พบ Chrome ที่เปิดโดย Selenium")
                
        except ImportError:
            print("ไม่สามารถ import psutil ได้ (ติดตั้งด้วย: pip install psutil)")
        except Exception as e:
            print(f"Error ในการปิด Chrome: {e}")
    
    def random_sleep(self, min_sec=1, max_sec=3):
        """หน่วงเวลาแบบสุ่มเพื่อให้ดูเป็นธรรมชาติ"""
        time.sleep(random.uniform(min_sec, max_sec))
    
    def human_like_scroll(self, driver, direction="down"):
        """เลื่อนหน้าจอแบบมนุษย์ - ช้าๆ และไม่เท่ากัน"""
        try:
            scroll_amount = random.randint(100, 400) if direction == "down" else -random.randint(100, 400)
            steps = random.randint(3, 6)  # แบ่งการเลื่อนเป็นหลายขั้น
            
            for _ in range(steps):
                step_scroll = scroll_amount // steps + random.randint(-20, 20)
                driver.execute_script(f"window.scrollBy(0, {step_scroll});")
                time.sleep(random.uniform(0.1, 0.3))
        except:
            pass
    
    def human_like_read_page(self, driver):
        """จำลองการอ่านหน้าเว็บ - เลื่อนดูและหยุดพัก"""
        try:
            # เลื่อนลงช้าๆ เหมือนกำลังอ่าน
            for _ in range(random.randint(2, 4)):
                self.human_like_scroll(driver, "down")
                time.sleep(random.uniform(0.5, 1.5))  # หยุดอ่าน
            
            # บางครั้งเลื่อนกลับขึ้นไปดูอีกรอบ
            if random.random() < 0.3:
                self.human_like_scroll(driver, "up")
                time.sleep(random.uniform(0.3, 0.8))
        except:
            pass
    
    def human_like_type(self, element, text, driver):
        """พิมพ์ข้อความแบบคนจริง พร้อมเคลื่อนเมาส์"""
        # เคลื่อนเมาส์ไปที่ element แบบช้าๆ
        try:
            actions = ActionChains(driver)
            actions.move_to_element(element).perform()
            time.sleep(random.uniform(0.4, 0.9))
        except:
            pass
        
        # พิมพ์ทีละตัวอักษรด้วยความเร็วสุ่มที่หลากหลาย
        for i, char in enumerate(text):
            # ChromeDriver พิมพ์ได้แค่ตัวอักษรใน BMP เจออีโมจิอย่าง 🔥 send_keys พังกลางข้อความ เลยแทรกผ่าน CDP แทน
            if ord(char) > 0xFFFF:
                driver.execute_cdp_cmd('Input.insertText', {'text': char})
            else:
                element.send_keys(char)

            # ความเร็วพิมพ์แปรผันตามตำแหน่ง
            if i == 0:
                time.sleep(random.uniform(0.15, 0.35))  # ตัวแรกช้าหน่อย
            else:
                time.sleep(random.uniform(0.06, 0.18))  # ตัวอื่นๆ
            
            # บางครั้งหยุดพักเหมือนคนคิด (เพิ่มโอกาส)
            if random.random() < 0.15:  # 15% โอกาส
                time.sleep(random.uniform(0.4, 1.2))
            
            # บางครั้งพิมพ์เร็วติดกัน 2-3 ตัว
            if random.random() < 0.2 and i < len(text) - 1:
                time.sleep(random.uniform(0.02, 0.05))
    
    def random_mouse_movement(self, driver):
        """เคลื่อนเมาส์แบบสุ่มเพื่อให้ดูเป็นธรรมชาติ"""
        try:
            # หา element สุ่มบนหน้าเว็บ
            elements = driver.find_elements(By.TAG_NAME, "div")
            if elements and len(elements) > 5:
                # เคลื่อนเมาส์ไปหลายจุด (เหมือนกำลังมองหา)
                for _ in range(random.randint(1, 3)):
                    random_element = random.choice(elements[:30])
                    actions = ActionChains(driver)
                    actions.move_to_element(random_element).perform()
                    time.sleep(random.uniform(0.2, 0.5))
        except:
            pass
    
    def human_like_clear_field(self, element, driver):
        """ล้างช่อง input แบบมนุษย์ — ใช้ Ctrl+A แล้ว Delete แทน .clear()"""
        try:
            element.send_keys(Keys.CONTROL + "a")
            time.sleep(random.uniform(0.1, 0.3))
            element.send_keys(Keys.DELETE)
            time.sleep(random.uniform(0.1, 0.2))
        except:
            # fallback ถ้าไม่ได้
            try:
                element.clear()
            except:
                pass
    
    def human_like_scroll_to_element(self, driver, element):
        """เลื่อนหน้าจอไปที่ element แบบมนุษย์ — ใช้ scrollBy แทน scrollIntoView"""
        try:
            # หาตำแหน่งของ element บนหน้าจอ
            elem_location = element.location
            elem_y = elem_location['y']
            
            # หาตำแหน่ง scroll ปัจจุบัน
            current_scroll = driver.execute_script("return window.pageYOffset;")
            viewport_height = driver.execute_script("return window.innerHeight;")
            
            # คำนวณว่าต้องเลื่อนเท่าไหร่ให้ element อยู่กลางจอ
            target_scroll = elem_y - (viewport_height // 2)
            scroll_needed = target_scroll - current_scroll
            
            # ถ้าไม่ต้องเลื่อนมาก (element อยู่ในจอแล้ว) ก็ไม่ต้องทำอะไร
            if abs(scroll_needed) < 100:
                return
            
            # เลื่อนแบบแบ่ง step เหมือนคนใช้ scroll wheel
            steps = random.randint(4, 8)
            for i in range(steps):
                step_amount = scroll_needed // steps + random.randint(-15, 15)
                driver.execute_script(f"window.scrollBy(0, {step_amount});")
                time.sleep(random.uniform(0.05, 0.15))
            
            # รอให้เลื่อนเสร็จ
            time.sleep(random.uniform(0.3, 0.6))
        except:
            # fallback ใช้ scrollIntoView ถ้าวิธีข้างบนไม่ได้
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
                time.sleep(random.uniform(0.8, 1.2))
            except:
                pass
    
    def simulate_focus_change(self, driver):
        """จำลองการหลุดโฟกัสชั่วคราว — เหมือนคนไปทำอย่างอื่นแล้วกลับมา"""
        try:
            # Blur หน้าต่าง (เหมือนคนคลิกไปที่อื่น)
            driver.execute_script("window.dispatchEvent(new Event('blur'));")
            time.sleep(random.uniform(2, 6))
            
            # Focus กลับมา
            driver.execute_script("window.dispatchEvent(new Event('focus'));")
            time.sleep(random.uniform(0.5, 1.0))
        except:
            pass
    
    def wait_for_page_load(self, driver, timeout=15):
        """รอให้หน้าเว็บโหลดเสร็จสมบูรณ์"""
        try:
            WebDriverWait(driver, timeout).until(
                lambda d: d.execute_script('return document.readyState') == 'complete'
            )
            # รอเพิ่มเล็กน้อยให้ JavaScript โหลดเสร็จ
            time.sleep(random.uniform(1, 2))
        except:
            pass
    
    def load_settings(self):
        """โหลดการตั้งค่าที่บันทึกไว้"""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    self.profiles = settings.get('profiles', {})
                    self.current_profile = settings.get('current_profile', None)
        except Exception:
            pass
    
    def save_settings(self):
        """บันทึกการตั้งค่า"""
        try:
            settings = {
                'profiles': self.profiles,
                'current_profile': self.current_profile
            }
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_reply_settings(self):
        """โหลดการตั้งค่าตอบแชทอัตโนมัติ (โฟลเดอร์สินค้า + ประวัติแชทที่ตอบไปแล้ว)"""
        try:
            if os.path.exists(self.reply_settings_file):
                with open(self.reply_settings_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.reply_root_folder = data.get('root_folder')
                    self.reply_state = data.get('state', {})
                    # ที่กรอกในโปรแกรมชนะค่าที่ฝังมากับ exe ลูกค้าเปลี่ยนเป็นบอทตัวเองได้
                    self.telegram_token = data.get('telegram_token') or DEFAULT_TELEGRAM_TOKEN
                    self.telegram_chat_id = data.get('telegram_chat_id') or DEFAULT_TELEGRAM_CHAT_ID
                    self.telegram_seen = data.get('telegram_seen') or 0
                    saved_stages = data.get('stage_enabled') or {}
                    self.stage_enabled = {
                        c: bool(saved_stages.get(c, self.DEFAULT_STAGE_ENABLED[c])) for c in self.ALL_STAGES}
                    self.renew_while_reply = bool(data.get('renew_while_reply', False))
                    self.renew_interval_min = data.get('renew_interval_min') or self.DEFAULT_RENEW_INTERVAL_MIN
        except Exception:
            pass

    def save_reply_settings(self):
        """บันทึกการตั้งค่าตอบแชทอัตโนมัติ"""
        try:
            with self.SETTINGS_LOCK:
                data = {
                    'root_folder': self.reply_root_folder,
                    'state': {p: dict(threads) for p, threads in list(self.reply_state.items())},
                    'telegram_token': getattr(self, 'telegram_token', ''),
                    'telegram_chat_id': getattr(self, 'telegram_chat_id', ''),
                    'telegram_seen': getattr(self, 'telegram_seen', 0),
                    'stage_enabled': dict(getattr(self, 'stage_enabled', {})),
                    'renew_while_reply': bool(getattr(self, 'renew_while_reply', False)),
                    'renew_interval_min': getattr(self, 'renew_interval_min', self.DEFAULT_RENEW_INTERVAL_MIN),
                }
                text = json.dumps(data, ensure_ascii=False, indent=2)
                # เขียนไฟล์ชั่วคราวแล้วสลับ ปิดโปรแกรมกลางคันจะได้ไม่เหลือไฟล์ขาดครึ่ง (โหลดไม่ขึ้น = ประวัติแชทหาย)
                tmp = self.reply_settings_file + '.tmp'
                with open(tmp, 'w', encoding='utf-8') as f:
                    f.write(text)
                os.replace(tmp, self.reply_settings_file)
        except Exception:
            pass

    def setup_gui(self):
        # หัวข้อ
        title_label = tk.Label(
            self.root, 
            text="โปรแกรมต่ออายุสินค้า Facebook", 
            font=("Arial", 14, "bold")
        )
        title_label.pack(pady=10)

        # สถานะ — pack ก่อนแบบติดขอบล่าง จอเตี้ยแค่ไหนบรรทัดนี้ก็ไม่โดนตัด (เป็นที่เดียวที่บอกว่าโปรแกรมทำอะไรอยู่)
        self.status_label = tk.Label(
            self.root,
            text="พร้อมใช้งาน",
            font=("Arial", 9),
            fg="gray"
        )
        self.status_label.pack(side=tk.BOTTOM, pady=5)

        # 2 คอลัมน์: ซ้ายจัดการ Profile + ต่ออายุ ขวาตอบแชท — เรียงลงมาแถวเดียวสูงเกินจอโน้ตบุ๊ก
        body = tk.Frame(self.root)
        body.pack(fill=tk.BOTH, expand=True)
        left = tk.Frame(body)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right = tk.Frame(body)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # กรอบจัดการ Profile
        profile_frame = tk.LabelFrame(left, text="จัดการ Profile", font=("Arial", 10, "bold"), padx=10, pady=10)
        profile_frame.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)
        
        # รายการ Profile พร้อม Checkbox
        list_frame = tk.Frame(profile_frame)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        tk.Label(list_frame, text="เลือก Profile ที่ต้องการต่ออายุ:", font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=(0, 5))
        
        # สร้าง Scrollbar และ Listbox
        scroll_frame = tk.Frame(list_frame)
        scroll_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = tk.Scrollbar(scroll_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.profile_listbox = tk.Listbox(
            scroll_frame,
            selectmode=tk.MULTIPLE,
            font=("Arial", 10),
            height=5,
            yscrollcommand=scrollbar.set
        )
        self.profile_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.profile_listbox.yview)
        
        # ปุ่มเลือก/ยกเลิกทั้งหมด
        select_frame = tk.Frame(list_frame)
        select_frame.pack(fill=tk.X, pady=5)
        
        select_all_btn = tk.Button(
            select_frame,
            text="เลือกทั้งหมด",
            command=self.select_all_profiles,
            font=("Arial", 9),
            cursor="hand2",
            width=12
        )
        select_all_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        deselect_all_btn = tk.Button(
            select_frame,
            text="ยกเลิกทั้งหมด",
            command=self.deselect_all_profiles,
            font=("Arial", 9),
            cursor="hand2",
            width=12
        )
        deselect_all_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.delete_btn = tk.Button(
            select_frame,
            text="ลบ Profile ที่เลือก",
            command=self.delete_selected_profiles,
            font=("Arial", 9),
            bg="#f44336",
            fg="white",
            cursor="hand2",
            width=15
        )
        self.delete_btn.pack(side=tk.RIGHT)

        self.manual_login_btn = tk.Button(
            select_frame,
            text="Login ด้วยมือ (บันทึก Cookie)",
            command=self.open_manual_login_browser,
            font=("Arial", 9),
            bg="#42b72a",
            fg="white",
            cursor="hand2",
            width=22
        )
        self.manual_login_btn.pack(side=tk.RIGHT, padx=(0, 5))

        # แถวปุ่ม Auto Cookie Login
        auto_login_frame = tk.Frame(list_frame)
        auto_login_frame.pack(fill=tk.X, pady=(0, 3))

        self.auto_cookie_login_btn = tk.Button(
            auto_login_frame,
            text="Login ด้วย Cookie อัตโนมัติ (Profile ที่เลือก)",
            command=self.open_auto_cookie_login_browser,
            font=("Arial", 9, "bold"),
            bg="#FF9800",
            fg="white",
            cursor="hand2",
        )
        self.auto_cookie_login_btn.pack(fill=tk.X)

        # เพิ่ม Profile ใหม่
        add_frame = tk.LabelFrame(profile_frame, text="เพิ่ม Profile ใหม่", font=("Arial", 9), padx=10, pady=8)
        add_frame.pack(fill=tk.X, pady=5)
        
        # ชื่อ Profile
        name_frame = tk.Frame(add_frame)
        name_frame.pack(fill=tk.X, pady=3)
        tk.Label(name_frame, text="ชื่อ Profile:", font=("Arial", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.profile_name_entry = tk.Entry(name_frame, font=("Arial", 9), width=35)
        self.profile_name_entry.pack(side=tk.LEFT, padx=5)
        
        # ไฟล์ Config
        file_frame = tk.Frame(add_frame)
        file_frame.pack(fill=tk.X, pady=3)
        tk.Label(file_frame, text="ไฟล์ .ini:", font=("Arial", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        
        self.new_file_var = tk.StringVar(value="ยังไม่ได้เลือก")
        self.new_file_label = tk.Label(file_frame, textvariable=self.new_file_var, font=("Arial", 9), fg="gray", width=22, anchor=tk.W)
        self.new_file_label.pack(side=tk.LEFT, padx=5)
        
        browse_btn = tk.Button(
            file_frame,
            text="เลือกไฟล์",
            command=self.browse_new_config,
            font=("Arial", 9),
            cursor="hand2"
        )
        browse_btn.pack(side=tk.LEFT)

        # นำเข้าทั้งโฟลเดอร์ - สแกน .ini ทุกไฟล์ในโฟลเดอร์ เพิ่ม Profile ให้อัตโนมัติทีเดียว
        import_folder_btn = tk.Button(
            add_frame,
            text="นำเข้าทั้งโฟลเดอร์ (.ini ทั้งหมด)",
            command=self.import_ini_folder,
            font=("Arial", 9),
            cursor="hand2"
        )
        import_folder_btn.pack(pady=(3, 0))

        # ปุ่มเพิ่ม
        add_btn = tk.Button(
            add_frame,
            text="เพิ่ม Profile",
            command=self.add_profile,
            font=("Arial", 9, "bold"),
            bg="#2196F3",
            fg="white",
            cursor="hand2",
            padx=15,
            pady=5
        )
        add_btn.pack(pady=8)
        
        # ปุ่มเริ่มต้น (ย้ายออกมานอก frame)
        button_frame = tk.Frame(left)
        button_frame.pack(pady=10, fill=tk.X, padx=20)
        
        self.start_button = tk.Button(
            button_frame,
            text="เริ่มต่ออายุสินค้า (Profile ที่เลือก)",
            command=self.start_renewal,
            bg="#4CAF50",
            fg="white",
            font=("Arial", 12, "bold"),
            padx=20,
            pady=12,
            cursor="hand2"
        )
        self.start_button.pack(fill=tk.X)

        # กรอบตอบแชทลูกค้าอัตโนมัติ (Marketplace inbox) — ใช้ Profile ที่เลือกด้านบนร่วมกัน
        reply_frame = tk.LabelFrame(right, text="ตอบแชทลูกค้าอัตโนมัติ (Marketplace)", font=("Arial", 10, "bold"), padx=10, pady=10)
        reply_frame.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)

        folder_row = tk.Frame(reply_frame)
        folder_row.pack(fill=tk.X, pady=3)
        tk.Label(folder_row, text="โฟลเดอร์สินค้า:", font=("Arial", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.reply_folder_var = tk.StringVar(value=self.reply_root_folder or "ยังไม่ได้เลือก")
        tk.Label(folder_row, textvariable=self.reply_folder_var, font=("Arial", 9), fg="gray", anchor=tk.W).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(folder_row, text="เลือกโฟลเดอร์", command=self.browse_reply_folder, font=("Arial", 9), cursor="hand2").pack(side=tk.RIGHT)

        # เลือกว่าจะให้ตอบออโต้ด้วยโฟลเดอร์ไหนบ้าง — ปิดอันไหน ออโต้ข้าม ส่งด้วยมือยังได้
        stage_row = tk.Frame(reply_frame)
        stage_row.pack(fill=tk.X, pady=3)
        tk.Label(stage_row, text="ตอบออโต้ด้วย:", font=("Arial", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.stage_vars = {}
        for category in self.ALL_STAGES:
            var = tk.BooleanVar(value=self.stage_enabled.get(category, True))
            self.stage_vars[category] = var
            tk.Checkbutton(
                stage_row, text=self.STAGE_LABELS[category], variable=var,
                font=("Arial", 9), command=self.save_stage_choice
            ).pack(side=tk.LEFT, padx=(0, 8))

        # ต่ออายุสินค้าไปด้วยระหว่างเฝ้าแชท — ใช้ Chrome ตัวเดิม กดปุ่มต่ออายุแยกไม่ได้อยู่แล้ว
        renew_row = tk.Frame(reply_frame)
        renew_row.pack(fill=tk.X, pady=3)
        tk.Label(renew_row, text="ต่ออายุด้วย:", font=("Arial", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.renew_while_reply_var = tk.BooleanVar(value=self.renew_while_reply)
        tk.Checkbutton(
            renew_row, text="ต่ออายุสินค้าไปด้วยระหว่างเฝ้าแชท ทุก", variable=self.renew_while_reply_var,
            font=("Arial", 9), command=self.save_renew_choice
        ).pack(side=tk.LEFT)
        self.renew_interval_entry = tk.Entry(renew_row, font=("Arial", 9), width=5, justify=tk.CENTER)
        self.renew_interval_entry.insert(0, str(self.renew_interval_min))
        self.renew_interval_entry.pack(side=tk.LEFT, padx=4)
        self.renew_interval_entry.bind("<FocusOut>", lambda e: self.save_renew_choice())
        self.renew_interval_entry.bind("<Return>", lambda e: self.save_renew_choice())
        tk.Label(renew_row, text="นาที", font=("Arial", 9)).pack(side=tk.LEFT)

        reply_btn_row = tk.Frame(reply_frame)
        reply_btn_row.pack(fill=tk.X, pady=5)
        self.reply_start_btn = tk.Button(
            reply_btn_row, text="เริ่มตอบแชทอัตโนมัติ (Profile ที่เลือกด้านบน)",
            command=self.start_auto_reply, bg="#2196F3", fg="white",
            font=("Arial", 10, "bold"), cursor="hand2"
        )
        self.reply_start_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.reply_stop_btn = tk.Button(
            reply_btn_row, text="หยุด", command=self.stop_auto_reply,
            bg="#f44336", fg="white", font=("Arial", 10, "bold"),
            state=tk.DISABLED, cursor="hand2", width=8
        )
        self.reply_stop_btn.pack(side=tk.RIGHT)

        # แจ้งเตือนเข้า Telegram เวลามีลูกค้าทัก (บอกว่ามาจากเฟสไหน)
        tg_row = tk.Frame(reply_frame)
        tg_row.pack(fill=tk.X, pady=3)
        tk.Label(tg_row, text="Telegram Token:", font=("Arial", 9), width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.tg_token_entry = tk.Entry(tg_row, font=("Arial", 9), show="*")
        self.tg_token_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.tg_token_entry.insert(0, self.telegram_token)

        tg_row2 = tk.Frame(reply_frame)
        tg_row2.pack(fill=tk.X, pady=3)
        tk.Label(tg_row2, text="Chat ID:", font=("Arial", 9), width=14, anchor=tk.W).pack(side=tk.LEFT)
        self.tg_chat_entry = tk.Entry(tg_row2, font=("Arial", 9))
        self.tg_chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.tg_chat_entry.insert(0, self.telegram_chat_id)
        tk.Button(tg_row2, text="บันทึก + ทดสอบส่ง", command=self.save_and_test_telegram,
                  font=("Arial", 9), cursor="hand2").pack(side=tk.RIGHT)

        tk.Label(reply_frame, text="แชทที่ตอบไปแล้ว:", font=("Arial", 9, "bold")).pack(anchor=tk.W, pady=(5, 0))
        reply_list_frame = tk.Frame(reply_frame)
        reply_list_frame.pack(fill=tk.BOTH, expand=True, pady=3)
        reply_scrollbar = tk.Scrollbar(reply_list_frame)
        reply_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.reply_listbox = tk.Listbox(
            reply_list_frame, font=("Arial", 9), height=5,
            yscrollcommand=reply_scrollbar.set
        )
        self.reply_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        reply_scrollbar.config(command=self.reply_listbox.yview)

        manual_btn_row = tk.Frame(reply_frame)
        manual_btn_row.pack(fill=tk.X, pady=3)
        tk.Button(
            manual_btn_row, text="ส่งรีวิวเพิ่ม (แชทที่เลือก)",
            command=lambda: self.manual_send_category('review'),
            font=("Arial", 9), cursor="hand2"
        ).pack(side=tk.LEFT, padx=(0, 5))
        tk.Button(
            manual_btn_row, text="ส่งข้อมูลเพิ่มเติม (แชทที่เลือก)",
            command=lambda: self.manual_send_category('extra'),
            font=("Arial", 9), cursor="hand2"
        ).pack(side=tk.LEFT)

        # อัปเดต Listbox
        self.update_profile_list()
        self.update_reply_list()
    
    def update_profile_list(self):
        """อัปเดตรายการ Profile ใน Listbox"""
        self.profile_listbox.delete(0, tk.END)
        
        for profile_name in self.profiles.keys():
            self.profile_listbox.insert(tk.END, profile_name)
        
        if not self.profiles:
            self.status_label.config(text="ยังไม่มี Profile กรุณาเพิ่ม Profile ใหม่", fg="orange")
        else:
            self.status_label.config(text=f"มี {len(self.profiles)} Profile พร้อมใช้งาน", fg="green")
    
    def select_all_profiles(self):
        """เลือก Profile ทั้งหมด"""
        self.profile_listbox.select_set(0, tk.END)
    
    def deselect_all_profiles(self):
        """ยกเลิกการเลือกทั้งหมด"""
        self.profile_listbox.selection_clear(0, tk.END)
    
    def browse_new_config(self):
        """เลือกไฟล์ Config สำหรับ Profile ใหม่"""
        file_path = filedialog.askopenfilename(
            title="เลือกไฟล์รหัสล็อคอิน",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")]
        )
        
        if file_path:
            self.new_config_path = file_path
            file_name = os.path.basename(file_path)
            self.new_file_var.set(file_name)
            self.new_file_label.config(fg="green")
    
    def add_profile(self):
        """เพิ่ม Profile ใหม่"""
        profile_name = self.profile_name_entry.get().strip()
        
        if not profile_name:
            messagebox.showwarning("คำเตือน", "กรุณากรอกชื่อ Profile")
            return
        
        if profile_name in self.profiles:
            messagebox.showwarning("คำเตือน", "ชื่อ Profile นี้มีอยู่แล้ว")
            return
        
        if not hasattr(self, 'new_config_path') or not self.new_config_path:
            messagebox.showwarning("คำเตือน", "กรุณาเลือกไฟล์ .ini")
            return
        
        if not os.path.exists(self.new_config_path):
            messagebox.showerror("ข้อผิดพลาด", "ไฟล์ที่เลือกไม่พบ")
            return
        
        # เพิ่ม Profile
        # ใช้ชื่อ Profile เป็นชื่อโฟลเดอร์เพื่อไม่ให้ซ้ำกัน
        safe_profile_name = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in profile_name)
        self.profiles[profile_name] = {
            'config_file': self.new_config_path,
            'chrome_profile': f"chrome_profile_{safe_profile_name}"
        }
        
        self.save_settings()
        
        # รีเซ็ตฟอร์ม
        self.profile_name_entry.delete(0, tk.END)
        self.new_file_var.set("ยังไม่ได้เลือก")
        self.new_file_label.config(fg="gray")
        self.new_config_path = None
        
        # อัปเดตรายการ
        self.update_profile_list()
        
        messagebox.showinfo("สำเร็จ", f"เพิ่ม Profile '{profile_name}' เรียบร้อยแล้ว")

    def import_ini_folder(self):
        """สแกนทั้งโฟลเดอร์ หาไฟล์ .ini ทุกไฟล์ เพิ่มเป็น Profile ให้อัตโนมัติทีเดียว (ชื่อ Profile = ชื่อไฟล์)"""
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์ที่มีไฟล์ .ini")
        if not folder:
            return

        ini_files = sorted(f for f in os.listdir(folder) if f.lower().endswith('.ini'))
        if not ini_files:
            messagebox.showwarning("คำเตือน", "ไม่พบไฟล์ .ini ในโฟลเดอร์นี้")
            return

        added, skipped = 0, 0
        for fname in ini_files:
            profile_name = os.path.splitext(fname)[0]
            if profile_name in self.profiles:
                skipped += 1
                continue
            safe_profile_name = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in profile_name)
            self.profiles[profile_name] = {
                'config_file': os.path.join(folder, fname),
                'chrome_profile': f"chrome_profile_{safe_profile_name}"
            }
            added += 1

        self.save_settings()
        self.update_profile_list()
        messagebox.showinfo("สำเร็จ", f"เพิ่ม Profile ใหม่ {added} รายการ (ข้าม {skipped} ที่มีอยู่แล้ว)")

    def delete_selected_profiles(self):
        """ลบ Profile ที่เลือก"""
        selected_indices = self.profile_listbox.curselection()
        
        if not selected_indices:
            messagebox.showwarning("คำเตือน", "กรุณาเลือก Profile ที่ต้องการลบ")
            return
        
        selected_names = [self.profile_listbox.get(i) for i in selected_indices]
        
        confirm = messagebox.askyesno("ยืนยัน", f"ต้องการลบ {len(selected_names)} Profile หรือไม่?\n\nจะลบทั้งข้อมูลและโฟลเดอร์ Chrome Profile\n\n" + "\n".join(selected_names))
        
        if confirm:
            deleted_count = 0
            for name in selected_names:
                if name in self.profiles:
                    # ลบโฟลเดอร์ Chrome Profile
                    try:
                        chrome_profile_dir = os.path.join(os.getcwd(), self.profiles[name]['chrome_profile'])
                        if os.path.exists(chrome_profile_dir):
                            import shutil
                            shutil.rmtree(chrome_profile_dir)
                            print(f"ลบโฟลเดอร์: {chrome_profile_dir}")
                    except Exception as e:
                        print(f"ไม่สามารถลบโฟลเดอร์ {chrome_profile_dir}: {e}")
                    
                    # ลบข้อมูลใน settings
                    del self.profiles[name]
                    deleted_count += 1
            
            self.save_settings()
            self.update_profile_list()

            messagebox.showinfo("สำเร็จ", f"ลบ {deleted_count} Profile และโฟลเดอร์เรียบร้อยแล้ว")

    def open_manual_login_browser(self):
        """เปิด Chrome จริงให้ผู้ใช้ Login มือ (ไม่พิมพ์ auto) แล้วบันทึก Cookies ลง .ini - เหมือน FBMKP"""
        selected_indices = self.profile_listbox.curselection()

        if not selected_indices:
            messagebox.showwarning("คำเตือน", "กรุณาเลือก Profile ที่ต้องการ Login")
            return

        if len(selected_indices) > 1:
            messagebox.showwarning("คำเตือน", "เลือก Login ด้วยมือได้ทีละ 1 Profile เท่านั้น")
            return

        profile_name = self.profile_listbox.get(selected_indices[0])
        threading.Thread(target=self.run_manual_login_thread, args=(profile_name,), daemon=True).start()

    def run_manual_login_thread(self, profile_name):
        try:
            self.manual_login_and_save_cookies(profile_name)
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("ผิดพลาด", f"Login ด้วยมือไม่สำเร็จ: {str(e)}"))

    def manual_login_and_save_cookies(self, profile_name):
        """เปิด Chrome ด้วย Profile ที่เลือก ให้ผู้ใช้ Login เองในหน้าต่างจริง แล้วบันทึก Cookie"""
        profile_data = self.profiles[profile_name]
        config_file_path = profile_data['config_file']
        chrome_profile_dir = os.path.join(os.getcwd(), profile_data['chrome_profile'])

        if not os.path.exists(chrome_profile_dir):
            os.makedirs(chrome_profile_dir)

        chrome_version = self._get_chrome_version()
        self._clean_mismatched_chromedriver(chrome_version)

        chrome_options = uc.ChromeOptions()
        chrome_options.add_argument(f"--user-data-dir={chrome_profile_dir}")
        chrome_options.add_argument("--profile-directory=Default")

        self.update_status(f"{profile_name}: กำลังเปิด Chrome ให้ Login ด้วยมือ...", "blue")
        driver = uc.Chrome(options=chrome_options, use_subprocess=True, version_main=chrome_version)

        try:
            # หน่วงหลังเปิด Chrome ก่อนยิงเข้า Facebook (เปิดปุ๊บวิ่งปั๊บดูเป็นบอท)
            time.sleep(random.uniform(5, 9))
            driver.get("https://www.facebook.com/login")
            time.sleep(random.uniform(3, 6))

            # กด OK = ผู้ใช้บอกว่า Login เสร็จแล้ว ให้บันทึกเลย (เคยเป็นแค่กล่องข้อความ กดแล้วไม่มีอะไรเกิดขึ้น)
            ok_pressed = threading.Event()

            def ask_done(text):
                messagebox.showinfo("Login ด้วยตัวเอง", text)
                ok_pressed.set()

            self.root.after(0, lambda: ask_done(
                f"กรุณา Login Facebook ในหน้าต่าง Chrome ที่เปิดขึ้น ({profile_name})\n\n"
                "เข้าหน้า Facebook ได้แล้วกด OK เพื่อบันทึก Cookie"
            ))

            # รอ Login สูงสุด 10 นาที ดูจาก Cookie c_user + หน้าไม่มีช่องรหัสผ่าน ไม่ดูคำว่า login ใน URL
            # เคยดู URL: หน้าหลัง Login บางหน้ามีคำว่า login (เช่นหน้าจำอุปกรณ์) โปรแกรมเลยรอจนผู้ใช้ปิด Chrome
            # แล้วขึ้นว่า Login ไม่สำเร็จ ทั้งที่เข้าได้แล้ว
            max_wait = 600
            waited = 0
            stable = 0
            cookies = None  # Cookie ชุดล่าสุดตอนที่ Login อยู่ ปิด Chrome ไปแล้วก็ยังบันทึกชุดนี้ได้
            while waited < max_wait:
                time.sleep(2)
                waited += 2
                try:
                    current_url = driver.current_url.lower()
                    now = driver.get_cookies()
                    on_login_form = bool(driver.find_elements(By.NAME, "pass"))
                except Exception:
                    break  # ปิด Chrome แล้ว

                # หน้ายืนยันตัวตน (checkpoint / ยืนยัน 2 ชั้น) มี c_user แล้วแต่ยังใช้ไม่ได้ ห้ามเก็บ
                # ไม่งั้นกด OK หรือปิด Chrome กลางทาง = ทับ .ini ด้วย session ที่เปิดมาก็ติด checkpoint (FBMKP ใช้ไฟล์เดียวกัน)
                verifying = any(k in current_url for k in (
                    'checkpoint', 'two_step_verification', 'auth_platform', 'afad', 'confirmemail', 'recover'))
                logged_in = any(c.get('name') == 'c_user' for c in now) and not on_login_form and not verifying
                if logged_in:
                    cookies = now

                if ok_pressed.is_set():
                    if cookies:
                        break
                    ok_pressed.clear()
                    self.root.after(0, lambda: ask_done(
                        f"{profile_name} ยังไม่ได้ Login หรือยังยืนยันตัวตนไม่เสร็จ\n\n"
                        "ทำในหน้าต่าง Chrome ให้เสร็จก่อน แล้วกด OK อีกครั้ง"))

                # ต้องนิ่งติดกัน 3 รอบ (6 วินาที) ถึงนับว่าเสร็จจริง
                if logged_in:
                    stable += 1
                    if stable >= 3:
                        break
                else:
                    stable = 0
                    self.update_status(f"{profile_name}: รอ Login / ยืนยันตัวตนใน Chrome...", "orange")

            if not cookies:
                raise Exception("ยังไม่ได้ Login (หมดเวลา 10 นาที หรือปิด Chrome ก่อน Login / ยืนยันตัวตนเสร็จ)")

            # เผื่อเวลาให้ Facebook ตั้ง Cookie ชุดสุดท้ายให้ครบก่อนบันทึก (ถ้า Chrome ยังเปิดอยู่)
            try:
                time.sleep(random.uniform(3, 5))
                now = driver.get_cookies()
                if any(c.get('name') == 'c_user' for c in now):
                    cookies = now
            except Exception:
                pass

            self._write_cookies_to_ini(config_file_path, cookies)
            self.update_status(f"{profile_name}: บันทึก Cookie สำเร็จ", "green")
            self.root.after(0, lambda: messagebox.showinfo("สำเร็จ", f"บันทึก Cookie ของ {profile_name} แล้ว\nครั้งต่อไปไม่ต้อง Login ซ้ำ"))
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    def open_auto_cookie_login_browser(self):
        """เปิด Chrome อัตโนมัติสำหรับทุก Profile ที่เลือก แล้ว Login ด้วย Cookie จากไฟล์ .ini"""
        selected_indices = self.profile_listbox.curselection()

        if not selected_indices:
            messagebox.showwarning("คำเตือน", "กรุณาเลือก Profile ที่ต้องการ Login ด้วย Cookie")
            return

        profile_names = [self.profile_listbox.get(i) for i in selected_indices]

        # ตรวจว่าทุก Profile มี Cookie ในไฟล์ .ini
        profiles_no_cookie = []
        for pn in profile_names:
            ini_path = self.profiles[pn].get('config_file', '')
            if not ini_path or not os.path.exists(ini_path):
                profiles_no_cookie.append(f"{pn} (ไม่พบไฟล์ .ini)")
                continue
            # ไม่มี Cookie แต่มี UserID/Password ก็ Login ด้วยรหัสได้
            if not self._read_cookies_from_ini(ini_path) and not all(self._read_credentials(ini_path)):
                profiles_no_cookie.append(f"{pn} (ไฟล์ .ini ไม่มีทั้ง Cookie และ UserID/Password)")

        if profiles_no_cookie:
            messagebox.showwarning(
                "บาง Profile ไม่มีข้อมูล Login",
                "Profile ต่อไปนี้ Login ไม่ได้ ข้ามไป:\n\n" +
                "\n".join(profiles_no_cookie) +
                "\n\nใช้ปุ่ม 'Login ด้วยมือ (บันทึก Cookie)' เพื่อบันทึก Cookie ก่อน"
            )
            # กรองเฉพาะที่มี Cookie
            profile_names = [
                pn for pn in profile_names
                if pn not in [p.split(" (")[0] for p in profiles_no_cookie]
            ]
            if not profile_names:
                return

        confirm = messagebox.askyesno(
            "ยืนยัน",
            f"จะเปิด Chrome และ Login ด้วย Cookie อัตโนมัติสำหรับ {len(profile_names)} Profile:\n\n" +
            "\n".join(profile_names) +
            "\n\nCookie ใช้ไม่ได้ จะ Login ด้วย UserID/Password ในไฟล์ .ini ให้แทน\n\nดำเนินการต่อ?"
        )
        if not confirm:
            return

        self.auto_cookie_login_btn.config(state=tk.DISABLED, bg="#9E9E9E", text="กำลัง Login...")
        threading.Thread(
            target=self.run_auto_cookie_login_thread,
            args=(profile_names,),
            daemon=True
        ).start()

    def run_auto_cookie_login_thread(self, profile_names):
        """Thread wrapper สำหรับ auto cookie login หลาย Profile"""
        try:
            self.auto_cookie_login_profiles(profile_names)
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("ผิดพลาด", f"Cookie Login ไม่สำเร็จ: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.auto_cookie_login_btn.config(
                state=tk.NORMAL, bg="#FF9800",
                text="Login ด้วย Cookie อัตโนมัติ (Profile ที่เลือก)"
            ))

    def auto_cookie_login_profiles(self, profile_names):
        """เปิด Chrome ทีละ Profile แล้ว inject Cookie จาก .ini เพื่อ Login — ไม่ต้องพิมพ์ User/Password"""
        total = len(profile_names)
        results = []

        for idx, profile_name in enumerate(profile_names, 1):
            self.update_status(f"[{idx}/{total}] กำลัง Cookie Login: {profile_name}...", "blue")
            driver = None
            try:
                profile_data = self.profiles[profile_name]
                config_file_path = profile_data['config_file']
                chrome_profile_dir = os.path.join(os.getcwd(), profile_data['chrome_profile'])

                if not os.path.exists(config_file_path):
                    raise Exception(f"ไม่พบไฟล์ .ini: {config_file_path}")

                cookies_raw = self._read_cookies_from_ini(config_file_path)

                if not os.path.exists(chrome_profile_dir):
                    os.makedirs(chrome_profile_dir)

                chrome_version = self._get_chrome_version()
                self._clean_mismatched_chromedriver(chrome_version)

                # ตั้งค่า Chrome (ออกจากหน้าต่าง แต่ยังมี viewport ปกติ)
                chrome_options = uc.ChromeOptions()
                chrome_options.add_argument(f"--user-data-dir={chrome_profile_dir}")
                chrome_options.add_argument("--profile-directory=Default")
                chrome_options.add_argument("--window-size=1280,900")

                driver = uc.Chrome(options=chrome_options, use_subprocess=True, version_main=chrome_version)

                # ให้หน้าต่างแสดงบนจอ (ต่างจากโหมด Renew ที่ซ่อนออกนอกจอ)
                driver.set_window_position(100, 100)

                # inject cookies และตรวจ Login — ใช้หน้า Facebook หลัก ไม่ใช่หน้า renew
                # Cookie ผ่าน = ไม่เขียนทับ Cookie เดิม ถ้า inject ไม่ครบ จะทับของดีด้วยของที่ขาด
                # (.ini ของลูกค้าเป็นต้นฉบับชุดเดียว) เขียนทับเฉพาะตอน login ใหม่สำเร็จเท่านั้น
                how = "Cookie"
                if not self._try_cookie_login(driver, cookies_raw):
                    # บอกให้ชัดว่าเข้าด้วยรหัส ลูกค้าเห็น Cookie ไม่ผ่านแล้วขึ้นสำเร็จ จะนึกว่าโปรแกรมโกหก
                    how = "UserID/Password เพราะ Cookie เดิมใช้ไม่ได้ (บันทึก Cookie ชุดใหม่แล้ว)"
                    # Cookie ใช้ไม่ได้ ลอง UserID/Password ใน .ini ต่อเหมือน FBMKP แล้วเก็บ Cookie ชุดใหม่ทับของเสีย
                    user_id, password = self._read_credentials(config_file_path)
                    if not (user_id and password):
                        raise Exception("Cookie หมดอายุ และไฟล์ .ini ไม่มี UserID/Password กรุณา Login ด้วยมือแล้วบันทึก Cookie ใหม่")
                    self.update_status(f"[{idx}/{total}] {profile_name}: Cookie ใช้ไม่ได้ กำลัง Login ด้วยรหัส...", "orange")
                    # ไม่มี Cookie ในไฟล์ = ยังไม่ได้เข้าหน้า Facebook เลย
                    if "facebook.com" not in driver.current_url:
                        driver.get("https://www.facebook.com/")
                        time.sleep(random.uniform(4, 7))
                    self._password_login(driver, profile_name, user_id, password)
                    self._save_cookies_to_ini(driver, config_file_path, force=True)

                self.update_status(f"[{idx}/{total}] {profile_name}: Login สำเร็จด้วย {how}", "green")
                results.append((profile_name, True, how))
                # ไม่ปิด driver — ให้หน้าต่าง Chrome ค้างอยู่ที่หน้า Facebook หลัก
                driver = None

            except Exception as e:
                self.update_status(f"[{idx}/{total}] {profile_name}: {str(e)[:80]}", "red")
                results.append((profile_name, False, str(e)))
            finally:
                # ปิด driver เฉพาะตอน error เท่านั้น (driver=None หมายถึง login สำเร็จ ไม่ต้องปิด)
                if driver:
                    try:
                        driver.quit()
                    except Exception:
                        pass

            # หน่วงเวลาระหว่าง Profile เพื่อไม่ให้เปิดพร้อมกัน
            if idx < total:
                time.sleep(random.uniform(2, 4))

        # สรุปผล
        success = [(r[0], r[2]) for r in results if r[1]]
        failed  = [(r[0], r[2]) for r in results if not r[1]]

        summary_lines = [f"สำเร็จ {len(success)}/{total} Profile"]
        if success:
            summary_lines += [f"  • {n}: เข้าด้วย {how}" for n, how in success]
        if failed:
            summary_lines.append(f"\nล้มเหลว {len(failed)} Profile:")
            summary_lines += [f"  • {n}: {e}" for n, e in failed]

        summary = "\n".join(summary_lines)
        self.root.after(0, lambda: messagebox.showinfo("ผลการ Cookie Login อัตโนมัติ", summary))
        self.update_status(f"Cookie Login เสร็จ: สำเร็จ {len(success)}/{total}", "green" if not failed else "orange")

    def start_renewal(self):
        selected_indices = self.profile_listbox.curselection()
        
        if not selected_indices:
            messagebox.showwarning("คำเตือน", "กรุณาเลือกอย่างน้อย 1 Profile")
            return
        
        if self.is_running:
            messagebox.showwarning("คำเตือน", "กำลังดำเนินการอยู่ กรุณารอให้เสร็จก่อน")
            return
        
        # ดึงชื่อ Profile ที่เลือก
        self.selected_profiles = [self.profile_listbox.get(i) for i in selected_indices]
        
        confirm = messagebox.askyesno(
            "ยืนยัน", 
            f"ต้องการต่ออายุสินค้าสำหรับ {len(self.selected_profiles)} Profile หรือไม่?\n\n" + 
            "\n".join(self.selected_profiles)
        )
        
        if not confirm:
            return
        
        self.is_running = True
        self.update_status(f"เริ่มต่ออายุ {len(self.selected_profiles)} Profile...", "blue")
        
        # ล็อคปุ่มระหว่างทำงาน (ล็อคปุ่มตอบแชทด้วย กันชนกันบน Profile เดียวกัน)
        self.start_button.config(state=tk.DISABLED, bg="#9E9E9E", text="กำลังทำงาน...")
        self.delete_btn.config(state=tk.DISABLED)
        self.reply_start_btn.config(state=tk.DISABLED, bg="#9E9E9E")

        # รันใน thread แยก
        thread = threading.Thread(target=self.run_renewal_thread, daemon=True)
        thread.start()
    
    def run_renewal_thread(self):
        try:
            self.renew_multiple_profiles()
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}"))
            self.root.after(0, lambda: self.update_status("เกิดข้อผิดพลาด", "red"))
        finally:
            self.is_running = False
            # ปลดล็อคปุ่มเมื่อเสร็จ
            self.root.after(0, lambda: self.start_button.config(
                state=tk.NORMAL, bg="#4CAF50", text="เริ่มต่ออายุสินค้า (Profile ที่เลือก)"
            ))
            self.root.after(0, lambda: self.delete_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.reply_start_btn.config(state=tk.NORMAL, bg="#2196F3"))
    
    def update_status(self, text, color):
        """อัปเดตสถานะอย่างปลอดภัยจาก thread"""
        self.root.after(0, lambda: self.status_label.config(text=text, fg=color))
    
    def renew_multiple_profiles(self):
        """ต่ออายุหลาย Profile แบบขนานกัน"""
        total_profiles = len(self.selected_profiles)
        
        # รีเซ็ตสถานะ (ถ้ายังไม่มีจะสร้างใหม่)
        if not hasattr(self, 'drivers'):
            self.drivers = []
        if not hasattr(self, 'profile_status'):
            self.profile_status = {}
        
        # เคลียร์ค่าเก่า
        self.drivers.clear()
        self.profile_status.clear()
        
        # ล้าง _next_rest_ ของทุก Profile เพื่อให้เริ่มนับใหม่ทุกรอบ
        for key in list(self.__dict__.keys()):
            if key.startswith('_next_rest_'):
                delattr(self, key)
        
        # เริ่มต้นสถานะ
        for profile_name in self.selected_profiles:
            self.profile_status[profile_name] = {
                'driver': None,
                'stage': 'waiting',  # waiting, logging_in, renewing, completed, failed
                'renewed_count': 0,
                'error': None,
                'hard_refresh_count': 0,  # นับจำนวนครั้งที่ Hard refresh
                'hard_refresh_reason': None  # เก็บสาเหตุที่ต้อง Hard refresh
            }
        
        try:
            # เปิด Chrome และล็อคอินทีละตัว รอให้ถึงหน้า Renew ก่อนเปิดตัวถัดไป
            for index, profile_name in enumerate(self.selected_profiles, 1):
                self.update_status(f"[{index}/{total_profiles}] กำลังเปิด Chrome สำหรับ: {profile_name}", "blue")
                
                try:
                    self.profile_status[profile_name]['stage'] = 'logging_in'
                    driver = self.open_and_login_profile(profile_name)
                    
                    if driver:
                        self.profile_status[profile_name]['driver'] = driver
                        self.profile_status[profile_name]['stage'] = 'renewing'
                        self.drivers.append(driver)
                        
                        self.update_status(f"[{index}/{total_profiles}] {profile_name} พร้อมต่ออายุ", "green")
                    else:
                        raise Exception("ไม่สามารถเปิด Chrome ได้")
                    
                    # หน่วงเวลาเล็กน้อยก่อนเปิดตัวถัดไป — สุ่มให้ดูเป็นธรรมชาติ
                    if index < total_profiles:
                        gap = random.uniform(4, 12)
                        time.sleep(gap)
                        
                except Exception as e:
                    self.profile_status[profile_name]['stage'] = 'failed'
                    self.profile_status[profile_name]['error'] = str(e)
                    self.update_status(f"[{index}/{total_profiles}] ล้มเหลว: {profile_name} - {str(e)}", "red")
                    
                    # ถ้า Profile นี้ล้มเหลว ให้ดำเนินการต่อกับ Profile ถัดไป
                    continue
            
            # ตรวจสอบว่ามี Profile ที่พร้อมต่ออายุหรือไม่
            ready_profiles = [pn for pn in self.selected_profiles if self.profile_status[pn]['stage'] == 'renewing']
            
            if not ready_profiles:
                self.update_status("ไม่มี Profile ที่พร้อมต่ออายุ", "red")
                return
            
            # ตอนนี้ทุก Profile ที่สำเร็จเปิดและอยู่ที่หน้า Renew แล้ว เริ่มต่ออายุพร้อมกัน
            self.update_status(f"กำลังต่ออายุ {len(ready_profiles)} Profile พร้อมกัน...", "blue")
            
            # สร้าง thread สำหรับแต่ละ Profile
            threads = []
            for profile_name in ready_profiles:
                thread = threading.Thread(
                    target=self.renew_profile_worker,
                    args=(profile_name,),
                    daemon=True
                )
                threads.append(thread)
                thread.start()
            
            # รอให้ทุก thread เสร็จ
            for thread in threads:
                thread.join()
            
            # รวบรวมผลลัพธ์
            results = []
            for profile_name in self.selected_profiles:
                status = self.profile_status[profile_name]
                if status['stage'] == 'completed':
                    results.append({
                        'profile': profile_name,
                        'success': True,
                        'count': status['renewed_count']
                    })
                else:
                    results.append({
                        'profile': profile_name,
                        'success': False,
                        'error': status.get('error', 'ไม่ทราบสาเหตุ')
                    })
            
            # แสดงสรุปผล
            self.show_summary(results)
            
        except Exception as e:
            self.update_status(f"เกิดข้อผิดพลาดร้ายแรง: {str(e)}", "red")
    
    def show_summary(self, results):
        """แสดงสรุปผลการต่ออายุ"""
        success_count = sum(1 for r in results if r['success'])
        fail_count = len(results) - success_count
        total_renewed = sum(r.get('count', 0) for r in results if r['success'])
        
        summary = f"สรุปผลการต่ออายุ\n"
        summary += f"{'='*50}\n"
        summary += f"Profile ทั้งหมด: {len(results)}\n"
        summary += f"สำเร็จ: {success_count} | ล้มเหลว: {fail_count}\n"
        summary += f"ต่ออายุทั้งหมด: {total_renewed} รายการ\n\n"
        
        for r in results:
            if r['success']:
                profile_name = r['profile']
                count = r['count']
                
                # แสดงข้อมูล Hard refresh ถ้ามี
                hard_refresh_info = ""
                if profile_name in self.profile_status:
                    status = self.profile_status[profile_name]
                    if status.get('hard_refresh_count', 0) > 0:
                        reason = status.get('hard_refresh_reason', 'Unknown')
                        hard_refresh_info = f" ⚠️ (Hard refresh {status['hard_refresh_count']}x: {reason})"
                
                summary += f"✓ {profile_name}: {count} รายการ{hard_refresh_info}\n"
            else:
                error_msg = r.get('error', 'ไม่ทราบสาเหตุ')
                # ตัดข้อความ error ให้สั้นลง
                if len(error_msg) > 100:
                    error_msg = error_msg[:100] + "..."
                summary += f"✗ {r['profile']}: {error_msg}\n"
        
        self.update_status(f"เสร็จสิ้นทั้งหมด! ({success_count}/{len(results)} สำเร็จ)", "green")
        self.root.after(0, lambda: messagebox.showinfo("สรุปผล", summary))
    
    def _get_chrome_version(self):
        """ตรวจจับ Chrome version ที่ติดตั้งอยู่บนเครื่องอัตโนมัติ"""
        import winreg
        paths = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
        ]
        chrome_exe = None
        for path in paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                chrome_exe = winreg.QueryValue(key, None)
                winreg.CloseKey(key)
                break
            except Exception:
                pass

        if chrome_exe and os.path.exists(chrome_exe):
            try:
                import subprocess
                result = subprocess.run(
                    ['powershell', '-command',
                     f'(Get-Item "{chrome_exe}").VersionInfo.FileVersion'],
                    capture_output=True, text=True, timeout=5
                )
                version_str = result.stdout.strip()
                if version_str:
                    major = int(version_str.split('.')[0])
                    return major
            except Exception:
                pass
        return None

    def _clean_mismatched_chromedriver(self, chrome_version):
        """ลบ ChromeDriver ที่ version ไม่ตรงกับ Chrome ออกอัตโนมัติ"""
        if not chrome_version:
            return
        try:
            import winreg
            driver_path = os.path.join(
                os.environ.get('APPDATA', ''),
                'undetected_chromedriver',
                'undetected_chromedriver.exe'
            )
            if os.path.exists(driver_path):
                from win32api import GetFileVersionInfo, LOWORD, HIWORD
                try:
                    info = GetFileVersionInfo(driver_path, "\\")
                    ms = info['FileVersionMS']
                    driver_major = HIWORD(ms)
                except Exception:
                    # fallback: อ่าน version จาก PowerShell
                    import subprocess
                    result = subprocess.run(
                        ['powershell', '-command',
                         f'(Get-Item "{driver_path}").VersionInfo.FileVersion'],
                        capture_output=True, text=True, timeout=5
                    )
                    ver_str = result.stdout.strip()
                    driver_major = int(ver_str.split('.')[0]) if ver_str else None

                if driver_major and driver_major != chrome_version:
                    os.remove(driver_path)
                    print(f"ลบ ChromeDriver v{driver_major} (ไม่ตรงกับ Chrome v{chrome_version})")
        except Exception as e:
            print(f"_clean_mismatched_chromedriver: {e}")

    def _read_cookies_from_ini(self, ini_path):
        """อ่านค่า Cookies จากไฟล์ .ini แบบ raw (ไม่ผ่าน configparser) เหมือน FBMKP"""
        try:
            with open(ini_path, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(
                r'(?im)^\s*cookies\s*=\s*(.*?)(?=^\s*[a-zA-Z_]\w*\s*=|\[|\Z)',
                content, re.MULTILINE | re.DOTALL
            )
            if match:
                raw = match.group(1).strip()
                return raw or None
        except Exception:
            pass
        return None

    def _parse_cookies_to_list(self, raw_cookies):
        """แปลงค่า Cookies ที่อ่านจาก .ini ให้เป็น list of dict สำหรับ Selenium add_cookie
        รองรับ: base64 JSON, JSON array/object ตรงๆ, หรือ cookie header string "key=value; key2=value2" """
        if not raw_cookies:
            return None

        def _from_header(s):
            cookies = []
            for part in s.split(';'):
                part = part.strip()
                if '=' not in part:
                    continue
                name, _, value = part.partition('=')
                name, value = name.strip(), value.strip()
                if name:
                    cookies.append({'name': name, 'value': value})
            return cookies or None

        def _normalize(raw):
            raw = raw.strip()
            try:
                data = json.loads(raw)
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return [{'name': k, 'value': v} for k, v in data.items()]
            except Exception:
                pass
            if '=' in raw and ';' in raw:
                return _from_header(raw)
            return None

        result = _normalize(raw_cookies)
        if result:
            return result

        try:
            decoded = base64.b64decode(raw_cookies.encode('ascii')).decode('utf-8')
            result = _normalize(decoded)
            if result:
                return result
        except Exception:
            pass

        return None

    def save_and_test_telegram(self):
        """บันทึก Token/Chat ID แล้วยิงข้อความทดสอบ จะได้รู้ตั้งแต่ตอนตั้งค่าว่าใช้ได้ไหม"""
        self.telegram_token = self.tg_token_entry.get().strip()
        self.telegram_chat_id = self.tg_chat_entry.get().strip()
        self.save_reply_settings()

        if not self.telegram_token:
            messagebox.showwarning("คำเตือน", "กรุณากรอก Telegram Token")
            return

        def _worker():
            # คนที่เพิ่งทักบอทถูกเพิ่มตรงนี้ แล้วได้ข้อความทดสอบไปด้วยเลย
            self.add_new_telegram_chats(force=True)
            ok, err = self.send_telegram("ทดสอบการแจ้งเตือนจากโปรแกรมต่ออายุสินค้า Facebook")
            if ok:
                note = f"\n\nแต่ส่งไม่ถึง {err}" if err else ""
                self.root.after(0, lambda: messagebox.showinfo("สำเร็จ", f"ส่งข้อความทดสอบแล้ว เช็คใน Telegram ได้เลย{note}"))
            else:
                self.root.after(0, lambda: messagebox.showerror("ส่งไม่สำเร็จ", f"ส่งข้อความทดสอบไม่ได้\n\n{err}"))

        threading.Thread(target=_worker, daemon=True).start()

    def save_stage_choice(self):
        """ติ๊ก/เอาติ๊กออกแล้วบันทึกทันที — มีผลกับรอบสแกนถัดไปโดยไม่ต้องกดหยุดแล้วเริ่มใหม่"""
        self.stage_enabled = {c: bool(v.get()) for c, v in self.stage_vars.items()}
        self.save_reply_settings()
        on = [self.STAGE_LABELS[c] for c in self.ALL_STAGES if self.stage_enabled.get(c)]
        self.update_status("ตอบออโต้ด้วย: " + (", ".join(on) if on else "ไม่ตอบอะไรเลย (แจ้งเตือนอย่างเดียว)"), "blue")

    def save_renew_choice(self):
        """ติ๊ก/แก้นาทีแล้วบันทึกทันที — มีผลรอบถัดไป ไม่ต้องกดหยุดแล้วเริ่มใหม่"""
        self.renew_while_reply = bool(self.renew_while_reply_var.get())
        self.renew_interval_min = self.clean_interval(self.renew_interval_entry.get())
        self.renew_interval_entry.delete(0, tk.END)
        self.renew_interval_entry.insert(0, str(self.renew_interval_min))
        self.save_reply_settings()
        if self.renew_while_reply:
            self.update_status(f"ระหว่างเฝ้าแชท จะต่ออายุสินค้าให้ทุก {self.renew_interval_min} นาที", "blue")
        else:
            self.update_status("ระหว่างเฝ้าแชท ไม่ต่ออายุสินค้าให้", "blue")

    def clean_interval(self, raw):
        """ช่องนาทีลูกค้าพิมพ์เอง ว่าง/ตัวอักษร/0 = ใช้ค่าเริ่มต้น ไม่ใช่พัง"""
        try:
            minutes = int(str(raw).strip())
        except (TypeError, ValueError):
            return self.DEFAULT_RENEW_INTERVAL_MIN
        return minutes if minutes >= 1 else self.DEFAULT_RENEW_INTERVAL_MIN

    def renew_due(self, last_renew_ts, now=None):
        """ถึงเวลาต่ออายุรอบถัดไปหรือยัง (เอาติ๊กออก = หยุดต่อตั้งแต่รอบถัดไป)"""
        if not getattr(self, 'renew_while_reply', False):
            return False
        now = time.time() if now is None else now
        return now - last_renew_ts >= self.clean_interval(self.renew_interval_min) * 60

    def build_notify_text(self, profile_name, product, status, listing_name="", message=""):
        """ข้อความแจ้งเตือนลูกค้าทักเข้า — บอกว่ามาจากเฟสไหนเป็นอันดับแรก (ลูกค้ามี 20 เฟส)"""
        lines = [
            "มีลูกค้าทักมา",
            f"เฟส: {profile_name}",
            f"สินค้า: {product or '(ไม่รู้ชื่อสินค้า)'}",
        ]
        if message:
            lines.append(f"ลูกค้าพิมพ์: {message}")
        if status == 'replied':
            lines.append("สถานะ: ตอบอัตโนมัติให้แล้ว")
        elif status == 'followup':
            lines.append(f"สถานะ: ลูกค้าทักกลับมา ส่ง{self.STAGE_LABELS.get(listing_name, listing_name)}ให้แล้ว")
        elif status == 'followup_done':
            lines.append("สถานะ: ลูกค้าทักกลับมา ส่งข้อมูลครบทุกโฟลเดอร์แล้ว ต้องตอบเอง")
        elif status == 'folder_missing':
            lines.append("สถานะ: ลูกค้าทักกลับมา แต่หาโฟลเดอร์สินค้านี้ไม่เจอแล้ว ต้องตอบเอง")
        elif status == 'unmatched_again':
            lines.append("สถานะ: ลูกค้าทักมาอีก จับคู่สินค้าไม่ได้ตั้งแต่แรก ต้องตอบเอง")
        elif status == 'send_failed':
            lines.append("สถานะ: โปรแกรมส่งข้อมูลให้ลูกค้าไม่สำเร็จ ต้องตอบเอง")
        elif status == 'quick_reply':
            lines.append("สถานะ: ลูกค้าตอบกลับมาหลังได้ข้อมูล ยังไม่ได้ตอบต่อ ต้องตอบเอง")
        elif status == 'old_chat':
            lines.append("สถานะ: ลูกค้าพิมพ์มาในแชทที่คุยกันอยู่แล้ว ไม่ได้ตอบออโต้ ต้องตอบเอง")
        elif status == 'main_off':
            lines.append("สถานะ: ปิดตอบออโต้ด้วยแชทหลักไว้ ยังไม่ได้ส่งอะไร ต้องตอบเอง")
        elif status == 'followup_off':
            lines.append("สถานะ: ลูกค้าทักมาอีก ไม่ได้ตอบให้ (ปิดตอบออโต้ไว้) ต้องตอบเอง")
        else:
            lines.append("สถานะ: ยังไม่ได้ตอบ จับคู่สินค้าไม่ได้ ต้องตอบเอง")
            if listing_name:
                lines.append(f"ชื่อประกาศ: {listing_name}")
        lines.append(f"เวลา: {time.strftime('%d/%m/%Y %H:%M')}")
        return "\n".join(lines)

    def chat_id_list(self):
        """ช่อง Chat ID มีได้หลายแชท คั่นด้วย , — ลบเลขไหนออกจากช่อง แชทนั้นเลิกได้แจ้งเตือน"""
        return [c for c in re.split(r'[,\s]+', getattr(self, 'telegram_chat_id', '') or '') if c]

    def chats_from_updates(self, payload, after=0):
        """แชทที่ทักบอทเข้ามา จากผล getUpdates — คืน ({chat_id: ชื่อ}, เวลาของอันล่าสุด)
        เอาแต่อันที่ใหม่กว่า after ไม่งั้นคนที่ลบออกจากช่อง Chat ID ไปแล้วเด้งกลับมาเองทุกรอบ
        (เทียบด้วยเวลา ไม่ใช้ update_id เพราะบอทเงียบเกินสัปดาห์ Telegram สุ่มเลข update_id ใหม่)"""
        found, newest = {}, after
        for update in (payload or {}).get('result') or []:
            member = update.get('my_chat_member')
            # โดนเตะออกจากกลุ่ม/โดนบล็อก ก็มาทาง my_chat_member เหมือนตอนถูกดึงเข้ากลุ่ม
            if member and (member.get('new_chat_member') or {}).get('status') not in ('member', 'administrator'):
                continue
            event = update.get('message') or member or {}
            chat, date = event.get('chat') or {}, event.get('date') or 0
            if chat.get('id') is None or date <= after:
                continue
            found[str(chat['id'])] = chat.get('title') or chat.get('first_name') or chat.get('username') or ''
            newest = max(newest, date)
        return found, newest

    def merge_telegram_chats(self, payload):
        """เอาคนที่ทักบอทเข้ามาใส่ช่อง Chat ID — คืน {chat_id: ชื่อ} เฉพาะคนที่เพิ่งเพิ่ม"""
        with self.TELEGRAM_LOCK:
            found, self.telegram_seen = self.chats_from_updates(payload, getattr(self, 'telegram_seen', 0))
            known = self.chat_id_list()
            new = {c: name for c, name in found.items() if c not in known}
            if new:
                self.telegram_chat_id = ", ".join(known + list(new))
            return new

    def add_new_telegram_chats(self, force=False):
        """ใครทักบอทเข้ามา เพิ่มเข้าช่อง Chat ID ให้เอง ไม่ต้องเปิด getUpdates หาเลขมากรอก
        ไม่ส่ง offset = ไม่ลบคิวฝั่ง Telegram เพราะ exe ทุกเครื่องใช้บอทตัวเดียวกัน เครื่องไหนลบ เครื่องอื่นไม่เห็น"""
        token = (getattr(self, 'telegram_token', '') or '').strip()
        if not token:
            return
        # 20 เฟสแจ้งเตือนถี่ๆ ไม่ต้องถาม Telegram ทุกอัน (ถามซ้อนกันโดน 409) ปุ่มทดสอบส่งใช้ force เช็คทันที
        with self.TELEGRAM_LOCK:
            if not force and time.time() - getattr(self, 'telegram_polled', 0) < 60:
                return
            self.telegram_polled = time.time()
        # ponytail: getUpdates ให้แค่ 100 อันเก่าสุดที่ค้างใน 24 ชม. มีคนพิมพ์ใส่บอทเกินนั้นคนใหม่จะเข้าช้า ถึงตอนนั้นค่อยไล่ด้วย offset
        try:
            with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/getUpdates", timeout=10) as resp:
                new = self.merge_telegram_chats(json.load(resp))
        except Exception:
            return
        if not new:
            return
        self.save_reply_settings()

        # ช่องใน GUI ต้องตามให้ทัน ไม่งั้นกดบันทึกรอบหน้าเอาค่าเก่าในช่องมาทับ คนใหม่หาย
        def _show():
            self.tg_chat_entry.delete(0, tk.END)
            self.tg_chat_entry.insert(0, self.telegram_chat_id)
        self.root.after(0, _show)

        for chat_id, name in new.items():
            self.send_telegram(f"เพิ่ม {name or 'แชทใหม่'} ({chat_id}) เข้ารับแจ้งเตือนแล้ว\n"
                               "ถ้าไม่ใช่คนของเรา ลบเลขนี้ออกจากช่อง Chat ID ในโปรแกรมแล้วกดบันทึก")

    def send_telegram(self, text):
        """ยิงข้อความเข้า Telegram bot ทุกแชทในช่อง Chat ID — ใช้ urllib (ไม่ต้องลง requests เพิ่มตอน build exe)
        คืน (ส่งถึงอย่างน้อย 1 แชท, error อันแรก) ไม่ throw เพราะห้ามให้แจ้งเตือนล้มแล้วลากการตอบแชทพังตาม"""
        token = (getattr(self, 'telegram_token', '') or '').strip()
        chat_ids = self.chat_id_list()
        if not token or not chat_ids:
            return False, "ยังไม่ได้ตั้งค่า Token หรือ Chat ID (ทักบอทใน Telegram 1 ข้อความ แล้วกดใหม่)"

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        sent, first_err = False, ""
        for chat_id in chat_ids:
            data = urllib.parse.urlencode({'chat_id': chat_id, 'text': text}).encode('utf-8')
            # คนนึงบล็อกบอท/ออกจากกลุ่มไปแล้ว คนที่เหลือต้องได้แจ้งเตือนเหมือนเดิม
            try:
                with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as resp:
                    sent = sent or resp.status == 200
            except Exception as e:
                first_err = first_err or f"แชท {chat_id}: {str(e)[:100]}"
        return sent, first_err

    def notify_new_chat(self, profile_name, product, status, listing_name="", message=""):
        """ส่งแจ้งเตือนแบบไม่บล็อก — การตอบแชทต้องเดินต่อได้แม้เน็ต Telegram ล่ม"""
        if not getattr(self, 'telegram_token', ''):
            return
        text = self.build_notify_text(profile_name, product, status, listing_name, message)

        def _worker():
            self.add_new_telegram_chats()
            ok, err = self.send_telegram(text)
            # exe ไม่มีหน้า CMD ให้ดู print ไปก็ไม่มีใครเห็น ต้องขึ้นบรรทัดสถานะ
            if err:
                self.update_status(f"แจ้งเตือน Telegram ไม่สำเร็จ: {err}", "red")

        threading.Thread(target=_worker, daemon=True).start()

    def notify_problem(self, profile_name, problem):
        """เฟสนี้เลิกเฝ้าแชทเองโดยไม่มีใครสั่ง — ไม่แจ้ง = เจ้าของนึกว่ายังเฝ้าอยู่ ลูกค้าทักมาก็เงียบ"""
        self.update_status(f"{profile_name}: {problem}", "red")
        text = "\n".join(["โปรแกรมมีปัญหา", f"เฟส: {profile_name}", problem,
                          f"เวลา: {time.strftime('%d/%m/%Y %H:%M')}"])
        threading.Thread(target=self.send_telegram, args=(text,), daemon=True).start()

    def _is_login_pending_url(self, url):
        """URL ที่ยังถือว่า Login ไม่เสร็จ — หน้า login เอง หรือหน้ายืนยันตัวตนของ Facebook"""
        url = (url or "").lower()
        pending = ('login', 'checkpoint', 'two_step_verification', 'confirmemail',
                   'recover', 'authentication', 'challenge')
        return any(p in url for p in pending)

    def _is_logged_in(self, driver):
        """เข้า Facebook อยู่จริงไหม: มี Cookie c_user + หน้าไม่มีช่องอีเมล/รหัส + ไม่ติดหน้ายืนยันตัวตน
        เคยดูแค่ว่าไม่มีช่องอีเมล หน้าไหนที่ไม่ใช่ฟอร์ม Login (เช่นหน้าเลือกบัญชี) ก็นับว่าเข้าแล้ว
        ลูกค้าเลยเห็น Login สำเร็จ ทั้งที่ Chrome ยังไม่ได้เข้า ไม่ดูคำว่า login ใน URL เพราะหน้าจำอุปกรณ์หลัง Login ก็มี"""
        try:
            url = (driver.current_url or "").lower()
            if any(k in url for k in ('checkpoint', 'two_step_verification', 'auth_platform', 'afad',
                                      'confirmemail', 'recover')):
                return False
            if driver.find_elements(By.NAME, "email") or driver.find_elements(By.NAME, "pass"):
                return False
            return bool(driver.get_cookie('c_user'))
        except Exception:
            return False

    def _build_selenium_cookie(self, c):
        """แปลง cookie dict (ฟอร์แมต Playwright ของ FBMKP) เป็นฟอร์แมตที่ Selenium add_cookie รับ
        ต้องส่ง secure ไปด้วย — Chrome ตีตก cookie ที่ SameSite=None แต่ไม่มี Secure
        (xs / c_user ของ Facebook เป็นแบบนั้น ถ้าตกไปคือ login ไม่ติด)"""
        name = c.get('name')
        value = c.get('value')
        if not name or value is None:
            return None

        cookie = {
            'name': name,
            'value': value,
            'domain': c.get('domain') or '.facebook.com',
            'path': c.get('path') or '/',
            'secure': bool(c.get('secure', False)),
            'httpOnly': bool(c.get('httpOnly', False)),
        }

        expiry = c.get('expiry', c.get('expires'))
        if isinstance(expiry, (int, float)) and expiry > 0:
            cookie['expiry'] = int(expiry)

        same_site = c.get('sameSite')
        if same_site in ('Strict', 'Lax', 'None'):
            # SameSite=None บังคับต้อง Secure ไม่งั้น Chrome ตีตกทั้งตัว
            if same_site == 'None':
                cookie['secure'] = True
            cookie['sameSite'] = same_site

        return cookie

    def _try_cookie_login(self, driver, cookies_raw):
        """Inject Cookies เข้า driver แล้วเช็คว่า Login ผ่านไหม (เหมือน FBMKP แต่พอร์ตมาใช้กับ Selenium)"""
        cookies_list = self._parse_cookies_to_list(cookies_raw)
        if not cookies_list:
            return False

        # ต้องอยู่โดเมน facebook.com ก่อนถึงจะ add_cookie ได้ (ข้อจำกัดของ Selenium)
        # ถ้าอยู่แล้วไม่ต้องโหลดซ้ำ — ผู้ใช้เห็นเป็นการรีเฟรชหน้าเปล่าๆ
        try:
            on_facebook = "facebook.com" in driver.current_url
        except Exception:
            on_facebook = False
        if not on_facebook:
            driver.get("https://www.facebook.com/")
        time.sleep(random.uniform(1.5, 3.0))

        rejected = []
        for c in cookies_list:
            cookie = self._build_selenium_cookie(c)
            if not cookie:
                continue
            try:
                driver.add_cookie(cookie)
            except Exception as e:
                rejected.append(f"{cookie['name']}: {str(e)[:60]}")

        # เทียบว่า cookie ที่ตั้งใจใส่ เข้าไปจริงกี่ตัว — ตัวที่ Chrome ตีตกจะไม่โผล่
        want = {c.get('name') for c in cookies_list if c.get('name')}
        try:
            got = {c['name'] for c in driver.get_cookies()}
        except Exception:
            got = set()
        missing = sorted(want - got)
        key_missing = [n for n in ('c_user', 'xs') if n in want and n not in got]

        self.update_status(
            f"Cookie: ใส่ได้ {len(want & got)}/{len(want)}" +
            (f" | ขาด {', '.join(missing[:6])}" if missing else ""),
            "orange" if missing else "blue"
        )
        if rejected:
            print("cookie rejected:", "; ".join(rejected[:10]))
        if key_missing:
            print(f"cookie สำคัญหายไป: {key_missing} — Chrome ตีตก (เช็ค secure/sameSite)")

        if not (want & got):
            return False

        # โหลดหน้าหลัก Facebook รอบเดียวเพื่อให้ Cookie มีผล แล้วเช็คว่าเข้าได้จริง
        # (ไม่ยิงไปหน้าปลายทางตรงนี้ ปล่อยให้ตัวเรียกเดินทางแบบคนจริงต่อเอง)
        time.sleep(random.uniform(1.0, 2.0))
        driver.get("https://www.facebook.com/")
        time.sleep(random.uniform(4, 7))

        try:
            if self._is_login_pending_url(driver.current_url):
                return False
        except Exception:
            return False

        return self._is_logged_in(driver)

    def _read_credentials(self, ini_path):
        """UserID, Password จาก section [FBAccount] (ไม่มี = ค่าว่าง)
        ปิด interpolation เหมือน FBMKP ไม่งั้นรหัสที่มี % อ่านไม่ขึ้น"""
        config = configparser.ConfigParser(interpolation=None)
        config.read(ini_path, encoding='utf-8')
        return (config.get('FBAccount', 'UserID', fallback='').strip(),
                config.get('FBAccount', 'Password', fallback='').strip())

    def _password_login(self, driver, profile_name, user_id, password):
        """กรอก UserID/Password จาก .ini ในหน้า Login ของ Facebook แล้วรอผ่านหน้ายืนยันตัวตน"""
        self.update_status(f"{profile_name}: กำลังล็อคอิน...", "blue")

        # รอให้ช่อง email ปรากฏ (ใช้ name="email" แทน ID)
        def find_email_field():
            return WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable((By.NAME, "email"))
            )

        try:
            email_field = find_email_field()
        except Exception:
            # Cookie ตายที่เพิ่งลองใส่ยังค้าง Facebook อาจโชว์หน้าอื่นแทนช่องอีเมล ล้าง session เก่าแล้วโหลดใหม่เหมือน FBMKP
            # ลบแค่ c_user / xs เก็บ Cookie อื่นไว้ Facebook จะได้ยังจำเครื่องนี้ได้
            # ยังไม่เจอ = error ของ Selenium ไม่มีข้อความ ผู้ใช้เห็นแค่ชื่อ Profile ว่างๆ ต้องบอกเอง
            try:
                for name in ('c_user', 'xs'):
                    driver.delete_cookie(name)
                driver.get("https://www.facebook.com/")
                time.sleep(random.uniform(4, 7))
                email_field = find_email_field()
            except Exception:
                raise Exception("ไม่เจอช่องกรอกอีเมลของ Facebook (อาจติดหน้ายืนยันตัวตน) ใช้ปุ่ม Login ด้วยมือแทน")

        # เลื่อนหน้าจอไปที่ช่อง email แบบมนุษย์
        self.human_like_scroll_to_element(driver, email_field)
        time.sleep(random.uniform(0.6, 1.2))

        # เคลื่อนเมาส์ไปมาก่อนคลิก (เหมือนกำลังมองหา)
        if random.random() < 0.5:
            self.random_mouse_movement(driver)

        email_field.click()
        time.sleep(random.uniform(0.5, 1.0))
        self.human_like_clear_field(email_field, driver)
        time.sleep(random.uniform(0.3, 0.7))

        # พิมพ์แบบมนุษย์
        self.human_like_type(email_field, user_id, driver)

        time.sleep(random.uniform(0.8, 1.8))

        # กรอก Password (ช่องล่าง)
        password_field = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.NAME, "pass"))
        )

        # เลื่อนหน้าจอไปที่ช่อง password แบบมนุษย์
        self.human_like_scroll_to_element(driver, password_field)
        time.sleep(random.uniform(0.5, 1.0))

        password_field.click()
        time.sleep(random.uniform(0.5, 1.0))
        self.human_like_clear_field(password_field, driver)
        time.sleep(random.uniform(0.3, 0.7))

        # พิมพ์แบบมนุษย์
        self.human_like_type(password_field, password, driver)

        time.sleep(random.uniform(1.0, 2.0))

        # กดปุ่มล็อคอิน - ลองหลายวิธี
        self.update_status(f"{profile_name}: กำลังกดปุ่มล็อคอิน...", "blue")

        # เคลื่อนเมาส์สุ่มก่อนกดปุ่ม
        if random.random() < 0.3:
            self.random_mouse_movement(driver)
            time.sleep(random.uniform(0.3, 0.7))

        login_clicked = False

        # วิธีที่ 1: ใช้ XPath หาจากข้อความ "Log in" หรือ "เข้าสู่ระบบ"
        try:
            login_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//span[text()='Log in' or text()='เข้าสู่ระบบ']"))
            )
            login_button.click()
            login_clicked = True
            self.update_status(f"{profile_name}: กดปุ่มล็อคอินสำเร็จ (วิธีที่ 1)", "green")
        except Exception as e1:
            self.update_status(f"{profile_name}: ลองวิธีที่ 2...", "blue")

            # วิธีที่ 2: หาปุ่มจาก type="submit"
            try:
                login_button = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@type='submit' and @name='login']"))
                )
                login_button.click()
                login_clicked = True
                self.update_status(f"{profile_name}: กดปุ่มล็อคอินสำเร็จ (วิธีที่ 2)", "green")
            except Exception as e2:
                self.update_status(f"{profile_name}: ลองวิธีที่ 3...", "blue")

                # วิธีที่ 3: หาปุ่มจาก data-testid
                try:
                    login_button = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, "//button[@data-testid='royal_login_button']"))
                    )
                    login_button.click()
                    login_clicked = True
                    self.update_status(f"{profile_name}: กดปุ่มล็อคอินสำเร็จ (วิธีที่ 3)", "green")
                except Exception as e3:
                    self.update_status(f"{profile_name}: ลองวิธีที่ 4...", "blue")

                    # วิธีที่ 4: กด Enter ที่ช่อง password
                    try:
                        from selenium.webdriver.common.keys import Keys
                        password_field.send_keys(Keys.RETURN)
                        login_clicked = True
                        self.update_status(f"{profile_name}: กดปุ่มล็อคอินสำเร็จ (วิธีที่ 4)", "green")
                    except Exception as e4:
                        raise Exception(f"ไม่สามารถกดปุ่มล็อคอินได้ทุกวิธี: {str(e1)}, {str(e2)}, {str(e3)}, {str(e4)}")

        if not login_clicked:
            raise Exception("ไม่สามารถกดปุ่มล็อคอินได้")

        # รอให้หน้าเว็บเปลี่ยน
        self.update_status(f"{profile_name}: รอล็อคอินเสร็จ...", "blue")
        time.sleep(random.uniform(5, 8))  # รอแบบสุ่ม

        # จำลองการอ่านหน้าเว็บหลังล็อคอิน
        if random.random() < 0.3:
            self.human_like_scroll(driver, "down")
            time.sleep(random.uniform(0.5, 1.0))

        # ตรวจสอบว่าเจอหน้า error หรือไม่
        current_url = driver.current_url

        try:
            page_source = driver.page_source.lower()
        except:
            page_source = ""

        # ตรวจสอบหน้า ERR_TOO_MANY_REDIRECTS หรือ error อื่นๆ
        if "err_too_many_redirects" in page_source or "this page isn't working" in page_source or "redirected you too many times" in page_source:
            # ลองรีเฟรชหน้าเว็บ
            self.update_status(f"{profile_name}: พบ redirect error กำลังลองใหม่...", "orange")
            driver.get("https://www.facebook.com/")
            time.sleep(5)

            current_url = driver.current_url
            try:
                page_source = driver.page_source.lower()
            except:
                page_source = ""

            # ตรวจสอบอีกครั้ง
            if "err_too_many_redirects" in page_source or "this page isn't working" in page_source:
                raise Exception("Facebook ตรวจพบ automation และบล็อคการเข้าถึง (ERR_TOO_MANY_REDIRECTS)")

        # รอจนเข้าได้จริง หรือเจอหน้ายืนยันตัวตน (Facebook บางทีพาไปหน้าถัดไปช้า เช็คครั้งเดียวไม่พอ)
        # เคย raise ตอนยังอยู่หน้า login ไว้ใน try/except: pass รหัสผิดก็ไม่เคยแจ้ง ขึ้น Login สำเร็จตลอด
        auth_keywords = ["two_step_verification", "checkpoint", "auth_platform/afad", "login/device-based", "login/identify"]
        is_auth_page = False
        for _ in range(15):
            if self._is_logged_in(driver):
                return
            current_url = driver.current_url
            is_auth_page = any(keyword in current_url for keyword in auth_keywords)
            if is_auth_page:
                break
            time.sleep(2)
        else:
            raise Exception("Login ด้วย UserID/Password ไม่สำเร็จ (รหัสผิด หรือ Facebook ไม่ให้เข้า) ใช้ปุ่ม Login ด้วยมือแทน")

        if is_auth_page:
            self.update_status(f"{profile_name}: พบหน้ายืนยันตัวตน", "orange")
            self.root.after(0, lambda pn=profile_name: messagebox.showinfo("ยืนยันตัวตน", f"กรุณายืนยันตัวตนสำหรับ Profile: {pn}\nเมื่อเสร็จแล้วกด OK"))

            # รอจนกว่าจะกลับไปหน้า Facebook หลัก
            max_wait = 300  # รอสูงสุด 5 นาที
            wait_count = 0

            while wait_count < max_wait:
                time.sleep(2)
                wait_count += 2
                current_url = driver.current_url

                # ตรวจสอบว่ากลับไปหน้า Facebook หลักแล้วหรือยัง
                is_still_auth = any(keyword in current_url for keyword in auth_keywords)

                if "facebook.com" in current_url and not is_still_auth:
                    self.update_status(f"{profile_name}: ยืนยันตัวตนสำเร็จ กำลังรอ 10 วินาที...", "green")
                    time.sleep(10)  # รอ 10 วินาทีหลังยืนยันตัวตนเสร็จ
                    break

            if wait_count >= max_wait:
                raise Exception("หมดเวลารอการยืนยันตัวตน")

            # กลับไปหน้า Facebook เริ่มต้นก่อน
            self.update_status(f"{profile_name}: กลับไปหน้า Facebook หลัก...", "blue")
            driver.get("https://www.facebook.com/")
            time.sleep(3)
            if not self._is_logged_in(driver):
                raise Exception("ยืนยันตัวตนแล้วแต่ยังเข้า Facebook ไม่ได้ ใช้ปุ่ม Login ด้วยมือแทน")

    def _save_cookies_to_ini(self, driver, ini_path, force=False):
        """บันทึก Cookies จาก Selenium driver ลงไฟล์ .ini section [FBAccount] (เหมือน FBMKP)
        จะบันทึกเฉพาะเมื่อไฟล์ .ini ยังไม่มี Cookies เท่านั้น เว้นแต่ force=True (ใช้เมื่อ Cookie เก่าหมดอายุแล้ว login ใหม่สำเร็จ)"""
        if not force:
            existing = self._read_cookies_from_ini(ini_path)
            if existing:
                return

        all_cookies = driver.get_cookies()
        if not all_cookies:
            return
        # ไม่มี c_user = ยังไม่ได้ Login จริง เขียนลงไปคือเอา Cookie เปล่าทับของเดิมในไฟล์ .ini ของลูกค้า
        if not any(c.get('name') == 'c_user' for c in all_cookies):
            raise Exception("ยัง Login ไม่สำเร็จ ไม่บันทึก Cookie")

        self._write_cookies_to_ini(ini_path, all_cookies)

    def _write_cookies_to_ini(self, ini_path, cookies):
        """เขียน Cookies ลง .ini ในฟอร์แมตของ FBMKP (Playwright) เพราะ FBMKP อ่านไฟล์เดียวกันนี้
        Selenium เรียกวันหมดอายุว่า expiry แต่ Playwright รู้จักแค่ expires ถ้าเขียน expiry ลงไป
        FBMKP จะได้ Cookie แบบไม่มีวันหมดอายุ ปิด Chrome ทีไร Login ในโปรไฟล์ของ FBMKP หายทุกที"""
        cookies = [{('expires' if k == 'expiry' else k): v for k, v in c.items()}
                   for c in cookies if isinstance(c, dict)]
        cookies_json_str = json.dumps(cookies, ensure_ascii=False)
        cookies_b64 = base64.b64encode(cookies_json_str.encode('utf-8')).decode('ascii')

        with open(ini_path, 'r', encoding='utf-8') as f:
            ini_content = f.read()

        if re.search(r'(?im)^\s*cookies\s*=', ini_content):
            ini_content = re.sub(
                r'(?im)^\s*cookies\s*=.*?(?=^\s*[a-zA-Z_]\w*\s*=|\[|\Z)',
                f'Cookies = {cookies_b64}\n',
                ini_content, count=1, flags=re.MULTILINE | re.DOTALL
            )
        elif '[FBAccount]' in ini_content:
            ini_content = ini_content.replace('[FBAccount]', f'[FBAccount]\nCookies = {cookies_b64}', 1)
        else:
            ini_content += f'\n[FBAccount]\nCookies = {cookies_b64}\n'

        # ไฟล์นี้มีรหัสผ่านของลูกค้าอยู่ด้วย เขียนไฟล์ข้างๆ แล้วสลับ ดับกลางทางไฟล์เดิมยังอยู่ครบ
        tmp_path = ini_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as f:
            f.write(ini_content)
        os.replace(tmp_path, ini_path)

    def fix_ini_cookie_format(self):
        """ไฟล์ .ini ที่เวอร์ชันก่อน v3 เขียนไว้ใช้ key expiry (ดู _write_cookies_to_ini)
        เปิดโปรแกรมมาแก้เป็น expires ให้ครั้งเดียว ค่า Cookie ไม่ถูกแตะ"""
        for profile in self.profiles.values():
            try:
                ini_path = profile.get('config_file', '')
                cookies = self._parse_cookies_to_list(self._read_cookies_from_ini(ini_path))
                if cookies and any(isinstance(c, dict) and 'expiry' in c for c in cookies):
                    self._write_cookies_to_ini(ini_path, cookies)
            except Exception:
                pass

    def open_and_login_profile(self, profile_name, target_url="https://www.facebook.com/marketplace/selling/renew_listings/"):
        """เปิด Chrome และล็อคอินจนถึงหน้าที่ระบุ (ค่าเริ่มต้น: หน้า Renew)"""
        driver = None
        
        try:
            # ดึงข้อมูล Profile
            profile_data = self.profiles[profile_name]
            config_file_path = profile_data['config_file']
            chrome_profile_dir = os.path.join(os.getcwd(), profile_data['chrome_profile'])
            
            # ตรวจสอบว่าไฟล์ยังอยู่หรือไม่
            if not os.path.exists(config_file_path):
                raise Exception(f"ไม่พบไฟล์ {config_file_path}")
            
            user_id, password = self._read_credentials(config_file_path)

            # อ่าน Cookies แบบ raw เพื่อหลีกเลี่ยงปัญหา ; และ % ใน configparser (เหมือน FBMKP)
            cookies_raw = self._read_cookies_from_ini(config_file_path)

            if not (user_id and password) and not cookies_raw:
                raise Exception("ไฟล์ .ini ต้องมีข้อมูล UserID และ Password หรือ Cookies ใน section [FBAccount]")
            
            # สร้างโฟลเดอร์ profile ถ้ายังไม่มี
            if not os.path.exists(chrome_profile_dir):
                os.makedirs(chrome_profile_dir)
            
            # ตั้งค่า Chrome Options พร้อม user profile
            chrome_options = uc.ChromeOptions()
            chrome_options.add_argument(f"--user-data-dir={chrome_profile_dir}")
            chrome_options.add_argument("--profile-directory=Default")
            
            # ไม่ปลอม fingerprint และไม่สุ่มขนาดจอ ใช้ค่าจริงของเครื่อง ให้ตรงกับ Chrome ที่ FBMKP เปิด
            # สองโปรแกรมใช้ session Facebook เดียวกันจากไฟล์ .ini ถ้าที่นี่สุ่มการ์ดจอ/ขนาดจอใหม่ทุกรอบ
            # Facebook จะเห็นเฟสเดียวโผล่จากเครื่องที่หน้าตาเปลี่ยนไปเรื่อยๆ (FBMKP ถอดของพวกนี้ไปแล้วตั้งแต่ ส.ค.)
            # ขนาดหน้าต่างไม่ต้องตั้ง undetected_chromedriver ใส่ --window-size กับ --start-maximized ทับเองอยู่แล้ว

            # หมายเหตุ: ไม่ใส่ --disable-infobars, --disable-popup-blocking, --no-sandbox,
            # --disable-gpu, --disable-dev-shm-usage เพราะเป็น flags ที่ bot ใช้บ่อย
            # คนปกติเปิด Chrome ไม่มี flags พิเศษเหล่านี้
            
            # เปิด Chrome ด้วย Undetected ChromeDriver (ป้องกันการตรวจจับ Bot)
            # หมายเหตุ: ไม่ตั้งค่า user-agent ใน arguments เพราะจะทำให้เกิด URL แปลกๆ
            # ให้ Undetected ChromeDriver จัดการ user-agent ให้อัตโนมัติ
            
            self.update_status(f"{profile_name}: กำลังเปิด Chrome...", "blue")
            
            # ตรวจจับ Chrome version อัตโนมัติ
            chrome_version = self._get_chrome_version()
            if chrome_version:
                self.update_status(f"{profile_name}: พบ Chrome v{chrome_version} กำลังเปิด...", "blue")
            
            # ลบ ChromeDriver เก่าที่ version ไม่ตรงออกอัตโนมัติ
            self._clean_mismatched_chromedriver(chrome_version)
            
            try:
                # เปิด Chrome ด้วย Undetected ChromeDriver ระบุ version ตรงๆ
                driver = uc.Chrome(options=chrome_options, use_subprocess=True, version_main=chrome_version)
                self.update_status(f"{profile_name}: เปิด Chrome สำเร็จ", "green")
            except Exception as chrome_error:
                error_msg = str(chrome_error)
                self.update_status(f"{profile_name}: ไม่สามารถเปิด Chrome ได้", "red")
                
                if "chrome not reachable" in error_msg.lower():
                    raise Exception("Chrome ไม่สามารถเข้าถึงได้ - ลองปิด Chrome ทั้งหมดแล้วลองใหม่")
                elif "session not created" in error_msg.lower():
                    raise Exception(f"Chrome version ไม่ตรงกับ ChromeDriver (Chrome v{chrome_version}) - ลองรันใหม่อีกครั้ง")
                elif "cannot find chrome binary" in error_msg.lower():
                    raise Exception("ไม่พบ Chrome - ตรวจสอบว่าติดตั้ง Chrome แล้ว")
                elif "chrome failed to start" in error_msg.lower():
                    raise Exception("Chrome เปิดไม่สำเร็จ - ลองรีสตาร์ทคอมพิวเตอร์")
                else:
                    raise Exception(f"เปิด Chrome ไม่สำเร็จ: {error_msg[:200]}")
            
            # รอสักครู่ก่อนย้ายหน้าต่าง (คนจริงเปิด Chrome แล้วจะเห็นหน้าต่างอยู่สักพัก)
            time.sleep(random.uniform(1.5, 3.0))
            
            driver.set_window_position(100, 100)

            # รอหลังเปิด Chrome ก่อนเข้า Facebook — สุ่มให้ไม่เป็น pattern
            wait_after_open = random.uniform(14, 25)
            self.update_status(f"{profile_name}: รอ {int(wait_after_open)} วินาทีหลังเปิด Chrome...", "blue")
            time.sleep(wait_after_open)

            # ตรวจสอบว่าล็อคอินอยู่แล้วหรือไม่
            driver.get("https://www.facebook.com/")
            time.sleep(random.uniform(6, 10))  # รอแบบสุ่ม
            
            # จำลองการอ่านหน้าเว็บ
            if random.random() < 0.4:  # 40% โอกาส
                self.human_like_read_page(driver)
            
            # ตรวจสอบว่าอยู่ในหน้า Facebook หลักหรือหน้าล็อคอิน (เคยดูแค่ว่าไม่เจอช่อง email = เข้าแล้ว)
            time.sleep(3)
            is_logged_in = self._is_logged_in(driver)
            if is_logged_in:
                self.update_status(f"{profile_name}: ล็อคอินอยู่แล้ว", "green")
            else:
                self.update_status(f"{profile_name}: ยังไม่ได้ล็อคอิน", "orange")

            # ถ้ายังไม่ได้ล็อคอิน ลอง Login ด้วย Cookie ก่อน (เหมือน FBMKP)
            cookie_expired = False
            if not is_logged_in and cookies_raw:
                self.update_status(f"{profile_name}: กำลังลอง Login ด้วย Cookie...", "blue")
                if self._try_cookie_login(driver, cookies_raw):
                    is_logged_in = True
                    self.update_status(f"{profile_name}: Login ด้วย Cookie สำเร็จ", "green")
                else:
                    cookie_expired = True
                    self.update_status(f"{profile_name}: Cookie หมดอายุหรือไม่ถูกต้อง", "orange")

            # ถ้ายังไม่ได้ล็อคอิน ให้ทำการล็อคอินด้วย User/Password
            if not is_logged_in:
                if not (user_id and password):
                    raise Exception(f"Cookie ของ Profile '{profile_name}' หมดอายุ และไม่มี UserID/Password สำรอง - กรุณา Login ด้วยมือใหม่ (ปุ่ม \"Login ด้วยมือ (บันทึก Cookie)\")")

                self._password_login(driver, profile_name, user_id, password)

            # บันทึก Cookie ใหม่ไว้ใช้ครั้งต่อไป - เขียนทับเฉพาะตอน Cookie เดิมพิสูจน์แล้วว่าหมดอายุ
            # เคยเขียนทับทุกรอบที่ Chrome ล็อคอินค้างอยู่แล้วด้วย (ไม่ได้ลอง Cookie = นับว่าไม่ผ่าน)
            # ไฟล์นี้ FBMKP ใช้ร่วม โดนทับทุกรอบคือ FBMKP ถูกลากมาใช้ session ของโปรแกรมนี้
            try:
                self._save_cookies_to_ini(driver, config_file_path, force=cookie_expired)
            except Exception:
                pass

            # รอ 10-30 วินาทีก่อนไปหน้าต่ออายุ (Session Duration - ทำให้ดูเป็นธรรมชาติ)
            # ย้ายมาไว้หลังล็อคอินเสร็จแล้ว
            wait_before_renew = random.uniform(10, 30)
            self.update_status(f"{profile_name}: รอ {int(wait_before_renew)} วินาทีก่อนเริ่มต่ออายุ...", "blue")
            time.sleep(wait_before_renew)
            
            # ไปที่หน้าต่ออายุสินค้า — จำลองการคลิกผ่าน Marketplace ก่อน
            self.update_status(f"{profile_name}: ไปหน้าต่ออายุ...", "blue")
            
            # หยุดพักสุ่มก่อนไปหน้าใหม่ (เหมือนคนกำลังคิด)
            time.sleep(random.uniform(1.5, 3.0))
            
            # เข้า Marketplace ก่อน (เหมือนคนคลิกเมนู)
            driver.get("https://www.facebook.com/marketplace/you/selling/")
            self.wait_for_page_load(driver)
            time.sleep(random.uniform(2, 4))
            
            # จำลองการอ่านหน้า Marketplace เล็กน้อย
            if random.random() < 0.5:
                self.human_like_scroll(driver, "down")
                time.sleep(random.uniform(0.8, 1.5))
            
            # แล้วค่อยไปหน้าที่ต้องการ (renew หรือ inbox แล้วแต่โหมด)
            time.sleep(random.uniform(1.0, 2.5))
            driver.get(target_url)

            # รอให้หน้าโหลดเสร็จ
            self.wait_for_page_load(driver)
            time.sleep(random.uniform(3, 5))

            self.update_status(f"{profile_name}: เข้าหน้า {target_url} สำเร็จ", "green")
            
            # ตรวจสอบอีกครั้งว่าเจอหน้า error หรือไม่
            current_url = driver.current_url
            
            try:
                page_source = driver.page_source.lower()
            except:
                page_source = ""
            
            if "err_too_many_redirects" in page_source or "this page isn't working" in page_source:
                # ลองรีเฟรชอีกครั้ง
                self.update_status(f"{profile_name}: พบ error กำลังลองใหม่...", "orange")
                
                # บันทึกสาเหตุ Hard refresh
                if profile_name in self.profile_status:
                    self.profile_status[profile_name]['hard_refresh_count'] += 1
                    if "err_too_many_redirects" in page_source:
                        self.profile_status[profile_name]['hard_refresh_reason'] = "ERR_TOO_MANY_REDIRECTS"
                    else:
                        self.profile_status[profile_name]['hard_refresh_reason'] = "This page isn't working"
                
                driver.refresh()
                time.sleep(5)
                
                try:
                    page_source = driver.page_source.lower()
                except:
                    page_source = ""
                
                if "err_too_many_redirects" in page_source or "this page isn't working" in page_source:
                    raise Exception("Facebook ตรวจพบ automation และบล็อคการเข้าถึง (ERR_TOO_MANY_REDIRECTS)")
            
            # ตรวจสอบว่าถูก redirect กลับไปหน้า login หรือไม่
            if "login" in current_url.lower():
                raise Exception("ถูก redirect กลับไปหน้า login - session ไม่ถูกต้อง")
            
            self.update_status(f"{profile_name}: พร้อมต่ออายุ", "green")
            
            # ส่ง driver กลับไป (ไม่ปิด)
            return driver
            
        except Exception as e:
            # ถ้ามี error ให้ปิด driver และ raise error
            error_msg = str(e)
            self.update_status(f"{profile_name}: Error - {error_msg[:100]}...", "red")
            
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            
            raise Exception(error_msg)
    
    def renew_profile_worker(self, profile_name, keep_open=False):
        """Worker thread สำหรับต่ออายุ Profile

        keep_open=True คือเรียกจากระหว่างเฝ้าแชท ใช้ Chrome ตัวเดิม ห้ามปิดตอนจบ
        """
        driver = None
        renew_page_url = self.RENEW_PAGE_URL

        try:
            driver = self.profile_status[profile_name]['driver']

            if not driver:
                raise Exception("ไม่พบ Chrome driver")

            renewed_count = 0
            no_button_refresh_count = 0
            renew_url_use_count = 0  # นับจำนวนครั้งที่ใช้ URL Renew

            while True:
                # กดหยุดเฝ้าแชทระหว่างต่ออายุอยู่ ออกทันที ไม่ให้รอจนต่อครบลิสต์
                if keep_open and not self.auto_reply_active:
                    break

                # ตรวจสอบว่า Chrome ยังเปิดอยู่หรือไม่
                try:
                    current_url = driver.current_url
                except:
                    raise Exception("Chrome ถูกปิดไปแล้ว")
                
                # ตรวจสอบว่ายังอยู่หน้าต่ออายุหรือไม่
                if "marketplace/selling/renew_listings" not in current_url:
                    # นับจำนวนครั้งที่ใช้ URL
                    renew_url_use_count += 1
                    
                    # ตรวจสอบว่าใช้ URL เกิน 4 ครั้งหรือไม่
                    if renew_url_use_count > 4:
                        self.update_status(f"{profile_name}: Error - ใช้ URL มากเกินไป ({renew_url_use_count} ครั้ง)", "red")
                        if not keep_open:
                            try:
                                driver.quit()
                            except:
                                pass
                        raise Exception(f"ใช้ URL Renew มากเกินไป ({renew_url_use_count} ครั้ง)")
                    
                    self.update_status(f"{profile_name}: ไม่ได้อยู่หน้าต่ออายุ กลับไปหน้าต่ออายุ (ครั้งที่ {renew_url_use_count}/4)...", "orange")
                    driver.get(renew_page_url)
                    time.sleep(random.uniform(3, 5))
                else:
                    # อยู่หน้าต่ออายุอยู่แล้ว ไม่ต้องทำอะไร
                    pass
                
                # ตรวจสอบและปิดแถบ (tabs) ที่เกินมา
                try:
                    # ดึงรายการ window handles ทั้งหมด
                    all_windows = driver.window_handles
                    
                    # ถ้ามีมากกว่า 1 แถบ
                    if len(all_windows) > 1:
                        self.update_status(f"{profile_name}: พบแถบเพิ่ม {len(all_windows)-1} แถบ กำลังปิด...", "orange")
                        
                        # หาแถบหลัก (แถบที่มี URL หน้าต่ออายุ)
                        main_window = None
                        current_window = driver.current_window_handle
                        
                        # วิธีที่ 1: หาแถบที่มี URL หน้าต่ออายุ (แม่นยำที่สุด)
                        for window in all_windows:
                            try:
                                driver.switch_to.window(window)
                                if "marketplace/selling/renew_listings" in driver.current_url:
                                    main_window = window
                                    break
                            except:
                                pass
                        
                        # วิธีที่ 2: ถ้าไม่เจอ ใช้แถบที่มี facebook.com
                        if not main_window:
                            for window in all_windows:
                                try:
                                    driver.switch_to.window(window)
                                    if "facebook.com" in driver.current_url:
                                        main_window = window
                                        break
                                except:
                                    pass
                        
                        # วิธีที่ 3: ถ้ายังไม่เจอ ใช้แถบปัจจุบัน
                        if not main_window:
                            main_window = current_window
                        
                        # ปิดแถบอื่นๆ ทั้งหมด (ยกเว้นแถบหลัก)
                        for window in all_windows:
                            if window != main_window:
                                try:
                                    driver.switch_to.window(window)
                                    driver.close()
                                except:
                                    pass
                        
                        # กลับไปแถบหลัก
                        driver.switch_to.window(main_window)
                        self.update_status(f"{profile_name}: ปิดแถบเพิ่มแล้ว", "green")
                        time.sleep(0.5)
                except Exception as e:
                    # ถ้า error ไม่ต้องทำอะไร
                    pass
                
                # ตรวจสอบและปิดหน้าต่างแชทถ้ามี
                try:
                    chat_windows = driver.find_elements(By.XPATH, "//div[@class='x9f619 x1ja2u2z x78zum5 x1n2onr6 x1r8uery x1iyjqo2 xs83m0k xeuugli x1qughib x6s0dn4 xozqiw3 x1q0g3np xyri2b x1c1uobl x18d9i69 xexx8yu x1ws5yxj xw01apr x4cne27 xifccgj']")
                    if chat_windows:
                        self.update_status(f"{profile_name}: พบหน้าต่างแชท กำลังปิด...", "orange")
                        
                        # หาปุ่มปิดจาก aria-label="ปิดแชท"
                        try:
                            close_button = driver.find_element(By.XPATH, "//div[@aria-label='ปิดแชท' and @role='button']")
                            close_button.click()
                            time.sleep(1)
                            self.update_status(f"{profile_name}: ปิดแชทแล้ว", "green")
                        except:
                            # ถ้าไม่เจอ ลองกด ESC
                            try:
                                from selenium.webdriver.common.keys import Keys
                                driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
                                time.sleep(1)
                                self.update_status(f"{profile_name}: ปิดแชทแล้ว (ESC)", "green")
                            except:
                                self.update_status(f"{profile_name}: ไม่สามารถปิดแชทได้", "orange")
                        
                        time.sleep(1)
                except:
                    pass
                
                # ตรวจสอบและปิดการแจ้งเตือนถ้ามี
                try:
                    notification_header = driver.find_elements(By.XPATH, "//h1[@class='html-h1 xdj266r x14z9mp xat24cr x1lziwak xexx8yu xyri2b x18d9i69 x1c1uobl x1vvkbs x1heor9g x1qlqyl8 x1pd3egz x1a2a7pz' and text()='การแจ้งเตือน']")
                    if notification_header:
                        self.update_status(f"{profile_name}: พบการแจ้งเตือน กำลังปิด...", "orange")
                        
                        # หาปุ่มการแจ้งเตือน (ระฆัง) และคลิก
                        try:
                            notification_button = driver.find_element(By.XPATH, "//div[@aria-label='การแจ้งเตือน' and @role='button']")
                            notification_button.click()
                            time.sleep(1)
                            self.update_status(f"{profile_name}: ปิดการแจ้งเตือนแล้ว", "green")
                        except:
                            self.update_status(f"{profile_name}: ไม่สามารถปิดการแจ้งเตือนได้", "orange")
                        
                        time.sleep(1)
                except:
                    pass
                
                # ค้นหาปุ่มต่ออายุ — รอสูงสุด 90 วิ (เดิม 120 วิ x สูงสุด 4 รอบ = ค้าง 8 นาทีตอนต่ออายุหมดแล้ว)
                renew_buttons = []
                try:
                    renew_buttons = WebDriverWait(driver, 90).until(
                        EC.presence_of_all_elements_located((By.XPATH, "//span[@class='x1lliihq x6ikm8r x10wlt62 x1n2onr6 xlyipyv xuxw1ft' and text()='ต่ออายุ']"))
                    )
                except:
                    renew_buttons = []
                
                if not renew_buttons:
                    # ไม่เจอปุ่ม กลับไปหน้าต่ออายุหรือรีเฟรช
                    no_button_refresh_count += 1
                    self.update_status(f"{profile_name}: ไม่เจอปุ่ม รีเฟรชครั้งที่ {no_button_refresh_count}/4", "orange")

                    # ถ้ารีเฟรช 4 ครั้งแล้ว หยุดเลย
                    if no_button_refresh_count >= 4:
                        self.update_status(f"{profile_name}: รีเฟรช 4 ครั้งแล้ว ต่ออายุหมดแล้ว", "green")
                        break
                    
                    # ตรวจสอบว่ายังอยู่หน้าต่ออายุหรือไม่
                    try:
                        current_url = driver.current_url
                        if "marketplace/selling/renew_listings" in current_url:
                            # อยู่หน้าต่ออายุ ใช้ location.reload() (ปลอดภัยที่สุด)
                            self.update_status(f"{profile_name}: รีเฟรชหน้าเว็บ (ครั้งที่ {no_button_refresh_count + 1}/4)...", "blue")
                            driver.execute_script("location.reload();")

                        else:
                            # ไม่ได้อยู่หน้าต่ออายุ กลับไปหน้าต่ออายุ (ใช้ URL เฉพาะกรณีนี้)
                            # นับจำนวนครั้งที่ใช้ URL
                            renew_url_use_count += 1
                            
                            # ตรวจสอบว่าใช้ URL เกิน 4 ครั้งหรือไม่
                            if renew_url_use_count > 4:
                                self.update_status(f"{profile_name}: Error - ใช้ URL มากเกินไป ({renew_url_use_count} ครั้ง)", "red")
                                if not keep_open:
                                    try:
                                        driver.quit()
                                    except:
                                        pass
                                raise Exception(f"ใช้ URL Renew มากเกินไป ({renew_url_use_count} ครั้ง)")
                            
                            self.update_status(f"{profile_name}: กลับไปหน้าต่ออายุ (ครั้งที่ {renew_url_use_count}/4)...", "blue")
                            driver.get(renew_page_url)
                    except Exception as refresh_error:
                        # ถ้า error ลองรีเฟรชด้วย location.reload() (ปลอดภัย)
                        try:
                            self.update_status(f"{profile_name}: Error ลองรีเฟรชอีกครั้ง...", "orange")
                            driver.execute_script("location.reload();")
                        except:
                            # ถ้ายังไม่ได้ ปิด Chrome และแจ้ง GUI
                            self.update_status(f"{profile_name}: Error 2 ครั้ง ปิด Chrome...", "red")
                            if not keep_open:
                                try:
                                    driver.quit()
                                except:
                                    pass
                            raise Exception("Error รีเฟรช 2 ครั้ง ปิด Chrome แล้ว")
                    
                    time.sleep(random.uniform(3, 5))
                    continue
                
                # พบปุ่มต่ออายุ — เลื่อนหาปุ่มแล้วคลิกแบบมนุษย์
                try:
                    # รอเล็กน้อยก่อน
                    time.sleep(random.uniform(0.5, 1.0))
                    
                    # เลื่อนหน้าจอไปที่ปุ่มแบบมนุษย์
                    self.human_like_scroll_to_element(driver, renew_buttons[0])
                    time.sleep(random.uniform(0.5, 1.0))
                    
                    # hover ก่อนกด
                    try:
                        actions = ActionChains(driver)
                        actions.move_to_element(renew_buttons[0]).perform()
                        time.sleep(random.uniform(0.5, 1.5))
                    except:
                        pass
                    
                    # หา parent element ที่คลิกได้
                    parent_button = renew_buttons[0].find_element(By.XPATH, "./ancestor::div[@role='button' or @role='none'][1]")
                    
                    # คลิกพร้อมสุ่มตำแหน่งในพื้นที่ปุ่ม
                    try:
                        btn_size = parent_button.size
                        btn_w = btn_size.get('width', 60)
                        btn_h = btn_size.get('height', 30)
                        margin = 6
                        offset_x = random.randint(-max(1, int(btn_w // 2) - margin), max(1, int(btn_w // 2) - margin))
                        offset_y = random.randint(-max(1, int(btn_h // 2) - margin), max(1, int(btn_h // 2) - margin))
                        actions = ActionChains(driver)
                        actions.move_to_element_with_offset(parent_button, offset_x, offset_y).pause(random.uniform(0.2, 0.4)).click().perform()
                    except:
                        try:
                            actions = ActionChains(driver)
                            actions.move_to_element(parent_button).pause(random.uniform(0.2, 0.4)).click().perform()
                        except:
                            parent_button.click()
                    
                    renewed_count += 1
                    no_button_refresh_count = 0
                    renew_url_use_count = 0  # กดต่ออายุสำเร็จ = session ปกติดี รีเซ็ตตัวนับ URL bounce

                    self.profile_status[profile_name]['renewed_count'] = renewed_count
                    self.update_status(f"{profile_name}: ต่ออายุแล้ว {renewed_count} รายการ", "green")
                    
                    # delay สุ่มหลังคลิก
                    time.sleep(random.uniform(2.5, 6.0))
                    
                    # Behavioral Pattern: หยุดพักเป็นระยะ — สุ่มทั้งจำนวนรายการและเวลาพัก
                    # ใช้ threshold สุ่มแทนตัวเลขตายตัว เพื่อไม่ให้เป็น pattern
                    if not hasattr(self, f'_next_rest_{profile_name}'):
                        setattr(self, f'_next_rest_{profile_name}', random.randint(7, 14))
                    next_rest = getattr(self, f'_next_rest_{profile_name}')
                    if renewed_count >= next_rest:
                        rest_time = random.uniform(15, 40)
                        self.update_status(f"{profile_name}: หยุดพัก {int(rest_time)} วินาที (ต่ออายุไปแล้ว {renewed_count} รายการ)...", "orange")
                        time.sleep(rest_time)
                        time.sleep(random.uniform(0.3, 0.7))
                        # ตั้ง threshold ถัดไปแบบสุ่ม
                        setattr(self, f'_next_rest_{profile_name}', renewed_count + random.randint(7, 15))
                    
                    # กลับไป loop เพื่อหาปุ่มต่ออายุตัวถัดไป
                    continue
                    
                except Exception as e1:
                    # ลองคลิกที่ span โดยตรง
                    try:
                        time.sleep(0.5)
                        self.human_like_scroll_to_element(driver, renew_buttons[0])
                        time.sleep(random.uniform(0.5, 1.0))
                        try:
                            actions = ActionChains(driver)
                            actions.move_to_element(renew_buttons[0]).pause(random.uniform(0.2, 0.4)).click().perform()
                        except:
                            renew_buttons[0].click()
                        
                        renewed_count += 1
                        no_button_refresh_count = 0
                        renew_url_use_count = 0  # กดต่ออายุสำเร็จ = session ปกติดี รีเซ็ตตัวนับ URL bounce
                        self.profile_status[profile_name]['renewed_count'] = renewed_count
                        self.update_status(f"{profile_name}: ต่ออายุแล้ว {renewed_count} รายการ", "green")
                        time.sleep(random.uniform(2.5, 5.0))
                        continue
                        
                    except Exception as e2:
                        # ถ้าคลิกไม่ได้ทั้ง 2 วิธี ข้ามไปหาปุ่มถัดไป
                        time.sleep(random.uniform(0.8, 1.5))
                        continue
            
            # เสร็จแล้ว - ปิด Chrome ของ Profile นี้
            self.profile_status[profile_name]['stage'] = 'completed'
            self.update_status(f"{profile_name}: เสร็จสิ้น - ต่ออายุ {renewed_count} รายการ", "green")

            # ปิด Chrome (ยกเว้นเรียกมาจากระหว่างเฝ้าแชท ต้องเอา Chrome ตัวนี้ไปอ่านแชทต่อ)
            if not keep_open:
                try:
                    driver.quit()
                    self.update_status(f"{profile_name}: ปิด Chrome แล้ว", "gray")
                except:
                    pass

        except Exception as e:
            self.profile_status[profile_name]['stage'] = 'failed'
            self.profile_status[profile_name]['error'] = str(e)
            self.update_status(f"{profile_name}: ล้มเหลว - {str(e)[:50]}", "red")

            # ปิด Chrome ถ้ายังเปิดอยู่ (ระหว่างเฝ้าแชทปล่อยไว้ ให้ลูปแชทเช็คเองว่า Chrome ตายยัง)
            if driver and not keep_open:
                try:
                    driver.quit()
                except:
                    pass

    # ========== ตอบแชทลูกค้าอัตโนมัติ (Marketplace inbox) ==========
    # หมายเหตุ: selector ของ DOM inbox/ห้องแชทด้านล่าง (get_selectors) เป็นการเดาที่ดีที่สุด
    # จากรูปแบบที่ Facebook ใช้ทั่วไป (aria-label/role — ไม่ใช้ atomic class เพราะเปลี่ยนทุก build)
    # ยังไม่เคยทดสอบกับ DOM จริง ต้องปรับตอน live-test บนเครื่องลูกค้า

    def strip_leading_number(self, name):
        """ตัดเลขนำหน้าชื่อโฟลเดอร์ออก เช่น '12. โซฟา 2 ที่นั่ง' -> 'โซฟา 2 ที่นั่ง'"""
        return re.sub(r'^[\s\d.\-_)]+', '', name).strip()

    def collect_folder_assets(self, folder_path):
        """เก็บรูป/วิดีโอ/ข้อความ .txt จากไฟล์ระดับบนสุดของโฟลเดอร์นี้ (ไม่ลงลึกโฟลเดอร์ย่อย)"""
        images, videos, texts = [], [], []
        try:
            for fname in sorted(os.listdir(folder_path)):
                fpath = os.path.join(folder_path, fname)
                if not os.path.isfile(fpath):
                    continue
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.IMAGE_EXTS:
                    images.append(fpath)
                elif ext in self.VIDEO_EXTS:
                    videos.append(fpath)
                elif ext == '.txt':
                    texts.append(fpath)
        except Exception:
            pass

        text_content = ""
        for tpath in texts:
            try:
                with open(tpath, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        text_content += (("\n\n" if text_content else "") + content)
            except Exception:
                pass

        return {'images': images, 'videos': videos, 'text': text_content}

    def scan_product_folders(self, root_folder):
        """สแกนโฟลเดอร์สินค้าทั้งหมดใต้ root_folder แยกเป็น หลัก/รีวิว/เพิ่มเติม ต่อสินค้า 1 โฟลเดอร์
        สมมติฐาน (ไม่มีสกรีนช็อตต้นฉบับแล้วหลัง compact): โฟลเดอร์ย่อยที่ชื่อมีคำว่า "รีวิว"/"เพิ่มเติม"
        คือหมวดนั้น ที่เหลือ (ไฟล์ระดับบน + โฟลเดอร์ย่อยอื่น) ถือเป็นหลักทั้งหมด
        คืนค่า {ชื่อสินค้า(ตัดเลขนำหน้าแล้ว): {'path':.., 'main':{...}, 'review':{...}|None, 'extra':{...}|None}}"""
        result = {}
        if not root_folder or not os.path.isdir(root_folder):
            return result

        for entry in sorted(os.listdir(root_folder)):
            entry_path = os.path.join(root_folder, entry)
            if not os.path.isdir(entry_path):
                continue

            product_name = self.strip_leading_number(entry)
            if not product_name:
                continue

            review_path = None
            extra_path = None
            other_subfolders = []

            try:
                sub_entries = os.listdir(entry_path)
            except Exception:
                sub_entries = []

            for sub in sub_entries:
                sub_path = os.path.join(entry_path, sub)
                if not os.path.isdir(sub_path):
                    continue
                if any(k in sub for k in self.REVIEW_KEYWORDS):
                    review_path = sub_path
                elif any(k in sub for k in self.EXTRA_KEYWORDS):
                    extra_path = sub_path
                else:
                    other_subfolders.append(sub_path)

            main_assets = self.collect_folder_assets(entry_path)
            for sub_path in other_subfolders:
                sub_assets = self.collect_folder_assets(sub_path)
                main_assets['images'] += sub_assets['images']
                main_assets['videos'] += sub_assets['videos']
                if sub_assets['text']:
                    main_assets['text'] += (("\n\n" if main_assets['text'] else "") + sub_assets['text'])

            result[product_name] = {
                'path': entry_path,
                'main': main_assets,
                'review': self.collect_folder_assets(review_path) if review_path else None,
                'extra': self.collect_folder_assets(extra_path) if extra_path else None,
            }

        return result

    def match_listing_to_folder(self, listing_name, product_folders):
        """จับคู่ชื่อสินค้าที่ลูกค้าทักกับชื่อโฟลเดอร์ — ต้องเจอ 1 คู่เป๊ะเท่านั้น
        0 คู่ หรือ >=2 คู่ = ไม่จับคู่ (กันส่งข้อมูลสินค้าผิดให้ลูกค้า)"""
        if not listing_name:
            return None
        matches = [name for name in product_folders if name and name in listing_name]
        if len(matches) == 1:
            return matches[0]
        return None

    def inbox_row_key(self, text):
        """คีย์สำหรับเทียบว่าแถว inbox มีข้อความใหม่เข้ามาไหม (ตัดตัวเลขกับคำบอกเวลาออก)"""
        return self.ROW_TIME_NOISE.sub('', (text or '').lower())

    def preview_message(self, row_text):
        """ดึงข้อความล่าสุดที่เห็นใน preview ของแถว inbox เอาไปแปะในแจ้งเตือน
        คืน "" ถ้าข้อความล่าสุดเป็นของเราเอง หรืออ่านไม่ออก — ห้ามเดา ถ้าไม่ชัวร์ก็ไม่ต้องแปะ
        หมายเหตุ: FB ตัดข้อความยาวด้วย … ที่ได้อาจไม่ใช่ประโยคเต็ม"""
        lines = [ln.strip() for ln in (row_text or '').split('\n') if ln.strip()]
        if not lines:
            return ""
        last = lines[-1]
        # บางธีมเอาเวลาไว้บรรทัดสุดท้ายแยกเดี่ยวๆ ("2 นาที") ถ้าเหลือแต่ noise ให้ถอยไปบรรทัดก่อนหน้า
        if not self.ROW_TIME_NOISE.sub('', last) and len(lines) > 1:
            last = lines[-2]
        # ตัดเวลาที่ห้อยท้ายบรรทัดเดียวกัน ("จ่ายปลายทางได้มั้ย · 2 นาที")
        last = re.split(r'\s*[·•]\s*', last)[0].strip()
        if not self.ROW_TIME_NOISE.sub('', last):
            return ""
        low = last.lower()
        if any(low.startswith(p) for p in self.PREVIEW_SELF_PREFIXES):
            return ""
        return last

    def next_reply_stage(self, info, row_key, available=None):
        """ตัดสินว่าแชทที่ตอบ main ไปแล้ว ควรส่งโฟลเดอร์อะไรต่อ เมื่อลูกค้าทักกลับมา
        available = ชุดชื่อโฟลเดอร์ที่มีไฟล์จริงของสินค้านั้น (None = ถือว่ามีครบ)
        คืน (category, stage ใหม่, reason):
          'unmatched' จับคู่สินค้าไม่ได้ตั้งแต่แรก ไม่ส่งอะไร
          'baseline'  ยังไม่เคยเก็บคีย์แถวนี้ (รอบแรกหลังอัปเดตโปรแกรม) เก็บไว้เทียบรอบหน้า ห้ามส่ง
          'nochange'  ลูกค้าไม่ได้ทักอะไรใหม่
          'send'      ส่ง category ได้
          'done'      ส่งครบทุกโฟลเดอร์แล้ว เหลือให้คนตอบเอง
        """
        if info.get('status') != 'replied':
            return None, None, 'unmatched'
        if info.get('row_key') is None:
            return None, None, 'baseline'
        if info.get('row_key') == row_key:
            return None, None, 'nochange'

        stage = int(info.get('stage', 1))
        for i in range(max(stage - 1, 0), len(self.REPLY_STAGES)):
            category = self.REPLY_STAGES[i]
            if available is None or category in available:
                return category, i + 2, 'send'
        return None, len(self.REPLY_STAGES) + 1, 'done'

    def split_text_to_messages(self, text):
        """แยกข้อความยาวเป็นย่อหน้า เพื่อส่งทีละข้อความ (ไม่ส่งไฟล์ .txt ให้ลูกค้าตรงๆ)"""
        if not text:
            return []
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        return paragraphs

    def get_selectors(self):
        """ตาราง selector ของ element ใน Marketplace inbox/ห้องแชท เรียงตามลำดับที่จะลอง
        ใช้ aria-label/role/text ก่อนเสมอ ห้ามใช้ atomic class (x1abc...) เพราะเปลี่ยนทุก build ของ FB"""
        return {
            'conversation_row': [
                (By.XPATH, "//div[@role='grid']//a[contains(@href,'/marketplace/t/')]"),
                (By.XPATH, "//a[contains(@href,'/marketplace/t/')]"),
                (By.XPATH, "//div[@role='row']//a[contains(@href,'/t/')]"),
            ],
            'listing_title': [
                (By.XPATH, "//a[contains(@href,'/marketplace/item/')]"),
                (By.XPATH, "//div[@role='main']//h2"),
            ],
            'message_box': [
                (By.XPATH, "//div[@aria-label='ข้อความ' and @role='textbox']"),
                (By.XPATH, "//div[@aria-label='Message' and @role='textbox']"),
                (By.XPATH, "//div[@role='textbox' and @contenteditable='true']"),
            ],
            'file_input': [
                (By.XPATH, "//input[@type='file' and contains(@accept,'image')]"),
                (By.XPATH, "//input[@type='file']"),
            ],
            'incoming_bubble': [
                (By.XPATH, "//div[@role='main']//div[@role='row']"),
            ],
        }

    def find_first(self, driver, key, context=None, wait=0):
        """หา element ตัวแรกที่เจอ ลองทีละ selector ตามลำดับใน get_selectors()[key]
        context ใช้จำกัดขอบเขตค้นหาให้เป็น element แทน driver ทั้งหน้า"""
        scope = context if context is not None else driver
        for by, expr in self.get_selectors().get(key, []):
            try:
                if wait > 0 and context is None:
                    el = WebDriverWait(driver, wait).until(EC.presence_of_element_located((by, expr)))
                else:
                    el = scope.find_element(by, expr)
                return el
            except Exception:
                continue
        return None

    def find_all(self, driver, key, context=None):
        """คืนทุก element ที่เจอจาก selector แรกใน get_selectors()[key] ที่ใช้ได้ผล"""
        scope = context if context is not None else driver
        for by, expr in self.get_selectors().get(key, []):
            try:
                els = scope.find_elements(by, expr)
                if els:
                    return els
            except Exception:
                continue
        return []

    def upload_files_to_chat(self, driver, file_paths):
        """แนบไฟล์ผ่าน input[type=file] โดยตรง (ห้ามคลิกปุ่มแนบไฟล์ — เปิด OS dialog ที่ Selenium สั่งไม่ได้)"""
        file_input = self.find_first(driver, 'file_input', wait=5)
        if not file_input:
            self.update_status("ไม่พบช่องแนบไฟล์ (file_input) - ต้องปรับ selector", "red")
            return False
        try:
            driver.execute_script(
                "arguments[0].style.display='block'; arguments[0].style.opacity=1; "
                "arguments[0].style.visibility='visible'; arguments[0].removeAttribute('hidden');",
                file_input
            )
        except Exception:
            pass
        try:
            file_input.send_keys("\n".join(file_paths))
            time.sleep(random.uniform(2, 4) * max(1, len(file_paths) // 5))
            return True
        except Exception as e:
            self.update_status(f"แนบไฟล์ไม่สำเร็จ: {str(e)[:80]}", "red")
            return False

    def send_chat_message(self, driver, text):
        """พิมพ์และส่งข้อความในห้องแชท (ใช้ human_like_type เดิม)"""
        box = self.find_first(driver, 'message_box', wait=5)
        if not box:
            self.update_status("ไม่พบช่องพิมพ์ข้อความ (message_box) - ต้องปรับ selector", "red")
            return False
        try:
            box.click()
            time.sleep(random.uniform(0.3, 0.7))
            self.human_like_type(box, text, driver)
            time.sleep(random.uniform(0.3, 0.8))
            box.send_keys(Keys.RETURN)
            return True
        except Exception as e:
            self.update_status(f"ส่งข้อความไม่สำเร็จ: {str(e)[:80]}", "red")
            return False

    def send_folder_content(self, driver, assets):
        """ส่งรูป+วิดีโอก่อน แล้วค่อยส่งข้อความจาก .txt ทีละย่อหน้า
        คืน False ถ้ามีชิ้นไหนส่งไม่ออก — ผู้เรียกห้ามบอกเจ้าของว่า "ตอบให้แล้ว" ทั้งที่ลูกค้าไม่ได้อะไร"""
        ok = True
        media_files = assets.get('images', []) + assets.get('videos', [])
        if media_files:
            ok = self.upload_files_to_chat(driver, media_files) and ok
            # แนบไฟล์เฉยๆ ยังไม่ถูกส่ง ต้องกด Enter — โฟลเดอร์ที่มีแต่รูป (ไม่มี .txt ตามมากด Enter ให้) ไม่เคยถูกส่งเลย
            ok = self.press_send(driver) and ok
            self.random_sleep(2, 5)

        for msg in self.split_text_to_messages(assets.get('text', '')):
            ok = self.send_chat_message(driver, msg) and ok
            self.random_sleep(2, 6)
        return ok

    def press_send(self, driver):
        """กด Enter ในช่องพิมพ์ เพื่อส่งของที่แนบค้างอยู่"""
        box = self.find_first(driver, 'message_box', wait=5)
        if not box:
            self.update_status("ไม่พบช่องพิมพ์ข้อความ (message_box) - ต้องปรับ selector", "red")
            return False
        try:
            box.send_keys(Keys.RETURN)
            return True
        except Exception as e:
            self.update_status(f"กดส่งไฟล์ไม่สำเร็จ: {str(e)[:80]}", "red")
            return False

    def browse_reply_folder(self):
        """เลือกโฟลเดอร์แม่ที่รวมโฟลเดอร์สินค้าทั้งหมด (แต่ละสินค้า = 1 โฟลเดอร์ย่อย)"""
        folder = filedialog.askdirectory(title="เลือกโฟลเดอร์สินค้า (แต่ละสินค้าคือ 1 โฟลเดอร์ย่อย)")
        if folder:
            self.reply_root_folder = folder
            self.reply_folder_var.set(folder)
            self.save_reply_settings()

    def update_reply_list(self):
        """อัปเดตรายการ 'แชทที่ตอบไปแล้ว' ใน Listbox จาก self.reply_state"""
        self.reply_listbox.delete(0, tk.END)
        self._reply_list_index = []
        # list() กัน worker เพิ่มแชทเข้ามาระหว่างวน (dict เปลี่ยนขนาดกลางลูป = พัง)
        for profile_name, threads in list(self.reply_state.items()):
            for thread_id, info in list(threads.items()):
                if info.get('status') == 'old':
                    continue  # แชทเก่าที่จดไว้เฉยๆ ไม่ได้ตอบ ไม่ต้องโชว์ให้รก
                if info.get('status') == 'failed':
                    status_txt = "⚠ ส่งไม่สำเร็จ"
                elif info.get('status') != 'replied':
                    status_txt = "⚠ จับคู่ไม่ได้"
                else:
                    sent = [self.STAGE_LABELS[c] for c in self.ALL_STAGES[:int(info.get('stage', 1))]]
                    status_txt = "✓ ส่งแล้ว: " + ", ".join(sent)
                label = f"[{profile_name}] {info.get('product', '?')} - {status_txt} ({info.get('replied_at', '')})"
                self.reply_listbox.insert(tk.END, label)
                self._reply_list_index.append((profile_name, thread_id))

    def start_auto_reply(self):
        selected_indices = self.profile_listbox.curselection()
        if not selected_indices:
            messagebox.showwarning("คำเตือน", "กรุณาเลือกอย่างน้อย 1 Profile")
            return
        if not self.reply_root_folder or not os.path.isdir(self.reply_root_folder):
            messagebox.showwarning("คำเตือน", "กรุณาเลือกโฟลเดอร์สินค้าก่อน")
            return
        if self.is_running:
            messagebox.showwarning("คำเตือน", "กำลังดำเนินการอยู่ กรุณารอให้เสร็จก่อน")
            return

        self.selected_profiles = [self.profile_listbox.get(i) for i in selected_indices]
        confirm = messagebox.askyesno(
            "ยืนยัน",
            f"ต้องการเริ่มตอบแชทอัตโนมัติสำหรับ {len(self.selected_profiles)} Profile หรือไม่?\n\n" +
            "\n".join(self.selected_profiles)
        )
        if not confirm:
            return

        self.is_running = True
        self.auto_reply_active = True
        self.update_status(f"เริ่มตอบแชทอัตโนมัติ {len(self.selected_profiles)} Profile...", "blue")

        self.start_button.config(state=tk.DISABLED, bg="#9E9E9E")
        self.reply_start_btn.config(state=tk.DISABLED, bg="#9E9E9E")
        self.reply_stop_btn.config(state=tk.NORMAL)
        self.delete_btn.config(state=tk.DISABLED)

        thread = threading.Thread(target=self.run_auto_reply_thread, daemon=True)
        thread.start()

    def stop_auto_reply(self):
        """สั่งหยุด — worker แต่ละ Profile จะเช็คแฟล็กนี้แล้วปิด Chrome ของตัวเองตอนจบรอบสแกน"""
        self.auto_reply_active = False
        self.update_status("กำลังหยุดตอบแชท (รอ Chrome ปิดครบทุก Profile)...", "orange")

    def run_auto_reply_thread(self):
        try:
            self.auto_reply_multiple_profiles()
        except Exception as e:
            self.root.after(0, lambda e=e: messagebox.showerror("ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}"))
        finally:
            self.is_running = False
            self.auto_reply_active = False
            self.reply_drivers = {}
            self.root.after(0, lambda: self.start_button.config(state=tk.NORMAL, bg="#4CAF50"))
            self.root.after(0, lambda: self.reply_start_btn.config(state=tk.NORMAL, bg="#2196F3"))
            self.root.after(0, lambda: self.reply_stop_btn.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.delete_btn.config(state=tk.NORMAL))
            self.root.after(0, self.update_reply_list)

    def auto_reply_multiple_profiles(self):
        """เปิด Chrome ทุก Profile ที่เลือก แล้วเริ่ม monitor แชทพร้อมกันจนกว่าจะกดหยุด"""
        product_folders = self.scan_product_folders(self.reply_root_folder)
        if not product_folders:
            self.update_status("ไม่พบโฟลเดอร์สินค้าในที่เลือก", "red")
            return

        self.reply_drivers = {}
        threads = []

        for index, profile_name in enumerate(self.selected_profiles, 1):
            if not self.auto_reply_active:
                break
            self.update_status(f"[{index}/{len(self.selected_profiles)}] กำลังเปิด Chrome: {profile_name}", "blue")
            try:
                driver = self.open_and_login_profile(profile_name, target_url="https://www.facebook.com/marketplace/inbox/")
                if driver:
                    self.reply_drivers[profile_name] = driver
                    t = threading.Thread(
                        target=self.auto_reply_worker,
                        args=(profile_name, driver, product_folders),
                        daemon=True
                    )
                    threads.append(t)
                    t.start()
                if index < len(self.selected_profiles):
                    time.sleep(random.uniform(4, 12))
            except Exception as e:
                self.notify_problem(profile_name, f"เปิดไม่สำเร็จ ไม่ได้เฝ้าแชทเฟสนี้ - {str(e)[:80]}")
                continue

        for t in threads:
            t.join()

        self.update_status("หยุดตอบแชทอัตโนมัติทุก Profile แล้ว", "green")

    def auto_reply_worker(self, profile_name, driver, product_folders):
        """monitor inbox ของ Profile นี้ วนหาแชทใหม่แล้วตอบอัตโนมัติ จนกว่า auto_reply_active จะเป็น False"""
        self.reply_state.setdefault(profile_name, {})
        lock = self.driver_locks.setdefault(profile_name, threading.Lock())
        last_renew = 0.0  # 0 = ต่ออายุให้รอบแรกเลย ลูกค้าจะได้เห็นว่ามันทำงานจริง
        first_pass = True  # รอบแรกเจอแต่แชทที่ค้างอยู่ก่อนเปิดโปรแกรม
        logged_out = False

        while self.auto_reply_active:
            try:
                driver.current_url
            except Exception:
                self.notify_problem(profile_name, "Chrome ถูกปิดไปแล้ว เลิกเฝ้าแชทเฟสนี้")
                break

            # ถือ Chrome ไว้ทั้งรอบ ปุ่มส่งด้วยมือต้องรอ ไม่งั้นมันพาไปห้องแชทอื่นกลางคัน
            with lock:
                try:
                    scanned = self.scan_inbox_once(profile_name, driver, product_folders, first_pass)
                    if scanned:
                        first_pass = False
                    # หลุด Login แล้วแถวแชทเป็น 0 ดูเหมือนไม่มีลูกค้าทัก เงียบไปทั้งเฟส — แจ้งตอนเพิ่งหลุดครั้งเดียว ไม่ยิงทุกนาที
                    elif not logged_out:
                        self.notify_problem(profile_name, "หลุด Login อ่านแชทไม่ได้ ต้อง Login เฟสนี้ใหม่")
                    logged_out = not scanned
                except Exception as e:
                    self.update_status(f"{profile_name}: Error สแกนแชท - {str(e)[:80]}", "orange")

                # ถึงรอบต่ออายุสินค้าหรือยัง — ใช้ Chrome ตัวเดิม เปิดโปรไฟล์เดียวซ้อนกันไม่ได้
                if self.auto_reply_active and not logged_out and self.renew_due(last_renew):
                    self.renew_pass_during_reply(profile_name, driver)
                    # นับเวลาจากตอนต่อเสร็จ ไม่ใช่ตอนเริ่ม ไม่งั้นรอบที่ต่อนานกว่า 30 นาที
                    # จะวนไปต่ออายุต่อทันทีโดยไม่ได้อ่านแชทคั่นเลย
                    last_renew = time.time()

            # พักก่อน scan รอบถัดไป — เช็คแฟล็กหยุดทุกวินาทีเพื่อให้กดหยุดแล้วตอบสนองไว
            for _ in range(int(random.uniform(40, 80))):
                if not self.auto_reply_active:
                    break
                time.sleep(1)

        try:
            driver.quit()
        except Exception:
            pass
        self.update_status(f"{profile_name}: ปิด Chrome แล้ว (หยุดตอบแชท)", "gray")

    def scan_inbox_once(self, profile_name, driver, product_folders, first_pass):
        """อ่าน inbox 1 รอบ ตอบ/แจ้งเตือนแชทที่มีอะไรใหม่ — คืน False ถ้าเฟสนี้หลุด Login (ไม่ได้อ่านแชท)"""
        driver.get("https://www.facebook.com/marketplace/inbox/")
        self.wait_for_page_load(driver)
        time.sleep(random.uniform(2, 4))
        if self._is_login_pending_url(driver.current_url):
            return False

        # อ่านทุกแถวให้ครบก่อนเปิดแชทแรก — พอ driver.get() แล้ว element ที่เหลือกลายเป็น stale
        pending = []
        seen_this_pass = set()
        for row in self.find_all(driver, 'conversation_row'):
            try:
                href = row.get_attribute('href')
                row_text = row.text
            except Exception:
                continue
            row_key = self.inbox_row_key(row_text)
            preview = self.preview_message(row_text)
            if not href or '/t/' not in href:
                continue

            thread_id = href.split('/t/')[-1].split('/')[0].split('?')[0]
            if not thread_id or thread_id in seen_this_pass:
                continue
            seen_this_pass.add(thread_id)
            pending.append((thread_id, href, row_key, preview))

        for thread_id, href, row_key, preview in pending:
            if not self.auto_reply_active:
                break
            info = self.reply_state[profile_name].get(thread_id)
            if info is None:
                self.handle_one_conversation(profile_name, driver, href, thread_id, product_folders,
                                             row_key, preview, is_new=not first_pass)
            elif not self.handle_followup(profile_name, driver, thread_id, product_folders, info, row_key, preview):
                continue  # ไม่มีอะไรใหม่ ไม่ได้เปิดหน้าไหน ไม่ต้องหน่วงเวลา
            self.random_sleep(3, 8)
        return True

    def renew_pass_during_reply(self, profile_name, driver):
        """คั่นรอบเฝ้าแชทไปต่ออายุสินค้า แล้วกลับมาอ่านแชทต่อด้วย Chrome ตัวเดิม"""
        if not hasattr(self, 'profile_status'):
            self.profile_status = {}
        self.profile_status.setdefault(profile_name, {})
        self.profile_status[profile_name].update({
            'driver': driver, 'stage': 'renewing', 'renewed_count': 0, 'error': None,
            'hard_refresh_count': 0, 'hard_refresh_reason': None,
        })
        # ล้างตัวนับพักมือของรอบก่อน ไม่งั้นรอบนี้ที่นับใหม่จาก 0 จะไม่พักเลย = ดูเป็นบอท
        if hasattr(self, f'_next_rest_{profile_name}'):
            delattr(self, f'_next_rest_{profile_name}')

        self.update_status(f"{profile_name}: พักเฝ้าแชท ไปต่ออายุสินค้า...", "blue")
        try:
            # เปิดหน้าต่ออายุให้ก่อน ไม่งั้น worker เห็นว่ายังอยู่หน้า inbox แล้วเสีย URL budget ไป 1 ครั้ง
            driver.get(self.RENEW_PAGE_URL)
            self.wait_for_page_load(driver)
            time.sleep(random.uniform(2, 4))
            self.renew_profile_worker(profile_name, keep_open=True)
        except Exception as e:
            self.update_status(f"{profile_name}: ต่ออายุระหว่างเฝ้าแชทไม่สำเร็จ - {str(e)[:60]}", "orange")

    def handle_one_conversation(self, profile_name, driver, href, thread_id, product_folders, row_key=None,
                                preview="", is_new=True):
        """เปิดแชทเดี่ยว ตรวจว่าเป็นข้อความแรกจากลูกค้าหรือไม่ จับคู่สินค้า แล้วส่งข้อมูล
        is_new=False คือแชทที่ค้างอยู่ก่อนเปิดโปรแกรม (เจอในรอบสแกนแรก)"""
        try:
            driver.get(href)
            self.wait_for_page_load(driver)
            time.sleep(random.uniform(2, 4))

            # หมายเหตุ: incoming_bubble นับแถวข้อความทั้งห้อง (ยังแยกฝั่งลูกค้า/เราไม่ได้ในตอนนี้)
            # ใช้เป็นตัวกรองหยาบๆ ว่ายังไม่มีบทสนทนายาว ต้องปรับให้แม่นตอน live-test
            incoming = self.find_all(driver, 'incoming_bubble')

            listing_el = self.find_first(driver, 'listing_title', wait=5)
            listing_name = listing_el.text.strip() if listing_el else ""

            matched_name = self.match_listing_to_folder(listing_name, product_folders)
            now = time.strftime('%Y-%m-%d %H:%M')

            if len(incoming) > 1:
                # มีข้อความมากกว่า 1 แถวแล้ว ไม่ตอบทับบทสนทนาที่คุยต่อแล้ว แต่ต้องจดไว้ —
                # ไม่จด รอบหน้าไม่รู้จักแชทนี้ เปิดซ้ำทุกรอบ (ขึ้นอ่านแล้วทุกนาที) และลูกค้าพิมพ์มาอีกก็ไม่มีแจ้งเตือน
                self.reply_state[profile_name][thread_id] = {
                    'product': matched_name or listing_name or '(ไม่พบชื่อสินค้า)',
                    'status': 'old',
                    'replied_at': now,
                    'row_key': row_key,
                }
                self.save_reply_settings()
                # โผล่มาหลังเปิดโปรแกรม = ลูกค้าเพิ่งพิมพ์มา ต้องบอกเจ้าของ
                # ที่ค้างอยู่ก่อนเปิดโปรแกรมไม่แจ้ง ไม่งั้นเปิดโปรแกรมทีนึงเด้งรัวเท่าจำนวนแชทเก่า
                if is_new:
                    self.notify_new_chat(profile_name, matched_name or listing_name, 'old_chat', message=preview)
                return

            if not matched_name:
                self.reply_state[profile_name][thread_id] = {
                    'product': listing_name or '(ไม่พบชื่อสินค้า)',
                    'status': 'unmatched',
                    'replied_at': now,
                    'row_key': row_key,
                }
                self.save_reply_settings()
                self.root.after(0, self.update_reply_list)
                self.update_status(f"{profile_name}: จับคู่สินค้าไม่ได้ - '{listing_name}' (ข้ามไว้ให้ส่งเอง)", "orange")
                self.notify_new_chat(profile_name, listing_name, 'unmatched', listing_name, message=preview)
                return

            folder_info = product_folders[matched_name]
            sent_main = self.stage_enabled.get('main', True)
            if sent_main and not self.send_folder_content(driver, folder_info['main']):
                # ส่งไม่ออก ห้ามจดว่าตอบแล้ว และห้ามลองเองซ้ำทุกรอบ (รูปอาจไปแล้วครึ่งนึง ส่งซ้ำ = ลูกค้าได้รูปซ้ำ)
                self.reply_state[profile_name][thread_id] = {
                    'product': matched_name,
                    'status': 'failed',
                    'replied_at': now,
                    'row_key': None,
                }
                self.save_reply_settings()
                self.root.after(0, self.update_reply_list)
                self.update_status(f"{profile_name}: ส่งข้อมูล '{matched_name}' ไม่สำเร็จ ต้องตอบเอง", "red")
                self.notify_new_chat(profile_name, matched_name, 'send_failed', message=preview)
                return

            self.reply_state[profile_name][thread_id] = {
                'product': matched_name,
                'status': 'replied',
                'replied_at': now,
                'stage': 1,
                # ส่งไปแล้ว preview ของแถวเปลี่ยนเพราะข้อความของเราเอง — ตั้ง None ให้รอบหน้าเก็บ
                # คีย์ใหม่เป็นฐานเทียบ ไม่งั้นจะนับว่าลูกค้าทักกลับแล้วยิงรีวิวทันที
                # ไม่ได้ส่งอะไร preview ยังเป็นของลูกค้า เก็บคีย์ไว้เลยได้
                'row_key': None if sent_main else row_key,
                'just_sent': sent_main,
            }
            self.save_reply_settings()
            self.root.after(0, self.update_reply_list)
            if sent_main:
                self.update_status(f"{profile_name}: ตอบแชท '{matched_name}' แล้ว", "green")
                self.notify_new_chat(profile_name, matched_name, 'replied', message=preview)
            else:
                self.update_status(f"{profile_name}: '{matched_name}' ปิดตอบแชทหลักไว้ (ไม่ได้ส่ง)", "orange")
                self.notify_new_chat(profile_name, matched_name, 'main_off', message=preview)

        except Exception as e:
            self.update_status(f"{profile_name}: ตอบแชทไม่สำเร็จ - {str(e)[:80]}", "red")

    def handle_followup(self, profile_name, driver, thread_id, product_folders, info, row_key, preview=""):
        """แชทที่ส่ง main ไปแล้วและลูกค้าทักกลับมา — ส่งโฟลเดอร์ถัดไปให้อัตโนมัติ
        คืน True ถ้าเปิดหน้าแชท (ให้ผู้เรียกหน่วงเวลาต่อ)"""
        category, new_stage, reason = self.next_reply_stage(info, row_key)

        if reason == 'nochange':
            return False

        if reason == 'unmatched':
            # แชทที่โปรแกรมไม่ได้ตอบให้ (จับคู่ไม่ได้ / แชทเก่า / ส่งไม่ออก) แต่ลูกค้าพิมพ์มาอีกต้องรู้
            changed = info.get('row_key') is not None and info.get('row_key') != row_key
            info['row_key'] = row_key
            if changed:
                self.save_reply_settings()
                self.update_status(f"{profile_name}: '{info.get('product', '?')}' ทักมาอีก (ยังต้องตอบเอง)", "orange")
                again = {'old': 'old_chat', 'failed': 'send_failed'}.get(info.get('status'), 'unmatched_again')
                self.notify_new_chat(profile_name, info.get('product', ''), again, message=preview)
            return False

        if reason == 'baseline':
            info['row_key'] = row_key  # เก็บฐานเทียบไว้ก่อน ยังไม่ส่งอะไร
            # เราเพิ่งส่งไป แต่ข้อความล่าสุดในแถวเป็นของลูกค้า = เขาตอบกลับมาก่อนรอบสแกนนี้
            # ไม่แจ้งตรงนี้ ข้อความนั้นจะกลายเป็นฐานเทียบ แล้วหายเงียบไปเลย (แจ้งอย่างเดียว ไม่ส่งโฟลเดอร์ถัดไป
            # เพราะถ้าอ่าน preview พลาด ได้แค่แจ้งเตือนเกินมา 1 อัน ไม่ใช่ยิงรีวิวใส่ลูกค้าที่ไม่ได้พิมพ์อะไร)
            answered = info.pop('just_sent', False) and bool(preview)
            self.save_reply_settings()
            if answered:
                self.update_status(f"{profile_name}: '{info.get('product', '?')}' ตอบกลับมาแล้ว (ต้องตอบเอง)", "orange")
                self.notify_new_chat(profile_name, info.get('product', ''), 'quick_reply', message=preview)
                return False
            # พิมพ์คีย์ให้เห็นด้วย ใช้ยืนยันตอน live-test ว่าอ่าน preview ของแถวได้จริง
            self.update_status(
                f"{profile_name}: เฝ้าแชท '{info.get('product', '?')}' (คีย์ {row_key[:24] or 'ว่าง!'})", "gray")
            return False

        if reason == 'done':
            info['row_key'] = row_key
            self.save_reply_settings()
            self.update_status(f"{profile_name}: '{info.get('product', '?')}' ทักมาอีก (ส่งครบแล้ว ต้องตอบเอง)", "orange")
            self.notify_new_chat(profile_name, info.get('product', ''), 'followup_done', message=preview)
            return False

        folder_info = product_folders.get(info.get('product'))
        if folder_info is None:
            # โฟลเดอร์สินค้าถูกย้าย/เปลี่ยนชื่อไปแล้ว — ห้ามนับว่าส่งครบ ไม่งั้นแชทนี้ตายไปเลย
            info['row_key'] = row_key
            self.save_reply_settings()
            self.update_status(f"{profile_name}: ไม่เจอโฟลเดอร์ '{info.get('product', '?')}' แล้ว ต้องตอบเอง", "orange")
            self.notify_new_chat(profile_name, info.get('product', ''), 'folder_missing', message=preview)
            return False

        category, new_stage, reason = self.next_reply_stage(
            info, row_key,
            {c for c in self.REPLY_STAGES if folder_info.get(c) and self.stage_enabled.get(c, True)})
        if reason == 'done':
            # ยังมีโฟลเดอร์ที่ยังไม่ได้ส่ง = เจ้าของปิดตอบออโต้ไว้ หรือโฟลเดอร์นั้นไม่มีไฟล์
            # ไม่งั้นคือส่งครบจริง — ข้อความแจ้งเตือนต้องแยกกัน ไม่งั้นอ่านแล้วเข้าใจผิด
            left = self.REPLY_STAGES[max(int(info.get('stage', 1)) - 1, 0):]
            status = 'followup_off' if left else 'followup_done'
            info['row_key'] = row_key
            self.save_reply_settings()
            self.update_status(f"{profile_name}: '{info.get('product', '?')}' ทักมาอีก (ไม่ได้ตอบ รอตอบเอง)", "orange")
            self.notify_new_chat(profile_name, info.get('product', ''), status, message=preview)
            return False

        try:
            driver.get(f"https://www.facebook.com/marketplace/t/{thread_id}/")
            self.wait_for_page_load(driver)
            time.sleep(random.uniform(2, 4))
            sent_ok = self.send_folder_content(driver, folder_info[category])
        except Exception as e:
            self.update_status(f"{profile_name}: ส่ง {category} อัตโนมัติไม่สำเร็จ - {str(e)[:80]}", "red")
            return True

        label = self.STAGE_LABELS.get(category, category)
        if not sent_ok:
            # ไม่ขยับ stage ลูกค้าพิมพ์มาอีกรอบหน้าจะลองส่งโฟลเดอร์นี้ใหม่ — ห้ามแจ้งว่าส่งแล้ว
            info['row_key'] = None
            self.save_reply_settings()
            self.update_status(f"{profile_name}: ส่ง{label}ให้ '{info.get('product', '?')}' ไม่สำเร็จ ต้องตอบเอง", "red")
            self.notify_new_chat(profile_name, info.get('product', ''), 'send_failed', message=preview)
            return True

        info['stage'] = new_stage
        info['row_key'] = None  # ส่งแล้ว preview เปลี่ยนเพราะเราเอง รอบหน้าเก็บฐานใหม่
        info['just_sent'] = True
        info['replied_at'] = time.strftime('%Y-%m-%d %H:%M')
        self.save_reply_settings()
        self.root.after(0, self.update_reply_list)
        self.update_status(f"{profile_name}: ส่ง{label}ให้ '{info.get('product', '?')}' อัตโนมัติแล้ว", "green")
        self.notify_new_chat(profile_name, info.get('product', ''), 'followup', category, message=preview)
        return True

    def manual_send_category(self, category):
        """ส่งโฟลเดอร์รีวิว(review)/เพิ่มเติม(extra) ให้แชทที่เลือกจากลิสต์ 'แชทที่ตอบไปแล้ว' ด้วยมือ
        ต้องกำลังรัน 'เริ่มตอบแชทอัตโนมัติ' อยู่ (Chrome ของ Profile นั้นต้องยังเปิดค้างอยู่)"""
        sel = self.reply_listbox.curselection()
        if not sel:
            messagebox.showwarning("คำเตือน", "กรุณาเลือกแชทจากรายการก่อน")
            return
        profile_name, thread_id = self._reply_list_index[sel[0]]
        info = self.reply_state.get(profile_name, {}).get(thread_id)
        if not info or info.get('status') != 'replied':
            messagebox.showwarning("คำเตือน", "แชทนี้ยังไม่ได้จับคู่สินค้าสำเร็จ ส่งเพิ่มไม่ได้")
            return

        driver = self.reply_drivers.get(profile_name)
        if not driver:
            messagebox.showwarning("คำเตือน", f"Chrome ของ {profile_name} ไม่ได้เปิดอยู่ (ต้องกดเริ่มตอบแชทอัตโนมัติก่อน)")
            return

        product_folders = self.scan_product_folders(self.reply_root_folder)
        folder_info = product_folders.get(info['product'])
        if not folder_info:
            messagebox.showwarning("คำเตือน", "ไม่พบโฟลเดอร์สินค้านี้แล้ว")
            return

        assets = folder_info.get(category)
        if not assets:
            messagebox.showwarning("คำเตือน", f"โฟลเดอร์ {category} ของสินค้านี้ไม่มี")
            return

        def worker():
            try:
                lock = self.driver_locks.setdefault(profile_name, threading.Lock())
                if lock.locked():
                    self.update_status(f"{profile_name}: รอ Chrome จบรอบที่ทำอยู่ก่อน แล้วจะส่งให้", "blue")
                # Chrome ตัวนี้ลูปเฝ้าแชทใช้อยู่ด้วย สั่งซ้อนกัน = มันพาไปห้องอื่นกลางคัน ของไปลงผิดลูกค้า
                with lock:
                    thread_href = f"https://www.facebook.com/marketplace/t/{thread_id}/"
                    driver.get(thread_href)
                    self.wait_for_page_load(driver)
                    time.sleep(random.uniform(2, 4))
                    sent_ok = self.send_folder_content(driver, assets)
                if not sent_ok:
                    self.update_status(f"{profile_name}: ส่ง {category} ให้ '{info['product']}' ไม่สำเร็จ", "red")
                    return
                # ขยับ stage ด้วย ไม่งั้นระบบออโต้ส่งโฟลเดอร์เดิมซ้ำตอนลูกค้าทักกลับมา
                if category in self.REPLY_STAGES:
                    info['stage'] = max(int(info.get('stage', 1)), self.REPLY_STAGES.index(category) + 2)
                    info['row_key'] = None
                    info['just_sent'] = True
                    self.save_reply_settings()
                self.update_status(f"{profile_name}: ส่ง {category} ให้ '{info['product']}' แล้ว", "green")
            except Exception as e:
                self.update_status(f"ส่ง {category} ไม่สำเร็จ: {str(e)[:80]}", "red")

        threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.root.mainloop()


def source_version(src):
    """เลข APP_VERSION ในโค้ดที่โหลดมา (หาไม่เจอ = 0 ถือว่าไม่ใช่ไฟล์โปรแกรม ไม่เอามารัน)"""
    m = re.search(r'^APP_VERSION\s*=\s*(\d+)', src, re.MULTILINE)
    return int(m.group(1)) if m else 0


def cached_update():
    """(เวอร์ชัน, โค้ด compile แล้ว) ของไฟล์ที่โหลดเก็บไว้ — ไม่มีไฟล์/ไฟล์พัง = (0, None)"""
    try:
        with open(UPDATE_FILE, encoding='utf-8', newline='') as f:
            src = f.read()
        return source_version(src), compile(src, UPDATE_FILE, 'exec')
    except Exception:
        return 0, None


def load_update():
    """โค้ดเวอร์ชันใหม่กว่าที่ฝังใน exe (compile แล้ว) — ไม่มี/โหลดไม่ได้/ไฟล์พัง = None
    โหลดได้ก็เก็บลงไฟล์ไว้ เน็ตล่มรอบหน้าจะได้ไม่ถอยกลับไปตัวเก่าที่ฝังมา"""
    try:
        # หน้าต่างยังไม่ขึ้นจนกว่าจะเช็คเสร็จ เน็ตอืดเกิน 5 วิ ใช้ตัวที่มีอยู่ไปก่อน
        with urllib.request.urlopen(UPDATE_URL, timeout=5) as resp:
            src = resp.read().decode('utf-8-sig')
        # เทียบกับตัวที่โหลดเก็บไว้ด้วย ไม่งั้นพอเลขบน main สูงกว่า exe แล้ว ทุก push ถึงลูกค้าทั้งที่ยังไม่เพิ่มเลข
        if source_version(src) > max(APP_VERSION, cached_update()[0]):
            # เขียนไฟล์ชั่วคราวแล้วค่อยสลับ ไฟดับกลางคันจะได้ไม่เหลือไฟล์ครึ่งเดียวที่รันแล้วไม่มีหน้าต่างขึ้น
            with open(UPDATE_FILE + '.part', 'w', encoding='utf-8', newline='') as f:
                f.write(src)
            os.replace(UPDATE_FILE + '.part', UPDATE_FILE)
    except Exception:
        pass
    version, code = cached_update()
    return code if version > APP_VERSION else None


def run_update():
    """รันโค้ดตัวใหม่แทนตัวที่ฝังใน exe — คืน False ถ้าไม่มีตัวใหม่ หรือตัวใหม่เปิดไม่ขึ้น (ให้ใช้ตัวที่ฝังมา)"""
    # ponytail: อัปเดตได้แค่ไฟล์นี้ โค้ดใหม่ import ไลบรารีที่ exe ไม่ได้ฝังมา = ต้อง build exe ใหม่
    code = load_update()
    if not code:
        return False
    try:
        exec(code, {'__name__': '__main__', 'UPDATED': True})
        return True
    except Exception:
        return False


if __name__ == "__main__":
    # เปิด .py ด้วย Python ในเครื่อง (เช่น VS Code) ที่ไม่มี selenium = uc เป็น None
    # กด Login แล้วขึ้น 'NoneType' object has no attribute 'ChromeOptions' ลูกค้าอ่านไม่รู้เรื่อง บอกตั้งแต่เปิด
    if uc is None:
        messagebox.showerror("เปิดผิดไฟล์", "ไฟล์ .py เปิดตรงๆ ไม่ได้ ให้เปิดที่ Renew Product.exe")
        sys.exit(1)
    # exe เท่านั้นที่อัปเดตตัวเอง รันจาก .py ตรงๆ (ตอนแก้โค้ด) ต้องได้โค้ดในเครื่อง
    if globals().get('UPDATED') or not getattr(sys, 'frozen', False) or not run_update():
        app = FacebookMarketplaceRenewer()
        app.run()
