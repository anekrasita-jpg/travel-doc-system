# Travel & Expense Document System (ระบบเอกสารราชการ)

ระบบเว็บแอปพลิเคชัน Flask สำหรับจัดการเอกสารอนุมัติเดินทาง เบิกจ่ายค่าเดินทาง และเบิกจ่ายค่ารักษาพยาบาล รันภายในเครื่อง Ubuntu Server ในระบบเครือข่ายส่วนตัวผ่าน Tailscale VPN

---

## ฟีเจอร์เด่น
- **โมดูล Blueprint แยกอิสระ**: การเพิ่มหรือแก้ไขโมดูลในอนาคตจะไม่กระทบหน้าหลัก
- **รูปแบบวันที่ พ.ศ. (Thai Buddhist Calendar)**: บันทึกข้อมูลแบบ ค.ศ. (ISO format) ในฐานข้อมูลปกติ แต่แสดงผลหน้าเว็บและพ่นลงเอกสาร Word (.docx) เป็นรูปแบบ พ.ศ. เสมอ (ฟังก์ชัน `to_thai_date()`)
- **การประมวลผล 3 ช่องทางพร้อมกันเมื่อส่งฟอร์ม**:
  1. บันทึกประวัติลง SQLite Database
  2. แปลงข้อมูลและกรอกใส่ไฟล์ต้นแบบเอกสาร Word (.docx) อัตโนมัติ (ใช้ `python-docx`)
  3. เขียนสรุปรายการแบบตาราง Markdown (.md) แยกประเดือนเก็บในโฟลเดอร์ Log ของ `knowledge-base/`
- **ระบบ Admin**: จัดการสถานะคำร้อง (อนุมัติ/ปฏิเสธ), สั่งดาวน์โหลดไฟล์เอกสาร Word ที่ถูกสร้างขึ้นมา, และระบบ CRUD ข้อมูลพนักงาน (Staff)

---

## ขั้นตอนการติดตั้งและทดสอบแบบ Local (Development)

1. **ดาวน์โหลดและเตรียมสภาพแวดล้อม:**
   ```bash
   # สร้าง virtual environment
   python -m venv venv
   
   # เปิดใช้งาน virtual environment (Windows Powershell)
   .\venv\Scripts\Activate.ps1
   # (หรือ Linux/macOS)
   source venv/bin/activate
   ```

2. **ติดตั้ง dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **เตรียมค่าคอนฟิก (.env):**
   ทำสำเนาจากไฟล์ต้นแบบและปรับแต่งคีย์ตามสมควร:
   ```bash
   cp .env.example .env
   ```
   *หมายเหตุ: ในไฟล์ `.env.example` มีค่าแฮชของรหัสผ่านผู้ดูแลระบบตั้งต้นไว้ โดยมี **Username: `admin`** และ **Password: `adminpassword`***

4. **รันเซิร์ฟเวอร์ทดสอบ:**
   ```bash
   python app.py
   ```
   เข้าชมผ่านเบราว์เซอร์ที่: [http://localhost:5000](http://localhost:5000)

---

## คู่มือการ Deploy บน Ubuntu Server (Production)

เนื่องจากระบบนี้จะรันบนเครื่องเซิร์ฟเวอร์ภายในบ้านและเข้าถึงผ่าน Tailscale VPN เท่านั้น สามารถรันผ่าน Systemd Service ร่วมกับ Gunicorn เพื่อความเสถียรได้ตามขั้นตอนนี้:

### 1. ติดตั้ง Python และ Software ที่จำเป็นบน Ubuntu
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv git -y
```

### 2. นำโค้ดขึ้นเซิร์ฟเวอร์และติดตั้ง Dependencies
ย้ายโฟลเดอร์โปรเจกต์ไปไว้ที่ `/opt/travel-doc-system` หรือพาธที่ต้องการ:
```bash
cd /opt
# สมมติโคลนมาหรือย้ายโฟลเดอร์มาแล้ว
cd travel-doc-system

# สร้าง virtual environment และติดตั้งแพ็กเกจ
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn  # ติดตั้ง gunicorn สำหรับรันระดับ production
```

### 3. ตั้งค่าสภาพแวดล้อม (.env)
สร้างไฟล์ `.env` และกำหนด Secret Key รวมถึงรหัสผ่านแอดมิน:
```bash
nano .env
```
หากต้องการสร้างรหัสผ่านแอดมินใหม่ที่แฮชด้วยความปลอดภัยสูง ให้เปิด Python Console แล้วคำนวณแฮช:
```python
from werkzeug.security import generate_password_hash
print(generate_password_hash("รหัสผ่านใหม่ของคุณที่นี่"))
# คัดลอกผลลัพธ์ที่ได้ไปกำหนดไว้ในบรรทัด ADMIN_PASSWORD_HASH ใน .env
```

### 4. สร้าง Systemd Service Unit File
สร้างไฟล์บริการเพื่อให้ Ubuntu จัดการระบบออโต้เมื่อเครื่องบู้ทเสร็จ:
```bash
sudo nano /etc/systemd/system/travel-doc.service
```
วางเนื้อหาต่อไปนี้ลงไป (ตรวจสอบพาธและ User ให้ตรงกับเครื่องเซิร์ฟเวอร์):
```ini
[Unit]
Description=Travel and Expense Document System Web Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/opt/travel-doc-system
ExecStart=/opt/travel-doc-system/venv/bin/gunicorn -w 4 -b 0.0.0.0:5000 "app:create_app()"
Restart=always

[Install]
WantedBy=multi-user.target
```

### 5. สั่งเริ่มทำงานและเปิดใช้งาน Service
```bash
# โหลดคอนฟิกของ systemd ใหม่
sudo systemctl daemon-reload

# สั่งให้ทำงานตอนเปิดเครื่องอัตโนมัติ
sudo systemctl enable travel-doc

# สั่งเริ่มทำงานเดี๋ยวนี้
sudo systemctl start travel-doc

# ตรวจสอบสถานะการทำงาน
sudo systemctl status travel-doc
```

---

## โครงสร้างและการทำ Template Word (.docx)

ในโฟลเดอร์ `document_templates/` จะจัดเก็บไฟล์ต้นแบบ Word สำหรับนำมาแทนที่ค่า ฟังก์ชันในตัวโปรแกรมจะทำการตรวจจับตัวแปรที่มีเครื่องหมายวงเล็บปีกกาคู่ `{{ ตัวแปร }}` และเขียนข้อมูลใหม่ทับไปโดยรักษาสไตล์เดิมไว้

### คีย์ตัวแปรที่สามารถระบุในไฟล์ `.docx` ต้นแบบ:

| โมดูล | ตัวแปรที่มีให้ใช้งาน |
|---|---|
| **ทุกโมดูล (ร่วมกัน)** | `{{full_name}}` (ชื่อเต็มพนักงาน), `{{position}}` (ตำแหน่ง), `{{department}}` (แผนก) |
| **travel_approval_template.docx** | `{{document_number}}`, `{{travel_date}}` (วันที่ พ.ศ.), `{{destination}}`, `{{reason}}` |
| **travel_expense_template.docx** | `{{approval_id}}` (รหัสอ้างอิงและสถานที่ปลายทาง), `{{amount}}` (ยอดเงินเบิกจ่าย), `{{expense_date}}` |
| **medical_expense_template.docx** | `{{amount}}` (ยอดเงิน), `{{treatment_date}}`, `{{hospital_name}}` |

*หากไม่มีไฟล์ `.docx` เหล่านี้ในโฟลเดอร์ `document_templates/` เมื่อกดบันทึกแบบฟอร์ม ตัวระบบจะสุ่มสร้างไฟล์เอกสารที่มีหัวตารางและใส่ตัวแปรตัวอย่างข้างต้นให้โดยอัตโนมัติเพื่อให้โปรแกรมไม่ขัดข้องในการทดสอบระดับเริ่มต้น*
