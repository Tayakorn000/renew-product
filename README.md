# Renew Product

โปรแกรมต่ออายุสินค้า Facebook Marketplace + ตอบแชทลูกค้าอัตโนมัติ (Tkinter + Selenium)

## Build .exe (Windows)

ต้องมี Python ก่อน แล้วรันตามนี้:

```
git clone https://github.com/Tayakorn000/renew-product.git
cd renew-product
pip install selenium undetected-chromedriver pyinstaller
pyinstaller --onefile --windowed --name "Renew Product" "Renew Product.py"
```

exe ออกที่ `dist\Renew Product.exe`

แก้โค้ดรอบหน้า ไม่ต้อง clone ใหม่ แค่:

```
git pull
pyinstaller --onefile --windowed --name "Renew Product" "Renew Product.py"
```

## แจ้งเตือน Telegram

เวลามีลูกค้าทักเข้ามา โปรแกรมยิงแจ้งเตือนเข้า Telegram ได้ บอกว่ามาจากเฟสไหน สินค้าอะไร ตอบไปหรือยัง

exe ที่ build จากเครื่องที่มีไฟล์ `telegram_default.py` จะมีบอทติดมาในตัว เปิดมาช่อง Token/Chat ID มีค่าอยู่แล้ว
ไฟล์นั้น gitignore ไว้ (repo นี้ public ห้ามมี token) ถ้า clone มา build เองจะไม่มี ต้องกรอกเอง:

```python
# telegram_default.py
TELEGRAM_TOKEN = "123456:AA..."
TELEGRAM_CHAT_ID = "7017153301"
```

ค่าที่กรอกในโปรแกรมชนะค่าที่ฝังมา เปลี่ยนเป็นบอทตัวเองได้ตลอด

ตั้งค่าครั้งเดียว:

1. ทัก [@BotFather](https://t.me/BotFather) ใน Telegram พิมพ์ `/newbot` ตั้งชื่อบอท จะได้ Token มา
2. ทักบอทตัวเองที่เพิ่งสร้าง พิมพ์อะไรก็ได้ 1 ข้อความ
3. เปิด `https://api.telegram.org/bot<TOKEN>/getUpdates` ในเบราว์เซอร์ หาเลข `"chat":{"id":...}` นั่นคือ Chat ID
4. เอา Token กับ Chat ID มากรอกในโปรแกรม ช่องอยู่ใต้หัวข้อตอบแชทลูกค้าอัตโนมัติ แล้วกดบันทึก + ทดสอบส่ง

อยากให้เข้ากลุ่มแทนแชทส่วนตัว ก็ดึงบอทเข้ากลุ่มแล้วใช้ Chat ID ของกลุ่ม (ขึ้นต้นด้วยเครื่องหมายลบ)

## ตอบแชทอัตโนมัติ (รวมลูกค้าที่ตอบไปแล้ว)

ลูกค้าทักมาครั้งแรก โปรแกรมจับคู่ชื่อประกาศกับชื่อโฟลเดอร์สินค้า แล้วส่งข้อมูลหลักให้

พอลูกค้าคนนั้นทักกลับมาอีก มันส่งต่อให้เองตามลำดับ: โฟลเดอร์รีวิวลูกค้า แล้วรอบถัดไปเป็นข้อมูลเพิ่มเติม
ส่งครบแล้วลูกค้าทักมาอีก มันไม่ส่งซ้ำ แค่แจ้งเตือน Telegram ว่าต้องเข้าไปตอบเอง

โฟลเดอร์ไหนไม่มีไฟล์ มันข้ามไปอันถัดไปเลย ปุ่มส่งด้วยมือยังใช้ได้เหมือนเดิม กดแล้วระบบออโต้จะไม่ส่งโฟลเดอร์นั้นซ้ำ

หมายเหตุ: มันดูแค่ว่ามีข้อความใหม่เข้ามา ไม่ได้อ่านว่าลูกค้าพูดอะไร ลูกค้าตอบ "ไม่สนใจครับ" ก็ได้รีวิวไปด้วย
และรอบสแกนแรกหลังอัปเดตโปรแกรม มันจะเก็บข้อมูลเป็นฐานเทียบก่อน 1 รอบ ยังไม่ส่งอะไรให้ประวัติเก่า

## Login

เพิ่ม Profile ด้วยไฟล์ `.ini` (section `[FBAccount]`, มี `UserID`/`Password` หรือ `Cookies` ก็ได้) — ถ้าไฟล์มี Cookie อยู่แล้วโปรแกรมจะ login อัตโนมัติ ไม่ต้องกด Login ด้วยมือ
