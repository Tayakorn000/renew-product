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

## Login

เพิ่ม Profile ด้วยไฟล์ `.ini` (section `[FBAccount]`, มี `UserID`/`Password` หรือ `Cookies` ก็ได้) — ถ้าไฟล์มี Cookie อยู่แล้วโปรแกรมจะ login อัตโนมัติ ไม่ต้องกด Login ด้วยมือ
