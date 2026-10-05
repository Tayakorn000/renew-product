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

ตั้งค่าครั้งเดียว:

1. ทัก [@BotFather](https://t.me/BotFather) ใน Telegram พิมพ์ `/newbot` ตั้งชื่อบอท จะได้ Token มา
2. ทักบอทตัวเองที่เพิ่งสร้าง พิมพ์อะไรก็ได้ 1 ข้อความ
3. เปิด `https://api.telegram.org/bot<TOKEN>/getUpdates` ในเบราว์เซอร์ หาเลข `"chat":{"id":...}` นั่นคือ Chat ID
4. เอา Token กับ Chat ID มากรอกในโปรแกรม ช่องอยู่ใต้หัวข้อตอบแชทลูกค้าอัตโนมัติ แล้วกดบันทึก + ทดสอบส่ง

อยากให้เข้ากลุ่มแทนแชทส่วนตัว ก็ดึงบอทเข้ากลุ่มแล้วใช้ Chat ID ของกลุ่ม (ขึ้นต้นด้วยเครื่องหมายลบ)

## Login

เพิ่ม Profile ด้วยไฟล์ `.ini` (section `[FBAccount]`, มี `UserID`/`Password` หรือ `Cookies` ก็ได้) — ถ้าไฟล์มี Cookie อยู่แล้วโปรแกรมจะ login อัตโนมัติ ไม่ต้องกด Login ด้วยมือ
