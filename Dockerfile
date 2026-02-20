# ใช้ Python ตัวเล็กเพื่อให้ Image ไม่หนักเครื่อง
FROM python:3.9-slim

# ตั้งเวลาใน Container ให้เป็นเวลาไทย
ENV TZ=Asia/Bangkok

# ติดตั้งเครื่องมือจัดการ Postgres และ GCC สำหรับคอมไพล์โค้ด
RUN apt-get update && apt-get install -y tzdata libpq-dev gcc && apt-get clean

# กำหนดโฟลเดอร์หลักที่ใช้รันงาน
WORKDIR /app

# ก๊อปปี้ไฟล์ Library มาลงก่อนเพื่อใช้ประโยชน์จาก Build Cache
COPY requirements.txt .

# ติดตั้ง Library ทั้งหมดโดยไม่เก็บไฟล์ขยะไว้ในเครื่อง
RUN pip install --no-cache-dir -r requirements.txt

# ก๊อปปี้ซอร์สโค้ดทั้งหมดเข้าเครื่องจำลอง
COPY . .

# เปิด Port 5000 สำหรับการเชื่อมต่อ
EXPOSE 5000

# รันเว็บด้วย Gunicorn แบบ 2 Workers เพื่อความเสถียร
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]