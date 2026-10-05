"""self-check สำหรับ logic ที่ไม่ต้องพึ่ง Selenium (จับคู่โฟลเดอร์/ตัดเลขนำหน้า/แยกข้อความ)
รันบนเครื่องที่ไม่มี selenium ก็ได้ (import guard ใน Renew Product.py กันไว้แล้ว)
ส่วน DOM/Selenium (get_selectors, find_first, upload_files_to_chat, ...) ยังไม่ได้ทดสอบ
ต้อง live-test บนเครื่อง Windows ของลูกค้าที่มี Chrome + login จริง
"""
import importlib.util
import os

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
    test_cookie_skips_nameless()
    test_split_text_to_messages()
    test_scan_product_folders()
    print("OK")
