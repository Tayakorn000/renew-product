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
import re
import configparser
import threading
import json
import base64
import random

class FacebookMarketplaceRenewer:
    IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp'}
    VIDEO_EXTS = {'.mp4', '.mov', '.avi', '.mkv', '.webm'}
    REVIEW_KEYWORDS = ['รีวิว']
    EXTRA_KEYWORDS = ['เพิ่มเติม']

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ต่ออายุสินค้า Facebook Marketplace")
        self.root.geometry("600x650")
        self.root.resizable(False, False)
        
        self.is_running = False
        self.settings_file = "renew_settings.json"
        self.profiles = {}
        self.current_profile = None

        # ตอบแชทอัตโนมัติ (Marketplace inbox)
        self.reply_settings_file = "reply_settings.json"
        self.reply_root_folder = None
        self.reply_state = {}  # {profile_name: {thread_id: {...}}}
        self.auto_reply_active = False
        self.reply_drivers = {}  # profile_name -> driver ที่ยังเปิดอยู่ระหว่างตอบแชท
        self._reply_list_index = []  # index ของ reply_listbox -> (profile_name, thread_id)

        # ตั้งค่าให้ปิด Chrome ทั้งหมดเมื่อปิดหน้าต่าง GUI
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # โหลดการตั้งค่าที่บันทึกไว้
        self.load_settings()
        self.load_reply_settings()
        self.setup_gui()
    
    def on_closing(self):
        """ฟังก์ชันที่ทำงานเมื่อปิดหน้าต่าง GUI"""
        try:
            # แสดง messagebox ยืนยัน
            if messagebox.askokcancel("ปิดโปรแกรม", "ต้องการปิดโปรแกรมและ Chrome ทั้งหมดหรือไม่?"):
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
    
    def add_human_behavior_scripts(self, driver):
        """เพิ่ม JavaScript เพื่อปลอม fingerprint และพฤติกรรม"""
        # สุ่ม noise สำหรับ canvas — ทั้งบวกและลบเพื่อไม่ให้เป็น pattern
        canvas_noise_r = random.randint(-5, 5)
        canvas_noise_g = random.randint(-5, 5)
        canvas_noise_b = random.randint(-5, 5)

        # สุ่ม WebGL vendor/renderer จากรายการที่เป็นไปได้จริง
        webgl_vendors = ['Intel Inc.', 'NVIDIA Corporation', 'AMD', 'Google Inc. (Intel)']
        webgl_renderers = [
            'Intel Iris OpenGL Engine',
            'ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0)',
            'ANGLE (NVIDIA, NVIDIA GeForce GTX 1650 Direct3D11 vs_5_0 ps_5_0)',
            'ANGLE (AMD, AMD Radeon RX 580 Direct3D11 vs_5_0 ps_5_0)',
        ]
        webgl_vendor = random.choice(webgl_vendors)
        webgl_renderer = random.choice(webgl_renderers)

        try:
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': f'''
                    // ซ่อน webdriver - Chrome จริง (ไม่ใช่ automation) คืนค่า false ไม่ใช่ undefined
                    Object.defineProperty(navigator, 'webdriver', {{get: () => false}});
                    
                    // ปลอม plugins
                    Object.defineProperty(navigator, 'plugins', {{
                        get: () => [
                            {{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'}},
                            {{name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''}},
                            {{name: 'Native Client', filename: 'internal-nacl-plugin', description: ''}}
                        ]
                    }});
                    
                    // ปลอม languages
                    Object.defineProperty(navigator, 'languages', {{get: () => ['th-TH', 'th', 'en-US', 'en']}});
                    
                    // เพิ่ม chrome object
                    window.chrome = {{
                        runtime: {{}},
                        loadTimes: function() {{}},
                        csi: function() {{}},
                        app: {{}}
                    }};
                    
                    // ปลอม permissions
                    const originalQuery = window.navigator.permissions.query;
                    window.navigator.permissions.query = (parameters) => (
                        parameters.name === 'notifications' ?
                            Promise.resolve({{state: Notification.permission}}) :
                            originalQuery(parameters)
                    );
                    
                    // ปลอม canvas fingerprint — เพิ่ม noise สุ่มทั้งบวกและลบเพื่อไม่ให้เป็น pattern
                    // ทำงานบน canvas สำเนา (ไม่แก้ canvas จริง) และ noise คงที่ต่อ session
                    // เพื่อให้เรียก toDataURL ซ้ำบน canvas เดิมได้ hash เดิมเสมอ (เหมือนเบราว์เซอร์จริง)
                    const _canvasNoise = [{canvas_noise_r}, {canvas_noise_g}, {canvas_noise_b}];
                    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
                    HTMLCanvasElement.prototype.toDataURL = function(type) {{
                        try {{
                            const ctx = this.getContext('2d');
                            if (ctx && this.width > 0 && this.height > 0) {{
                                const imageData = ctx.getImageData(0, 0, this.width, this.height);
                                for (let i = 0; i < imageData.data.length; i += 4) {{
                                    imageData.data[i]     = Math.max(0, Math.min(255, imageData.data[i]     + _canvasNoise[0]));
                                    imageData.data[i + 1] = Math.max(0, Math.min(255, imageData.data[i + 1] + _canvasNoise[1]));
                                    imageData.data[i + 2] = Math.max(0, Math.min(255, imageData.data[i + 2] + _canvasNoise[2]));
                                }}
                                const clone = document.createElement('canvas');
                                clone.width = this.width;
                                clone.height = this.height;
                                clone.getContext('2d').putImageData(imageData, 0, 0);
                                return originalToDataURL.apply(clone, arguments);
                            }}
                        }} catch(e) {{}}
                        return originalToDataURL.apply(this, arguments);
                    }};
                    
                    // ปลอม WebGL — สุ่ม vendor/renderer ต่างกันทุก session
                    const _wglVendor = '{webgl_vendor}';
                    const _wglRenderer = '{webgl_renderer}';
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                        if (parameter === 37445) {{ return _wglVendor; }}
                        if (parameter === 37446) {{ return _wglRenderer; }}
                        return getParameter.apply(this, arguments);
                    }};
                    const getParameter2 = WebGL2RenderingContext.prototype.getParameter;
                    WebGL2RenderingContext.prototype.getParameter = function(parameter) {{
                        if (parameter === 37445) {{ return _wglVendor; }}
                        if (parameter === 37446) {{ return _wglRenderer; }}
                        return getParameter2.apply(this, arguments);
                    }};
                '''
            })
        except:
            pass
    
    def _get_real_hardware_info(self):
        """ดึงข้อมูล hardware จริงจากเครื่อง เพื่อให้ค่าสอดคล้องกับเครื่องจริง"""
        import subprocess
        
        # ดึง CPU cores จริง
        try:
            import os
            real_cores = os.cpu_count() or 4
        except:
            real_cores = 4
        
        # ดึง RAM จริง (แปลงเป็น GB แบบ deviceMemory — ปัดเป็น 1, 2, 4, 8, 16, 32)
        try:
            import psutil
            ram_bytes = psutil.virtual_memory().total
            ram_gb = ram_bytes / (1024 ** 3)
            # deviceMemory API ปัดลง power of 2
            for val in [32, 16, 8, 4, 2, 1]:
                if ram_gb >= val:
                    real_mem = val
                    break
            else:
                real_mem = 4
        except:
            real_mem = 8
        
        # ดึง Timezone จริง
        try:
            import datetime
            offset_sec = -time.timezone if time.daylight == 0 else -time.altzone
            real_tz_offset = offset_sec // 60  # นาที
        except:
            real_tz_offset = 420  # Asia/Bangkok default (UTC+7)
        
        return real_cores, real_mem, real_tz_offset

    def add_advanced_stealth_scripts(self, driver):
        """เพิ่ม scripts ซ่อนตัวขั้นสูง - แก้ headless detection และอื่นๆ"""
        # ใช้ screen config เดียวกับที่ตั้ง window size (ต้อง sync กัน)
        if hasattr(self, '_chosen_screen'):
            sw, sh, sah = self._chosen_screen
        else:
            # fallback ถ้าไม่มี
            screen_configs = [
                (1920, 1080, 1040), (1920, 1200, 1160),
                (1680, 1050, 1010), (1440, 900, 860), (1366, 768, 728),
            ]
            sw, sh, sah = random.choice(screen_configs)

        # หน้าต่างจริงถูกย้ายออกนอกจอ (set_window_position(-2500, 0)) แต่ต้องปลอม
        # window.screenX/Y ให้เป็นค่าที่คนจริงจะมี (อยู่ในจอ) ไม่งั้นค่าติดลบจะเป็นจุดสังเกตชัดเจน
        win_w, win_h = getattr(self, '_chosen_window_size', (sw, sah))
        fake_screen_x = random.randint(0, max(0, sw - win_w))
        fake_screen_y = random.randint(0, max(0, sah - win_h))

        # ดึงค่า hardware จริงจากเครื่อง เพื่อให้สอดคล้องกับเครื่องจริง
        real_cores, real_mem, real_tz_offset = self._get_real_hardware_info()
        
        # hardware concurrency: ใช้ค่าจริง ±0 (ไม่สุ่ม เพราะต้องตรงกับเครื่อง)
        hw_cores = real_cores
        # device memory: ใช้ค่าจริง
        hw_mem = real_mem
        rtt_val  = random.randint(20, 80)
        dl_val   = round(random.uniform(5, 20), 1)

        try:
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': f'''
                    // แก้ headless detection
                    Object.defineProperty(navigator, 'maxTouchPoints', {{get: () => 0}});
                    Object.defineProperty(navigator, 'platform', {{get: () => 'Win32'}});
                    Object.defineProperty(navigator, 'vendor', {{get: () => 'Google Inc.'}});
                    
                    // ปลอม battery API
                    Object.defineProperty(navigator, 'getBattery', {{
                        get: () => async () => ({{
                            charging: true,
                            chargingTime: 0,
                            dischargingTime: Infinity,
                            level: 1
                        }})
                    }});
                    
                    // ปลอม connection — สุ่ม rtt/downlink ต่างกันทุก session
                    Object.defineProperty(navigator, 'connection', {{
                        get: () => ({{
                            effectiveType: '4g',
                            rtt: {rtt_val},
                            downlink: {dl_val},
                            saveData: false
                        }})
                    }});
                    
                    // ปลอม screen properties — สุ่ม resolution ต่างกันทุก session
                    Object.defineProperty(screen, 'availWidth',  {{get: () => {sw}}});
                    Object.defineProperty(screen, 'availHeight', {{get: () => {sah}}});
                    Object.defineProperty(screen, 'width',       {{get: () => {sw}}});
                    Object.defineProperty(screen, 'height',      {{get: () => {sh}}});
                    Object.defineProperty(screen, 'colorDepth',  {{get: () => 24}});
                    Object.defineProperty(screen, 'pixelDepth',  {{get: () => 24}});

                    // หน้าต่างจริงถูกย้ายออกนอกจอ - ปลอมตำแหน่งให้ดูเหมือนอยู่ในจอปกติ
                    Object.defineProperty(window, 'screenX',    {{get: () => {fake_screen_x}}});
                    Object.defineProperty(window, 'screenY',    {{get: () => {fake_screen_y}}});
                    Object.defineProperty(window, 'screenLeft', {{get: () => {fake_screen_x}}});
                    Object.defineProperty(window, 'screenTop',  {{get: () => {fake_screen_y}}});

                    // ปลอม hardwareConcurrency — ใช้ค่าจริงจากเครื่อง
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {hw_cores}}});
                    
                    // ปลอม deviceMemory — ใช้ค่าจริงจากเครื่อง
                    Object.defineProperty(navigator, 'deviceMemory', {{get: () => {hw_mem}}});
                    
                    // ปลอม timezone offset ให้ตรงกับเครื่องจริง
                    const _realTzOffset = {real_tz_offset};
                    const _origDateGetTimezoneOffset = Date.prototype.getTimezoneOffset;
                    Date.prototype.getTimezoneOffset = function() {{
                        return -_realTzOffset;
                    }};
                    
                    // ซ่อน automation indicators
                    delete navigator.__proto__.webdriver;
                    
                    // ปลอม chrome runtime
                    if (!window.chrome) {{ window.chrome = {{}}; }}
                    if (!window.chrome.runtime) {{ window.chrome.runtime = {{}}; }}
                    
                    // ปลอม media devices
                    if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {{
                        const originalEnumerateDevices = navigator.mediaDevices.enumerateDevices;
                        navigator.mediaDevices.enumerateDevices = async function() {{
                            const devices = await originalEnumerateDevices.call(this);
                            return devices.length > 0 ? devices : [
                                {{deviceId: 'default', kind: 'audioinput', label: '', groupId: ''}},
                                {{deviceId: 'default', kind: 'videoinput', label: '', groupId: ''}}
                            ];
                        }};
                    }}
                '''
            })
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
        except Exception:
            pass

    def save_reply_settings(self):
        """บันทึกการตั้งค่าตอบแชทอัตโนมัติ"""
        try:
            data = {'root_folder': self.reply_root_folder, 'state': self.reply_state}
            with open(self.reply_settings_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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
        
        # กรอบจัดการ Profile
        profile_frame = tk.LabelFrame(self.root, text="จัดการ Profile", font=("Arial", 10, "bold"), padx=10, pady=10)
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
        button_frame = tk.Frame(self.root)
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
        reply_frame = tk.LabelFrame(self.root, text="ตอบแชทลูกค้าอัตโนมัติ (Marketplace)", font=("Arial", 10, "bold"), padx=10, pady=10)
        reply_frame.pack(pady=5, padx=20, fill=tk.BOTH, expand=True)

        folder_row = tk.Frame(reply_frame)
        folder_row.pack(fill=tk.X, pady=3)
        tk.Label(folder_row, text="โฟลเดอร์สินค้า:", font=("Arial", 9), width=12, anchor=tk.W).pack(side=tk.LEFT)
        self.reply_folder_var = tk.StringVar(value=self.reply_root_folder or "ยังไม่ได้เลือก")
        tk.Label(folder_row, textvariable=self.reply_folder_var, font=("Arial", 9), fg="gray", anchor=tk.W).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        tk.Button(folder_row, text="เลือกโฟลเดอร์", command=self.browse_reply_folder, font=("Arial", 9), cursor="hand2").pack(side=tk.RIGHT)

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

        # สถานะ
        self.status_label = tk.Label(
            self.root,
            text="พร้อมใช้งาน",
            font=("Arial", 9),
            fg="gray"
        )
        self.status_label.pack(pady=5)
        
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
            self.root.after(0, lambda: messagebox.showerror("ผิดพลาด", f"Login ด้วยมือไม่สำเร็จ: {str(e)}"))

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
            driver.get("https://www.facebook.com/login")

            self.root.after(0, lambda: messagebox.showinfo(
                "Login ด้วยตัวเอง",
                f"กรุณา Login Facebook ในหน้าต่าง Chrome ที่เปิดขึ้น ({profile_name})\n\n"
                "เสร็จแล้วกด OK ที่นี่เพื่อบันทึก Cookie"
            ))

            # รอจนกว่าจะออกจากหน้า login (ผู้ใช้ Login เสร็จ) สูงสุด 10 นาที
            max_wait = 600
            waited = 0
            login_done = False
            while waited < max_wait:
                time.sleep(2)
                waited += 2
                try:
                    current_url = driver.current_url
                except Exception:
                    break
                if "facebook.com" in current_url and "login" not in current_url.lower():
                    login_done = True
                    break

            if not login_done:
                raise Exception("หมดเวลารอ Login (10 นาที) หรือ Browser ถูกปิดก่อน Login เสร็จ")

            self._save_cookies_to_ini(driver, config_file_path, force=True)
            self.update_status(f"{profile_name}: บันทึก Cookie สำเร็จ", "green")
            self.root.after(0, lambda: messagebox.showinfo("สำเร็จ", f"บันทึก Cookie ของ {profile_name} แล้ว\nครั้งต่อไปไม่ต้อง Login ซ้ำ"))
        finally:
            try:
                driver.quit()
            except Exception:
                pass

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
            self.root.after(0, lambda: messagebox.showerror("ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}"))
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

    def _try_cookie_login(self, driver, cookies_raw, target_url):
        """Inject Cookies เข้า driver แล้วเช็คว่า Login ผ่านไหม (เหมือน FBMKP แต่พอร์ตมาใช้กับ Selenium)"""
        cookies_list = self._parse_cookies_to_list(cookies_raw)
        if not cookies_list:
            return False

        # ต้องอยู่โดเมน facebook.com ก่อนถึงจะ add_cookie ได้ (ข้อจำกัดของ Selenium)
        driver.get("https://www.facebook.com/")
        time.sleep(1)

        injected = 0
        for c in cookies_list:
            name = c.get('name')
            value = c.get('value')
            if not name or value is None:
                continue

            cookie = {
                'name': name,
                'value': value,
                'domain': c.get('domain') or '.facebook.com',
                'path': c.get('path') or '/',
            }

            expiry = c.get('expiry', c.get('expires'))
            if isinstance(expiry, (int, float)) and expiry > 0:
                cookie['expiry'] = int(expiry)

            same_site = c.get('sameSite')
            if same_site in ('Strict', 'Lax', 'None'):
                cookie['sameSite'] = same_site

            try:
                driver.add_cookie(cookie)
                injected += 1
            except Exception:
                continue

        if injected == 0:
            return False

        driver.get(target_url)
        time.sleep(random.uniform(3, 5))

        try:
            current_url = driver.current_url
            if "login" in current_url.lower():
                return False
            if driver.find_elements(By.NAME, "email"):
                return False
        except Exception:
            return False

        return True

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

        cookies_json_str = json.dumps(all_cookies, ensure_ascii=False)
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

        with open(ini_path, 'w', encoding='utf-8') as f:
            f.write(ini_content)

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
            
            # อ่านไฟล์ config
            config = configparser.ConfigParser()
            config.read(config_file_path, encoding='utf-8')
            
            # อ่านข้อมูลล็อคอินจาก section [FBAccount]
            user_id = ""
            password = ""
            
            if config.has_section('FBAccount'):
                if config.has_option('FBAccount', 'UserID'):
                    user_id = config.get('FBAccount', 'UserID').strip()
                if config.has_option('FBAccount', 'Password'):
                    password = config.get('FBAccount', 'Password').strip()

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
            
            # สุ่ม screen config ที่จะใช้ทั้ง window size และ stealth script ให้ตรงกัน
            # (screen_width, screen_height, available_height)
            self._screen_configs_pool = [
                (1920, 1080, 1040),
                (1920, 1200, 1160),
                (1680, 1050, 1010),
                (1440, 900, 860),
                (1366, 768, 728),
            ]
            self._chosen_screen = random.choice(self._screen_configs_pool)
            chosen_sw, chosen_sh, chosen_sah = self._chosen_screen
            
            # Window size ต้องเล็กกว่าหรือเท่ากับ screen resolution (คนจริงไม่ได้ maximize เสมอ)
            # สุ่มให้เล็กกว่า screen เล็กน้อย หรือเท่ากับ screen (maximize)
            if random.random() < 0.4:
                # 40% maximize เต็มจอ
                win_w = chosen_sw
                win_h = chosen_sah  # ใช้ available height (หัก taskbar)
            else:
                # 60% ไม่เต็มจอ — ลดขนาดลงเล็กน้อย
                win_w = chosen_sw - random.randint(0, 200)
                win_h = chosen_sah - random.randint(0, 150)
            
            chrome_options.add_argument(f"--window-size={win_w},{win_h}")
            self._chosen_window_size = (win_w, win_h)
            
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
            
            # ย้ายหน้าต่างออกนอกจอ (เพื่อให้ viewport ยังมีขนาดปกติ)
            driver.set_window_position(-2500, 0)
            
            # inject fingerprint scripts ทันทีหลังเปิด Chrome
            # ต้อง inject ก่อนเปิดหน้าเว็บใดๆ เพื่อให้มีผลตั้งแต่หน้าแรก
            try:
                self.add_human_behavior_scripts(driver)
                self.add_advanced_stealth_scripts(driver)
            except:
                pass
            
            # รอหลังเปิด Chrome ก่อนเข้า Facebook — สุ่มให้ไม่เป็น pattern
            wait_after_open = random.uniform(8, 15)
            self.update_status(f"{profile_name}: รอ {int(wait_after_open)} วินาทีหลังเปิด Chrome...", "blue")
            time.sleep(wait_after_open)
            
            # เก็บสถานะว่าหน้าต่างถูกย้ายออกนอกจอ
            self.window_minimized = True
            
            # ตรวจสอบว่าล็อคอินอยู่แล้วหรือไม่
            driver.get("https://www.facebook.com/")
            time.sleep(random.uniform(4, 7))  # รอแบบสุ่ม
            
            # จำลองการอ่านหน้าเว็บ
            if random.random() < 0.4:  # 40% โอกาส
                self.human_like_read_page(driver)
            
            # ตรวจสอบว่าอยู่ในหน้า Facebook หลักหรือหน้าล็อคอิน
            is_logged_in = False
            
            try:
                # รอให้หน้าเว็บโหลดเสร็จก่อน
                time.sleep(3)
                
                # ตรวจสอบจาก URL ก่อน
                current_url = driver.current_url
                
                # ถ้า URL มี "login" แสดงว่ายังไม่ได้ล็อคอิน
                if "login" in current_url.lower():
                    is_logged_in = False
                    self.update_status(f"{profile_name}: ยังไม่ได้ล็อคอิน", "orange")
                else:
                    # ลองหาช่อง email (รอสูงสุด 5 วินาที)
                    try:
                        WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.NAME, "email"))
                        )
                        # เจอช่อง email = ยังไม่ได้ล็อคอิน
                        is_logged_in = False
                        self.update_status(f"{profile_name}: ยังไม่ได้ล็อคอิน", "orange")
                    except:
                        # ไม่เจอช่อง email = ล็อคอินอยู่แล้ว
                        is_logged_in = True
                        self.update_status(f"{profile_name}: ล็อคอินอยู่แล้ว", "green")
            except:
                # ถ้า error ให้ถือว่ายังไม่ได้ล็อคอิน (ปลอดภัยกว่า)
                is_logged_in = False
                self.update_status(f"{profile_name}: ไม่แน่ใจ กำลังลองล็อคอิน...", "orange")

            # ถ้ายังไม่ได้ล็อคอิน ลอง Login ด้วย Cookie ก่อน (เหมือน FBMKP)
            cookie_login_ok = False
            if not is_logged_in and cookies_raw:
                self.update_status(f"{profile_name}: กำลังลอง Login ด้วย Cookie...", "blue")
                cookie_login_ok = self._try_cookie_login(driver, cookies_raw, target_url)
                if cookie_login_ok:
                    is_logged_in = True
                    self.update_status(f"{profile_name}: Login ด้วย Cookie สำเร็จ", "green")
                else:
                    self.update_status(f"{profile_name}: Cookie หมดอายุหรือไม่ถูกต้อง", "orange")

            # ถ้ายังไม่ได้ล็อคอิน ให้ทำการล็อคอินด้วย User/Password
            if not is_logged_in:
                if not (user_id and password):
                    raise Exception(f"Cookie ของ Profile '{profile_name}' หมดอายุ และไม่มี UserID/Password สำรอง - กรุณา Login ด้วยมือใหม่ (ปุ่ม \"Login ด้วยมือ (บันทึก Cookie)\")")

                self.update_status(f"{profile_name}: กำลังล็อคอิน...", "blue")

                # รอให้ช่อง email ปรากฏ (ใช้ name="email" แทน ID)
                email_field = WebDriverWait(driver, 15).until(
                    EC.element_to_be_clickable((By.NAME, "email"))
                )
                
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
                
                # ตรวจสอบว่ายังอยู่หน้า login หรือไม่ (ล็อคอินไม่สำเร็จ)
                if "login" in current_url.lower():
                    try:
                        if driver.find_elements(By.NAME, "email"):
                            raise Exception("ล็อคอินไม่สำเร็จ - ยังอยู่หน้า login")
                    except:
                        pass
                
                # ตรวจสอบว่าเจอหน้ายืนยันตัวตนหรือไม่ (ทุกรูปแบบ)
                auth_keywords = ["two_step_verification", "checkpoint", "auth_platform/afad", "login/device-based", "login/identify"]
                is_auth_page = any(keyword in current_url for keyword in auth_keywords)
                
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

            # บันทึก Cookie ใหม่ไว้ใช้ครั้งต่อไป - เขียนทับเฉพาะตอน Cookie เดิมพิสูจน์แล้วว่าหมดอายุ
            try:
                self._save_cookies_to_ini(driver, config_file_path, force=bool(cookies_raw) and not cookie_login_ok)
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
            
            # ย้ายหน้าต่างออกนอกจอหลังเข้าหน้าต่ออายุสำเร็จ
            try:
                driver.set_window_position(-2500, 0)
                self.window_minimized = True
            except:
                pass
            
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
    
    def renew_profile_worker(self, profile_name):
        """Worker thread สำหรับต่ออายุ Profile"""
        driver = None
        renew_page_url = "https://www.facebook.com/marketplace/selling/renew_listings/"
        
        try:
            driver = self.profile_status[profile_name]['driver']
            
            if not driver:
                raise Exception("ไม่พบ Chrome driver")
            
            renewed_count = 0
            no_button_refresh_count = 0
            renew_url_use_count = 0  # นับจำนวนครั้งที่ใช้ URL Renew
            
            while True:
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
            
            # ปิด Chrome
            try:
                driver.quit()
                self.update_status(f"{profile_name}: ปิด Chrome แล้ว", "gray")
            except:
                pass
            
        except Exception as e:
            self.profile_status[profile_name]['stage'] = 'failed'
            self.profile_status[profile_name]['error'] = str(e)
            self.update_status(f"{profile_name}: ล้มเหลว - {str(e)[:50]}", "red")
            
            # ปิด Chrome ถ้ายังเปิดอยู่
            if driver:
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
        """ส่งรูป+วิดีโอก่อน แล้วค่อยส่งข้อความจาก .txt ทีละย่อหน้า"""
        media_files = assets.get('images', []) + assets.get('videos', [])
        if media_files:
            self.upload_files_to_chat(driver, media_files)
            self.random_sleep(2, 5)

        for msg in self.split_text_to_messages(assets.get('text', '')):
            self.send_chat_message(driver, msg)
            self.random_sleep(2, 6)

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
        for profile_name, threads in self.reply_state.items():
            for thread_id, info in threads.items():
                status_txt = "✓ ตอบแล้ว" if info.get('status') == 'replied' else "⚠ จับคู่ไม่ได้"
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
            self.root.after(0, lambda: messagebox.showerror("ข้อผิดพลาด", f"เกิดข้อผิดพลาด: {str(e)}"))
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
                self.update_status(f"{profile_name}: เปิดไม่สำเร็จ - {str(e)[:80]}", "red")
                continue

        for t in threads:
            t.join()

        self.update_status("หยุดตอบแชทอัตโนมัติทุก Profile แล้ว", "green")

    def auto_reply_worker(self, profile_name, driver, product_folders):
        """monitor inbox ของ Profile นี้ วนหาแชทใหม่แล้วตอบอัตโนมัติ จนกว่า auto_reply_active จะเป็น False"""
        self.reply_state.setdefault(profile_name, {})

        while self.auto_reply_active:
            try:
                driver.current_url
            except Exception:
                self.update_status(f"{profile_name}: Chrome ถูกปิดไปแล้ว", "red")
                break

            try:
                driver.get("https://www.facebook.com/marketplace/inbox/")
                self.wait_for_page_load(driver)
                time.sleep(random.uniform(2, 4))

                rows = self.find_all(driver, 'conversation_row')
                seen_this_pass = set()
                for row in rows:
                    if not self.auto_reply_active:
                        break
                    try:
                        href = row.get_attribute('href')
                    except Exception:
                        continue
                    if not href or '/t/' not in href:
                        continue

                    thread_id = href.split('/t/')[-1].split('/')[0].split('?')[0]
                    if not thread_id or thread_id in seen_this_pass:
                        continue
                    seen_this_pass.add(thread_id)

                    if thread_id in self.reply_state[profile_name]:
                        continue  # ตอบ/ตรวจไปแล้ว ข้าม

                    self.handle_one_conversation(profile_name, driver, href, thread_id, product_folders)
                    self.random_sleep(3, 8)

            except Exception as e:
                self.update_status(f"{profile_name}: Error สแกนแชท - {str(e)[:80]}", "orange")

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

    def handle_one_conversation(self, profile_name, driver, href, thread_id, product_folders):
        """เปิดแชทเดี่ยว ตรวจว่าเป็นข้อความแรกจากลูกค้าหรือไม่ จับคู่สินค้า แล้วส่งข้อมูล"""
        try:
            driver.get(href)
            self.wait_for_page_load(driver)
            time.sleep(random.uniform(2, 4))

            # หมายเหตุ: incoming_bubble นับแถวข้อความทั้งห้อง (ยังแยกฝั่งลูกค้า/เราไม่ได้ในตอนนี้)
            # ใช้เป็นตัวกรองหยาบๆ ว่ายังไม่มีบทสนทนายาว ต้องปรับให้แม่นตอน live-test
            incoming = self.find_all(driver, 'incoming_bubble')
            if len(incoming) > 1:
                return  # มีข้อความมากกว่า 1 แถวแล้ว ข้าม (กันไปตอบทับบทสนทนาที่คุยต่อแล้ว)

            listing_el = self.find_first(driver, 'listing_title', wait=5)
            listing_name = listing_el.text.strip() if listing_el else ""

            matched_name = self.match_listing_to_folder(listing_name, product_folders)

            if not matched_name:
                self.reply_state[profile_name][thread_id] = {
                    'product': listing_name or '(ไม่พบชื่อสินค้า)',
                    'status': 'unmatched',
                    'replied_at': time.strftime('%Y-%m-%d %H:%M'),
                }
                self.save_reply_settings()
                self.root.after(0, self.update_reply_list)
                self.update_status(f"{profile_name}: จับคู่สินค้าไม่ได้ - '{listing_name}' (ข้ามไว้ให้ส่งเอง)", "orange")
                return

            folder_info = product_folders[matched_name]
            self.send_folder_content(driver, folder_info['main'])

            self.reply_state[profile_name][thread_id] = {
                'product': matched_name,
                'status': 'replied',
                'replied_at': time.strftime('%Y-%m-%d %H:%M'),
            }
            self.save_reply_settings()
            self.root.after(0, self.update_reply_list)
            self.update_status(f"{profile_name}: ตอบแชท '{matched_name}' แล้ว", "green")

        except Exception as e:
            self.update_status(f"{profile_name}: ตอบแชทไม่สำเร็จ - {str(e)[:80]}", "red")

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
                thread_href = f"https://www.facebook.com/marketplace/t/{thread_id}/"
                driver.get(thread_href)
                self.wait_for_page_load(driver)
                time.sleep(random.uniform(2, 4))
                self.send_folder_content(driver, assets)
                self.update_status(f"{profile_name}: ส่ง {category} ให้ '{info['product']}' แล้ว", "green")
            except Exception as e:
                self.update_status(f"ส่ง {category} ไม่สำเร็จ: {str(e)[:80]}", "red")

        threading.Thread(target=worker, daemon=True).start()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = FacebookMarketplaceRenewer()
    app.run()
