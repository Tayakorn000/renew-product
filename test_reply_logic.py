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
    test_split_text_to_messages()
    test_scan_product_folders()
    print("OK")
