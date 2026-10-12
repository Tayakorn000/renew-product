"""self-check สำหรับ logic ที่ไม่ต้องพึ่ง Selenium (จับคู่โฟลเดอร์/ตัดเลขนำหน้า/แยกข้อความ)
รันบนเครื่องที่ไม่มี selenium ก็ได้ (import guard ใน Renew Product.py กันไว้แล้ว)
ส่วน DOM/Selenium (get_selectors, find_first, upload_files_to_chat, ...) ยังไม่ได้ทดสอบ
ต้อง live-test บนเครื่อง Windows ของลูกค้าที่มี Chrome + login จริง
"""
import importlib.util
import io
import os
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("renew_product", os.path.join(HERE, "Renew Product.py"))
renew_product = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renew_product)

App = renew_product.FacebookMarketplaceRenewer
app = App.__new__(App)  # ข้าม __init__ (ไม่เปิด Tkinter) เพราะ method พวกนี้ไม่แตะ self.root


def test_strip_leading_number():
    assert app.strip_leading_number("12. โซฟา 2 ที่นั่ง") == "โซฟา 2 ที่นั่ง"
    assert app.strip_leading_number("03_เตียงนอน") == "เตียงนอน"
    assert app.strip_leading_number("โต๊ะทำงาน") == "โต๊ะทำงาน"


def test_match_exact_one():
    folders = {"โซฟา 2 ที่นั่ง": {}, "เตียงนอน": {}}
    assert app.match_listing_to_folder("ขาย โซฟา 2 ที่นั่ง สีดำ", folders) == "โซฟา 2 ที่นั่ง"


def test_match_ambiguous_returns_none():
    folders = {"โซฟา": {}, "โซฟา 2 ที่นั่ง": {}}
    assert app.match_listing_to_folder("สนใจ โซฟา 2 ที่นั่ง สีดำ", folders) is None


def test_match_no_match_returns_none():
    folders = {"เตียงนอน": {}}
    assert app.match_listing_to_folder("สนใจโซฟา", folders) is None


def test_cookie_samesite_none_forces_secure():
    # Chrome ตีตก SameSite=None ที่ไม่มี Secure — xs/c_user ของ Facebook เป็นแบบนี้
    c = app._build_selenium_cookie({'name': 'xs', 'value': 'v', 'sameSite': 'None', 'secure': False})
    assert c['secure'] is True
    assert c['sameSite'] == 'None'


def test_cookie_keeps_secure_and_httponly():
    c = app._build_selenium_cookie({'name': 'c_user', 'value': '1', 'secure': True, 'httpOnly': True})
    assert c['secure'] is True and c['httpOnly'] is True
    assert c['domain'] == '.facebook.com' and c['path'] == '/'


def test_notify_text_names_the_profile():
    # ลูกค้ามี 20 เฟส ข้อความต้องบอกให้ได้ว่ามาจากเฟสไหน
    t = app.build_notify_text("ID7", "โช๊คหลัง PCX", "replied")
    assert "ID7" in t and "โช๊คหลัง PCX" in t and "ตอบอัตโนมัติให้แล้ว" in t

    t2 = app.build_notify_text("ID3", "", "unmatched", "โช้คหลัง PCX แต่งศูนย์")
    assert "ID3" in t2 and "ต้องตอบเอง" in t2 and "โช้คหลัง PCX แต่งศูนย์" in t2


def test_send_telegram_without_config_is_quiet():
    app.telegram_token = ""
    app.telegram_chat_id = ""
    ok, err = app.send_telegram("x")
    assert ok is False and "ยังไม่ได้ตั้งค่า" in err


def test_people_who_message_the_bot_get_added():
    def msg(chat_id, date, name="x"):
        return {"message": {"chat": {"id": chat_id, "first_name": name}, "date": date}}

    def member(chat_id, date, status):
        return {"my_chat_member": {"chat": {"id": chat_id, "title": "กลุ่มร้าน"}, "date": date,
                                   "new_chat_member": {"status": status}}}

    payload = {"ok": True, "result": [
        msg(111, 10), msg(222, 20, "พี่"), msg(222, 21, "พี่"),
        member(333, 30, "kicked"), member(-100, 40, "member")]}
    app.telegram_chat_id, app.telegram_seen = "111", 0

    # คนเดิมไม่ซ้ำ คนที่เตะบอทออกไม่นับ ดึงบอทเข้ากลุ่มนับ
    assert app.merge_telegram_chats(payload) == {"222": "พี่", "-100": "กลุ่มร้าน"}
    assert app.chat_id_list() == ["111", "222", "-100"] and app.telegram_seen == 40

    # ลบ 222 ออกจากช่องแล้ว ข้อความเก่าที่ยังค้างในคิว Telegram ต้องไม่ดึงกลับมา
    app.telegram_chat_id = "111,-100"
    assert app.merge_telegram_chats(payload) == {}
    assert app.chat_id_list() == ["111", "-100"]

    # ทักบอทมาใหม่ถึงจะกลับเข้ามา
    assert app.merge_telegram_chats({"result": [msg(222, 50, "พี่")]}) == {"222": "พี่"}
    assert app.merge_telegram_chats({"ok": False}) == {} and app.telegram_seen == 50


def test_bot_poll_is_throttled():
    calls = []
    real = renew_product.urllib.request.urlopen
    renew_product.urllib.request.urlopen = lambda *a, **k: (calls.append(1), io.BytesIO(b'{"result": []}'))[1]
    try:
        app.telegram_token, app.telegram_polled = "t", 0
        app.add_new_telegram_chats()
        app.add_new_telegram_chats()
        assert len(calls) == 1  # แจ้งเตือนถี่ๆ ถาม Telegram แค่รอบเดียว
        app.add_new_telegram_chats(force=True)
        assert len(calls) == 2  # ปุ่มทดสอบส่งต้องเช็คทันที
    finally:
        renew_product.urllib.request.urlopen = real
        app.telegram_token = ""


def test_exe_runs_newer_source_from_github():
    tmp = tempfile.mkdtemp()
    cache, ran = os.path.join(tmp, "renew_update.py"), os.path.join(tmp, "ran.txt")
    newer = renew_product.APP_VERSION + 1
    remote = {}

    def fake(*a, **k):
        if remote["src"] is None:
            raise OSError("offline")
        return io.BytesIO(remote["src"].encode("utf-8-sig"))  # ไฟล์จริงบน GitHub มี BOM

    real_open, real_file = renew_product.urllib.request.urlopen, renew_product.UPDATE_FILE
    renew_product.urllib.request.urlopen, renew_product.UPDATE_FILE = fake, cache
    try:
        # เวอร์ชันเท่าเดิม หรือได้หน้า error มาแทนไฟล์ = ไม่เก็บ ไม่รัน
        remote["src"] = f"APP_VERSION = {renew_product.APP_VERSION}\n"
        assert renew_product.run_update() is False and not os.path.exists(cache)
        remote["src"] = "<html>404</html>"
        assert renew_product.run_update() is False and not os.path.exists(cache)

        # เวอร์ชันใหม่กว่า = รันตัวใหม่ และบอกตัวใหม่ว่าไม่ต้องเช็คอัปเดตซ้ำ
        remote["src"] = f"APP_VERSION = {newer}\nopen({ran!r}, 'w').write(f'{{UPDATED}} A')\n"
        assert renew_product.run_update() is True and open(ran).read() == "True A"

        # push ต่อโดยไม่เพิ่มเลข = เครื่องที่โหลดเลขนี้ไปแล้วยังรันตัวเดิม (เลขใน exe ค้างที่เลขตอน build ตลอด)
        remote["src"] = f"APP_VERSION = {newer}\nopen({ran!r}, 'w').write('B')\n"
        assert renew_product.run_update() is True and open(ran).read() == "True A"

        # เน็ตล่มรอบถัดไป ยังได้ตัวใหม่จากไฟล์ที่เก็บไว้
        os.remove(ran)
        remote["src"] = None
        assert renew_product.run_update() is True and os.path.exists(ran)

        # ตัวใหม่ใช้ไลบรารีที่ exe ไม่มี หรือไฟล์ขาดกลาง = ถอยไปใช้ตัวที่ฝังมา
        remote["src"] = f"APP_VERSION = {newer + 1}\nimport no_such_module_xyz\n"
        assert renew_product.run_update() is False
        remote["src"] = f"APP_VERSION = {newer + 2}\ndef broken(:\n"
        assert renew_product.run_update() is False

        # แก้ไฟล์พังแล้ว push เลขเดิมซ้ำก็กลับมาได้ ไม่ค้างอยู่กับไฟล์พัง
        remote["src"] = f"APP_VERSION = {newer + 2}\nopen({ran!r}, 'w').write('C')\n"
        assert renew_product.run_update() is True and open(ran).read() == "C"
    finally:
        renew_product.urllib.request.urlopen, renew_product.UPDATE_FILE = real_open, real_file


def test_login_pending_url():
    # หน้ายืนยันตัวตนต้องนับว่า login ยังไม่เสร็จ ไม่งั้นบันทึก Cookie ครึ่งๆ กลางๆ
    assert app._is_login_pending_url("https://www.facebook.com/checkpoint/123") is True
    assert app._is_login_pending_url("https://www.facebook.com/login") is True
    assert app._is_login_pending_url("https://www.facebook.com/two_step_verification/x") is True
    assert app._is_login_pending_url("https://www.facebook.com/") is False
    assert app._is_login_pending_url("https://www.facebook.com/marketplace/inbox/") is False
    assert app._is_login_pending_url("") is False


def test_cookie_skips_nameless():
    assert app._build_selenium_cookie({'value': 'v'}) is None


def test_inbox_row_key_ignores_relative_time():
    # เวลาใน preview ขยับเอง ("2 นาที" -> "5 นาที") ห้ามนับว่าลูกค้าทักใหม่
    a = app.inbox_row_key("สมชาย\nโช๊คหลัง PCX\nคุณ: ราคา 1200 บาท\n2 นาที")
    b = app.inbox_row_key("สมชาย\nโช๊คหลัง PCX\nคุณ: ราคา 1200 บาท\n5 นาที")
    assert a == b
    c = app.inbox_row_key("สมชาย\nโช๊คหลัง PCX\nสนใจครับ\n1 นาที")
    assert c != a


def test_preview_message_reads_what_customer_typed():
    assert app.preview_message("สมชาย\nโช๊คหลัง PCX\nจ่ายปลายทางได้มั้ย · 2 นาที") == "จ่ายปลายทางได้มั้ย"
    # บางธีมเวลาอยู่บรรทัดแยก
    assert app.preview_message("สมชาย\nโช๊คหลัง PCX\nมีสีดำมั้ยครับ\n5 นาที") == "มีสีดำมั้ยครับ"


def test_preview_message_skips_our_own_message():
    # ข้อความล่าสุดเป็นของเราเอง ห้ามแปะว่า "ลูกค้าพิมพ์"
    assert app.preview_message("สมชาย\nโช๊คหลัง PCX\nคุณ: ราคา 1200 บาทครับ · 1 นาที") == ""
    assert app.preview_message("John\nPCX shock\nYou: sent a photo · 1m") == ""
    assert app.preview_message("") == ""
    assert app.preview_message("สมชาย\n2 นาที") == "สมชาย"


def test_notify_text_includes_customer_message():
    t = app.build_notify_text("ID7", "โช๊คหลัง PCX", "followup", "review", message="จ่ายปลายทางได้มั้ย")
    assert "ลูกค้าพิมพ์: จ่ายปลายทางได้มั้ย" in t and "ID7" in t
    # ไม่มีข้อความก็ไม่ต้องมีบรรทัดเปล่า
    assert "ลูกค้าพิมพ์" not in app.build_notify_text("ID7", "x", "replied")


def test_followup_backfill_sends_nothing():
    # รอบแรกหลังอัปเดตโปรแกรม ประวัติเก่าไม่มี row_key — ห้ามยิงรีวิวใส่ลูกค้าเก่าทุกคนพร้อมกัน
    info = {'product': 'โช๊คหลัง PCX', 'status': 'replied'}
    assert app.next_reply_stage(info, "abc") == (None, None, 'baseline')


def test_followup_no_change_sends_nothing():
    info = {'status': 'replied', 'stage': 1, 'row_key': 'abc'}
    assert app.next_reply_stage(info, "abc") == (None, None, 'nochange')


def test_followup_advances_stages_then_stops():
    info = {'status': 'replied', 'stage': 1, 'row_key': 'old'}
    assert app.next_reply_stage(info, "new") == ('review', 2, 'send')
    assert app.next_reply_stage({**info, 'stage': 2}, "new") == ('extra', 3, 'send')
    assert app.next_reply_stage({**info, 'stage': 3}, "new")[2] == 'done'


def test_followup_skips_missing_folder():
    # ไม่มีโฟลเดอร์รีวิว ให้ข้ามไปส่งข้อมูลเพิ่มเติมเลย
    info = {'status': 'replied', 'stage': 1, 'row_key': 'old'}
    assert app.next_reply_stage(info, "new", available={'extra'}) == ('extra', 3, 'send')
    assert app.next_reply_stage(info, "new", available=set())[2] == 'done'


def test_stage_toggle_skips_disabled_folder():
    # ปิด "รีวิวสินค้า" ไว้ ลูกค้าทักกลับมาต้องข้ามไปส่งรูปภาพเพิ่มเติมเลย
    info = {'status': 'replied', 'stage': 1, 'row_key': 'old'}
    assert app.next_reply_stage(info, "new", available={'extra'}) == ('extra', 3, 'send')
    # ปิดทั้งสองอัน = ไม่ส่งอะไรต่อ แจ้งเตือนอย่างเดียว
    assert app.next_reply_stage(info, "new", available=set())[2] == 'done'


def test_default_only_answers_the_first_message():
    # ลูกค้าถาม "จ่ายปลายทางได้มั้ย" ต้องแค่แจ้งเตือน ห้ามยิงรีวิวกลับไปแทนคำตอบ
    assert App.DEFAULT_STAGE_ENABLED['main'] is True
    assert App.DEFAULT_STAGE_ENABLED['review'] is False
    assert App.DEFAULT_STAGE_ENABLED['extra'] is False


def test_renew_due_respects_toggle_and_interval():
    app.renew_while_reply = False
    app.renew_interval_min = 30
    assert app.renew_due(0, now=10 ** 9) is False  # ไม่ติ๊ก = ไม่ต่ออายุ แม้ทิ้งไว้ทั้งวัน

    app.renew_while_reply = True
    assert app.renew_due(1000, now=1000 + 29 * 60) is False
    assert app.renew_due(1000, now=1000 + 30 * 60) is True
    assert app.renew_due(0.0) is True  # last_renew=0.0 ของรอบแรก = ต่ออายุเลย

    # ช่องนาทีลูกค้าพิมพ์เอง ว่าง/ตัวอักษร/0 ต้องไม่ทำให้ worker พัง
    for bad in ("", "  ", "ห้า", None, 0, -5):
        app.renew_interval_min = bad
        assert app.clean_interval(bad) == App.DEFAULT_RENEW_INTERVAL_MIN
        assert app.renew_due(1000, now=1000 + 30 * 60) is True


def test_notify_separates_disabled_from_finished():
    off = app.build_notify_text("ID7", "โช๊คหลัง PCX", "followup_off", message="จ่ายปลายทางได้มั้ย")
    assert "ปิดตอบออโต้ไว้" in off and "จ่ายปลายทางได้มั้ย" in off
    assert "ครบ" not in off  # ห้ามบอกว่าส่งครบแล้ว ทั้งที่ยังไม่ได้ส่ง
    assert "ครบ" in app.build_notify_text("ID7", "x", "followup_done")


def test_stage_labels_cover_every_stage():
    # GUI สร้าง checkbox จาก ALL_STAGES ถ้าขาด label จะ KeyError ตอนเปิดโปรแกรม
    assert set(App.ALL_STAGES) == set(App.STAGE_LABELS)
    assert App.ALL_STAGES[0] == 'main'


def test_followup_skips_unmatched_thread():
    info = {'status': 'unmatched', 'row_key': 'old'}
    assert app.next_reply_stage(info, "new") == (None, None, 'unmatched')


def test_split_text_to_messages():
    text = "ย่อหน้า 1\n\nย่อหน้า 2\n\n\nย่อหน้า 3"
    assert app.split_text_to_messages(text) == ["ย่อหน้า 1", "ย่อหน้า 2", "ย่อหน้า 3"]


def test_scan_product_folders(tmp_root="/tmp/_reply_scan_test"):
    import shutil
    shutil.rmtree(tmp_root, ignore_errors=True)
    os.makedirs(os.path.join(tmp_root, "1. โซฟา", "รีวิวลูกค้า"))
    os.makedirs(os.path.join(tmp_root, "1. โซฟา", "ข้อมูลเพิ่มเติม"))
    with open(os.path.join(tmp_root, "1. โซฟา", "info.txt"), "w", encoding="utf-8") as f:
        f.write("ราคา 1000 บาท")
    with open(os.path.join(tmp_root, "1. โซฟา", "รีวิวลูกค้า", "r1.txt"), "w", encoding="utf-8") as f:
        f.write("รีวิวดีมาก")

    result = app.scan_product_folders(tmp_root)
    assert "โซฟา" in result
    assert result["โซฟา"]["main"]["text"] == "ราคา 1000 บาท"
    assert result["โซฟา"]["review"]["text"] == "รีวิวดีมาก"
    assert result["โซฟา"]["extra"]["images"] == []
    shutil.rmtree(tmp_root, ignore_errors=True)


# ---- ลูปตอบแชทกับ Chrome ปลอม (ไม่มี Selenium ไม่มีเน็ต ไม่มี sleep) ----
# เช็คได้แค่ว่า "เจอ element แล้วโปรแกรมทำอะไรต่อ" ส่วน selector หา element บนหน้า Facebook จริงเจอไหม ยังต้อง live-test

class FakeEl:
    def __init__(self, text="", href=None):
        self.text, self.href, self.keys = text, href, []

    def get_attribute(self, name):
        return self.href

    def send_keys(self, *keys):
        self.keys.extend(keys)

    def click(self):
        pass


class FakeDriver:
    def __init__(self, cookies=()):
        self.current_url, self.visited, self.cdp, self.cookies, self.closed = "", [], [], list(cookies), False

    def get(self, url):
        self.visited.append(url)
        self.current_url = url

    def execute_cdp_cmd(self, cmd, params):
        self.cdp.append((cmd, params))

    def execute_script(self, *args):
        pass

    def get_cookies(self):
        return self.cookies

    def quit(self):
        self.closed = True


class FakeList:
    def __init__(self):
        self.items = []

    def delete(self, *args):
        self.items = []

    def insert(self, where, label):
        self.items.append(label)

    def curselection(self):
        return (0,)


class SyncThread:
    """แทน threading.Thread ให้ start() รันจบตรงนั้นเลย เทสจะได้ไม่ต้องรอ"""
    def __init__(self, target, args=(), daemon=None):
        self.target, self.args = target, args

    def start(self):
        self.target(*self.args)


FOLDERS = {"โช๊คหลัง PCX": {
    "main": {"images": [], "videos": [], "text": "ราคา 500\n\nส่งฟรี"},
    "review": {"images": ["r1.jpg", "r2.jpg"], "videos": [], "text": ""},
    "extra": None,
}}
THREAD = "https://www.facebook.com/marketplace/t/%s/"


def reply_app():
    import types
    renew_product.time.sleep = lambda s: None
    renew_product.Keys = types.SimpleNamespace(RETURN="<ENTER>", CONTROL="", DELETE="")
    a = App.__new__(App)
    a.reply_state = {"ID7": {}}
    a.stage_enabled = dict(App.DEFAULT_STAGE_ENABLED)
    a.reply_settings_file = os.path.join(tempfile.mkdtemp(), "reply_settings.json")
    a.reply_root_folder = None
    a.auto_reply_active = True
    a.driver_locks = {}
    a.notes, a.statuses, a.found = [], [], {}
    a.notify_new_chat = lambda profile, product, status, listing_name="", message="": a.notes.append((status, message))
    a.update_status = lambda text, color: a.statuses.append(text)
    a.wait_for_page_load = lambda d: None
    a.random_sleep = lambda *x: None
    a.root = types.SimpleNamespace(after=lambda ms, fn=None: None)
    a.find_all = lambda d, key, context=None: a.found.get(key, [])
    a.find_first = lambda d, key, context=None, wait=0: (a.found.get(key) or [None])[0]
    return a


def test_never_says_replied_when_nothing_was_sent():
    a, drv = reply_app(), FakeDriver()
    a.found = {"incoming_bubble": [FakeEl()], "listing_title": [FakeEl("โช๊คหลัง PCX แต่งศูนย์")]}

    # หาช่องพิมพ์ไม่เจอ = ลูกค้าไม่ได้อะไรเลย ต้องแจ้งว่าส่งไม่สำเร็จ ไม่ใช่ "ตอบอัตโนมัติให้แล้ว"
    a.handle_one_conversation("ID7", drv, THREAD % 111, "111", FOLDERS, "k", "จ่ายปลายทางได้มั้ย")
    assert a.reply_state["ID7"]["111"]["status"] == "failed"
    assert a.notes == [("send_failed", "จ่ายปลายทางได้มั้ย")]

    # ส่งออก = จดว่าตอบแล้ว แจ้งพร้อมข้อความที่ลูกค้าพิมพ์ และพิมพ์ครบ 2 ย่อหน้า กด Enter 2 ที
    box = FakeEl()
    a.found["message_box"] = [box]
    a.handle_one_conversation("ID7", drv, THREAD % 222, "222", FOLDERS, "k", "สนใจครับ")
    info = a.reply_state["ID7"]["222"]
    assert (info["status"], info["stage"], info["row_key"], info["just_sent"]) == ("replied", 1, None, True)
    assert a.notes[-1] == ("replied", "สนใจครับ")
    assert "".join(box.keys) == "ราคา 500<ENTER>ส่งฟรี<ENTER>"

    # ลูกค้าพิมพ์มาอีกในแชทที่ส่งไม่ออก ยังต้องแจ้ง (เดิมเงียบ)
    failed = a.reply_state["ID7"]["111"]
    assert a.handle_followup("ID7", drv, "111", FOLDERS, failed, "k1", "") is False and len(a.notes) == 2
    a.handle_followup("ID7", drv, "111", FOLDERS, failed, "k2", "ยังอยู่ไหม")
    assert a.notes[-1] == ("send_failed", "ยังอยู่ไหม")


def test_folder_with_only_pictures_is_actually_sent():
    a, drv = reply_app(), FakeDriver()
    picker, box = FakeEl(), FakeEl()
    a.found = {"file_input": [picker], "message_box": [box]}

    # แนบรูปอย่างเดียวยังไม่ถูกส่ง ต้องมี Enter ตาม (โฟลเดอร์รีวิว/รูปเพิ่มเติมไม่มี .txt มากด Enter ให้)
    assert a.send_folder_content(drv, FOLDERS["โช๊คหลัง PCX"]["review"]) is True
    assert picker.keys == ["r1.jpg\nr2.jpg"] and box.keys == ["<ENTER>"]

    a.found = {"file_input": [picker]}
    assert a.send_folder_content(drv, FOLDERS["โช๊คหลัง PCX"]["review"]) is False


def test_followup_failure_does_not_advance_or_claim_sent():
    a, drv = reply_app(), FakeDriver()
    a.stage_enabled["review"] = True
    info = {"product": "โช๊คหลัง PCX", "status": "replied", "stage": 1, "row_key": "k0"}

    # ลูกค้าทักกลับ แต่ส่งรีวิวไม่ออก: stage ต้องอยู่ที่เดิม และแจ้งว่าไม่สำเร็จ
    assert a.handle_followup("ID7", drv, "111", FOLDERS, info, "k1", "มีรีวิวไหม") is True
    assert info["stage"] == 1 and a.notes == [("send_failed", "มีรีวิวไหม")]

    a.found = {"file_input": [FakeEl()], "message_box": [FakeEl()]}
    info["row_key"] = "k0"
    a.handle_followup("ID7", drv, "111", FOLDERS, info, "k1", "มีรีวิวไหม")
    assert info["stage"] == 2 and info["just_sent"] is True and a.notes[-1][0] == "followup"


def test_ongoing_chat_is_remembered_and_reported_once_new():
    a, drv = reply_app(), FakeDriver()
    a.found = {"incoming_bubble": [FakeEl(), FakeEl()], "listing_title": [FakeEl("โช๊คหลัง PCX")]}

    # แชทที่ค้างอยู่ก่อนเปิดโปรแกรม: จดไว้เฉยๆ ไม่ตอบ ไม่แจ้ง (ไม่งั้นเปิดโปรแกรมทีเด้งเป็นสิบ)
    a.handle_one_conversation("ID7", drv, THREAD % 111, "111", FOLDERS, "k0", "ของยังอยู่ไหม", is_new=False)
    info = a.reply_state["ID7"]["111"]
    assert info["status"] == "old" and a.notes == []

    # จดแล้วรอบหน้าไม่เปิดแชทนี้ซ้ำ และพอลูกค้าพิมพ์มาใหม่ต้องแจ้ง
    assert a.handle_followup("ID7", drv, "111", FOLDERS, info, "k0", "ของยังอยู่ไหม") is False
    assert a.notes == [] and drv.visited == [THREAD % 111]
    a.handle_followup("ID7", drv, "111", FOLDERS, info, "k1", "ลดได้ไหม")
    assert a.notes == [("old_chat", "ลดได้ไหม")]

    # แชทที่โผล่มาระหว่างโปรแกรมเปิดอยู่ แต่ลูกค้าพิมพ์รัว 2 ข้อความก่อนรอบสแกน: ไม่ตอบทับ แต่ต้องแจ้ง
    a.handle_one_conversation("ID7", drv, THREAD % 222, "222", FOLDERS, "k", "ลดได้ไหม", is_new=True)
    assert a.notes[-1] == ("old_chat", "ลดได้ไหม")

    # แชทเก่าไม่ต้องโชว์ในรายการ "แชทที่ตอบไปแล้ว"
    a.reply_listbox = FakeList()
    a.update_reply_list()
    assert a.reply_listbox.items == [] and a._reply_list_index == []


def test_quick_reply_after_our_message_is_not_swallowed():
    a, drv = reply_app(), FakeDriver()

    # เราเพิ่งส่งไป ลูกค้าตอบกลับก่อนรอบสแกนถัดไป: ต้องแจ้ง ไม่ใช่เก็บเป็นฐานเทียบเงียบๆ
    info = {"product": "โช๊คหลัง PCX", "status": "replied", "stage": 1, "row_key": None, "just_sent": True}
    assert a.handle_followup("ID7", drv, "111", FOLDERS, info, "k1", "จ่ายปลายทางได้มั้ย") is False
    assert a.notes == [("quick_reply", "จ่ายปลายทางได้มั้ย")]
    assert info["row_key"] == "k1" and "just_sent" not in info and drv.visited == []

    # ข้อความล่าสุดเป็นของเราเอง (preview ว่าง) = ยังไม่มีใครตอบ ไม่แจ้ง
    info = {"product": "โช๊คหลัง PCX", "status": "replied", "stage": 1, "row_key": None, "just_sent": True}
    a.handle_followup("ID7", drv, "111", FOLDERS, info, "k1", "")
    assert len(a.notes) == 1
    assert app.preview_message("สมชาย\nคุณส่งรูปภาพ 3 รูป · 1 นาที") == ""

    # ประวัติเก่าจากโปรแกรมรุ่นก่อน (ไม่มี just_sent): รอบแรกเก็บฐานอย่างเดียว ห้ามแจ้ง ห้ามส่ง
    old = {"product": "โช๊คหลัง PCX", "status": "replied", "stage": 1}
    a.handle_followup("ID7", drv, "111", FOLDERS, old, "k1", "ข้อความเมื่ออาทิตย์ก่อน")
    assert len(a.notes) == 1 and old["row_key"] == "k1"


def test_scan_notices_logout_and_which_chats_are_new():
    a, drv = reply_app(), FakeDriver()
    a.found = {"conversation_row": [
        FakeEl("สมชาย\nสนใจครับ · 2 นาที", THREAD % 999),
        FakeEl("สมชาย\nสนใจครับ · 2 นาที", THREAD % 999),
        FakeEl("ลิงก์อื่น", "https://www.facebook.com/marketplace/item/5/")]}
    seen = []
    a.handle_one_conversation = lambda p, d, href, tid, f, key, preview, is_new: seen.append((tid, preview, is_new))

    assert a.scan_inbox_once("ID7", drv, FOLDERS, first_pass=True) is True
    assert a.scan_inbox_once("ID7", drv, FOLDERS, first_pass=False) is True
    assert seen == [("999", "สนใจครับ", False), ("999", "สนใจครับ", True)]

    # หลุด Login: inbox เด้งไปหน้า login แถวแชทเป็น 0 ต้องบอกว่าไม่ได้อ่าน ไม่ใช่ "ไม่มีลูกค้าทัก"
    drv.get = lambda url: setattr(drv, "current_url", "https://www.facebook.com/login/?next=inbox")
    assert a.scan_inbox_once("ID7", drv, FOLDERS, first_pass=False) is False


def test_worker_reports_a_profile_that_stopped_watching():
    a, drv = reply_app(), FakeDriver()
    problems, calls = [], []
    a.notify_problem = lambda profile, problem: problems.append(problem)

    def scan(profile, driver, folders, first_pass):
        calls.append(first_pass)
        if len(calls) == 3:
            a.auto_reply_active = False
        return False  # หลุด Login ทุกรอบ
    a.scan_inbox_once = scan

    a.auto_reply_worker("ID7", drv, FOLDERS)
    # แจ้งครั้งเดียวตอนเพิ่งหลุด ไม่ยิงซ้ำทุกรอบ และรอบแรกยังไม่จบ (first_pass ค้างไว้จนกว่าจะอ่านได้จริง)
    assert len(problems) == 1 and "Login" in problems[0] and calls == [True, True, True] and drv.closed

    class Dead(FakeDriver):
        @property
        def current_url(self):
            raise RuntimeError("chrome gone")

        @current_url.setter
        def current_url(self, value):
            pass

    a.auto_reply_active, problems[:] = True, []
    a.auto_reply_worker("ID7", Dead(), FOLDERS)
    assert len(problems) == 1 and "Chrome" in problems[0]


def test_manual_send_waits_its_turn_and_reports_failure():
    a, drv = reply_app(), FakeDriver()
    real_thread = renew_product.threading.Thread
    renew_product.threading.Thread = SyncThread
    try:
        info = {"product": "โช๊คหลัง PCX", "status": "replied", "stage": 1, "row_key": "k0"}
        a.reply_state["ID7"]["111"] = info
        a.reply_listbox, a._reply_list_index = FakeList(), [("ID7", "111")]
        a.reply_drivers = {"ID7": drv}
        a.scan_product_folders = lambda root: FOLDERS

        a.manual_send_category("review")  # ไม่มีช่องแนบไฟล์ = ส่งไม่ออก
        assert info["stage"] == 1 and "ไม่สำเร็จ" in a.statuses[-1]

        a.found = {"file_input": [FakeEl()], "message_box": [FakeEl()]}
        a.manual_send_category("review")
        assert info["stage"] == 2 and info["row_key"] is None and drv.visited[-1] == THREAD % 111
        assert not a.driver_locks["ID7"].locked()
    finally:
        renew_product.threading.Thread = real_thread


def test_logged_out_cookies_never_overwrite_the_ini():
    path = os.path.join(tempfile.mkdtemp(), "ID7.ini")
    with open(path, "w", encoding="utf-8") as f:
        f.write("[FBAccount]\nUserID = a\nCookies = OLDGOOD\n")

    try:
        app._save_cookies_to_ini(FakeDriver([{"name": "datr", "value": "x"}]), path, force=True)
        raise AssertionError("ต้องไม่ยอมบันทึก Cookie ตอนยังไม่ได้ Login")
    except Exception as e:
        assert "Login" in str(e)
    assert "OLDGOOD" in open(path, encoding="utf-8").read()

    app._save_cookies_to_ini(FakeDriver([{"name": "c_user", "value": "1"}, {"name": "xs", "value": "2"}]), path, force=True)
    saved = open(path, encoding="utf-8").read()
    assert "OLDGOOD" not in saved and "UserID = a" in saved and app._read_cookies_from_ini(path)


def test_typing_emoji_does_not_break_the_message():
    reply_app()
    el, drv = FakeEl(), FakeDriver()
    app.human_like_type(el, "ดี🔥", drv)
    assert el.keys == ["ด", "ี"] and drv.cdp == [("Input.insertText", {"text": "🔥"})]


def test_reply_settings_file_is_replaced_whole():
    import json
    a = reply_app()
    a.reply_state = {"ID7": {"111": {"product": "โช๊คหลัง PCX", "status": "old"}}}
    a.save_reply_settings()
    folder = os.path.dirname(a.reply_settings_file)
    assert os.listdir(folder) == ["reply_settings.json"]
    assert json.load(open(a.reply_settings_file, encoding="utf-8"))["state"]["ID7"]["111"]["status"] == "old"


def test_new_notify_statuses_have_their_own_wording():
    texts = {s: app.build_notify_text("ID7", "โช๊คหลัง PCX", s) for s in ("send_failed", "quick_reply", "old_chat")}
    assert "ไม่สำเร็จ" in texts["send_failed"] and "ตอบกลับมา" in texts["quick_reply"] and "คุยกันอยู่แล้ว" in texts["old_chat"]
    assert all("จับคู่สินค้าไม่ได้" not in t and "เฟส: ID7" in t for t in texts.values())


if __name__ == "__main__":
    test_strip_leading_number()
    test_match_exact_one()
    test_match_ambiguous_returns_none()
    test_match_no_match_returns_none()
    test_cookie_samesite_none_forces_secure()
    test_cookie_keeps_secure_and_httponly()
    test_login_pending_url()
    test_notify_text_names_the_profile()
    test_send_telegram_without_config_is_quiet()
    test_people_who_message_the_bot_get_added()
    test_bot_poll_is_throttled()
    test_exe_runs_newer_source_from_github()
    test_cookie_skips_nameless()
    test_inbox_row_key_ignores_relative_time()
    test_preview_message_reads_what_customer_typed()
    test_preview_message_skips_our_own_message()
    test_notify_text_includes_customer_message()
    test_followup_backfill_sends_nothing()
    test_followup_no_change_sends_nothing()
    test_followup_advances_stages_then_stops()
    test_followup_skips_missing_folder()
    test_stage_toggle_skips_disabled_folder()
    test_default_only_answers_the_first_message()
    test_renew_due_respects_toggle_and_interval()
    test_notify_separates_disabled_from_finished()
    test_stage_labels_cover_every_stage()
    test_followup_skips_unmatched_thread()
    test_split_text_to_messages()
    test_scan_product_folders()
    test_never_says_replied_when_nothing_was_sent()
    test_folder_with_only_pictures_is_actually_sent()
    test_followup_failure_does_not_advance_or_claim_sent()
    test_ongoing_chat_is_remembered_and_reported_once_new()
    test_quick_reply_after_our_message_is_not_swallowed()
    test_scan_notices_logout_and_which_chats_are_new()
    test_worker_reports_a_profile_that_stopped_watching()
    test_manual_send_waits_its_turn_and_reports_failure()
    test_logged_out_cookies_never_overwrite_the_ini()
    test_typing_emoji_does_not_break_the_message()
    test_reply_settings_file_is_replaced_whole()
    test_new_notify_statuses_have_their_own_wording()
    print("OK")
