# 🤖 cPanel & Server Monitor Telegram Bot

Bot Telegram otomatis dan mandiri untuk memantau status kesehatan server cPanel dan website Anda secara berkala (24/7). Bot ini akan langsung mengirimkan peringatan darurat ke Telegram ketika server terdeteksi **DOWN** agar Anda bisa sigap menghubungi admin pemilik server untuk menyalakan kembali layanannya.

---

## ✨ Fitur Utama

- 🚨 **Notifikasi DOWN Instan**: Memberikan notifikasi darurat saat website atau port cPanel tidak dapat diakses atau mengembalikan error server (HTTP 500, 502, 503, 504, timeout, atau koneksi terputus).
- 🛡 **Anti-Alarm Palsu (Failure Threshold)**: Pengecekan cerdas dengan ambang batas (default 3 kali gagal berturut-turut) untuk menghindari kepanikan akibat fluktuasi koneksi internet lokal sejenak.
- 🔄 **Notifikasi Pemulihan (Recovery)**: Memberikan kabar gembira saat server sudah kembali normal (UP) lengkap dengan informasi total durasi *downtime*.
- ⚙️ **Target & Interval Dinamis**: Anda dapat menambah/menghapus URL target serta mengubah frekuensi pengecekan kapan saja, baik melalui file [`.env`](file:///home/pc-it/Projects/cpanel-monitor-bot/.env) maupun **langsung dari chat Telegram** (`/addtarget`, `/setinterval`).
- 💾 **Persistensi Otomatis**: Setiap perubahan target atau interval yang diatur lewat Telegram akan otomatis tersimpan permanen di `data/config.json`.
- 🕹 **Perintah Interaktif**: Dilengkapi perintah Telegram `/status`, `/check` (cek instan), `/mute` (jeda saat maintenance), dan `/targets`.
- 🕒 **Background Service 24/7**: Terintegrasi penuh dengan `systemd --user` sehingga bot otomatis berjalan di latar belakang dan langsung aktif saat server/laptop dinyalakan kembali.

---

## 📁 Struktur Proyek

```
cpanel-monitor-bot/
├── .env                      # Konfigurasi aktif (token Telegram & chat ID)
├── .env.example              # Template konfigurasi
├── requirements.txt          # Dependensi Python
├── README.md                 # Dokumentasi panduan
├── data/
│   └── config.json           # Runtime config persisten (target & interval dinamis)
├── src/
│   ├── config.py             # Pengelola konfigurasi (.env + persistensi JSON)
│   ├── checker.py            # Engine HTTP & TCP health checker
│   ├── state.py              # State machine (UP/DOWN/RECOVERED & anti-spam)
│   ├── notifier.py           # Format pesan Telegram HTML rapi & jelas
│   └── bot.py                # Main bot runner: command handlers & async monitor loop
├── tests/                    # Unit & integration tests
│   ├── test_config.py
│   ├── test_checker.py
│   └── test_state.py
├── service/
│   └── cpanel-monitor.service # Unit file systemd
└── scripts/
    ├── setup.sh              # Skrip setup otomatis venv & requirements
    ├── start.sh              # Skrip menjalankan bot langsung di terminal
    └── manage_service.sh     # Skrip manajemen systemd (install, status, logs, stop)
```

---

## 🚀 Panduan Memulai Cepat (Quick Start)

### 1. Buat Bot Telegram & Dapatkan Token
1. Buka aplikasi Telegram dan cari **[@BotFather](https://t.me/BotFather)**.
2. Kirim pesan `/newbot` dan ikuti petunjuk (beri nama bot dan username berakhiran `_bot`).
3. Salin token API yang diberikan (misal: `7123456789:AAHk...`).

### 2. Dapatkan Chat ID Anda
1. Buka **[@userinfobot](https://t.me/userinfobot)** di Telegram.
2. Salin angka **Id** Anda (misal: `123456789`).
   *(Atau Anda bisa langsung menjalankan bot dan ketik `/start` ke bot Anda, bot akan otomatis menampilkan Chat ID Anda).*

### 3. Masukkan ke File `.env`
Buka file [`.env`](file:///home/pc-it/Projects/cpanel-monitor-bot/.env) di folder proyek:
```ini
# Masukkan token dari @BotFather:
TELEGRAM_BOT_TOKEN=7123456789:AAHk...

# Masukkan Chat ID akun/grup Anda:
TELEGRAM_CHAT_ID=123456789

# Target pemantauan awal:
TARGET_URLS=https://prima.rsmra.id,https://prima.rsmra.id:2083

# Interval cek dalam detik (default 60 detik):
CHECK_INTERVAL_SECONDS=60

# Ambang batas kegagalan berturut-turut sebelum alarm:
FAILURE_THRESHOLD=3

# Pengingat saat masih down (tiap 30 menit, 0 = nonaktif):
REMINDER_INTERVAL_MINUTES=30
```

---

## 🧪 Uji Coba Pengecekan

### A. Uji Cek Status Server Langsung di Terminal:
```bash
./scripts/start.sh --check-once
```
*Output akan menampilkan status koneksi dan latency setiap URL secara langsung.*

### B. Uji Kirim Pesan Tes ke Telegram Anda:
```bash
./scripts/start.sh --test-message
```
*Bot akan mengirimkan pesan tes ke akun Telegram Anda untuk memastikan token dan chat ID sudah benar.*

### C. Jalankan Bot di Terminal (Foreground):
```bash
./scripts/start.sh
```
*Tekan `Ctrl + C` untuk menghentikan bot.*

---

## 📱 Daftar Perintah Telegram (Interactive Commands)

Anda dapat mengontrol bot langsung dari Telegram:

| Perintah | Fungsi | Contoh Penggunaan |
| :--- | :--- | :--- |
| `/status` | Melihat status kesehatan real-time seluruh target yang dipantau | `/status` |
| `/check` | Memaksa pengecekan instan saat itu juga | `/check` |
| `/targets` | Menampilkan daftar URL yang dipantau & interval aktif | `/targets` |
| `/addtarget <url>` | Menambahkan URL target baru yang ingin dipantau | `/addtarget https://domainanda.com:2083` |
| `/removetarget <url>` | Menghapus URL dari daftar pemantauan | `/removetarget https://domainanda.com` |
| `/setinterval <detik>` | Mengubah jeda pengecekan (minimal 5 detik) | `/setinterval 30` (cek tiap 30 detik) |
| `/setthreshold <kali>` | Mengubah batas toleransi kegagalan berturut-turut | `/setthreshold 3` |
| `/mute <menit>` | Mematikan notifikasi alert sementara (misal saat maintenance) | `/mute 60` (jeda selama 1 jam) |
| `/unmute` | Mengaktifkan kembali alert notifikasi | `/unmute` |
| `/id` | Menampilkan Telegram Chat ID Anda | `/id` |
| `/help` | Menampilkan menu bantuan perintah | `/help` |

> [!TIP]
> **Keamanan**: Perintah konfigurasi seperti `/addtarget`, `/removetarget`, `/setinterval`, `/setthreshold`, dan `/mute` hanya dapat dijalankan oleh Chat ID yang terdaftar sebagai admin di konfigurasi.

---

## ⚙️ Menjalankan sebagai Background Service 24/7 (Systemd)

Agar bot terus berjalan di latar belakang dan otomatis aktif kembali saat komputer atau server dinyalakan ulang, pasang sebagai `systemd user service`:

### 1. Pasang & Aktifkan Service:
```bash
./scripts/manage_service.sh install
```

### 2. Cek Status Service:
```bash
./scripts/manage_service.sh status
```

### 3. Lihat Log Real-Time:
```bash
./scripts/manage_service.sh logs
```

### 4. Perintah Tambahan:
- Restart service: `./scripts/manage_service.sh restart`
- Hentikan service: `./scripts/manage_service.sh stop`
- Hapus service: `./scripts/manage_service.sh uninstall`

---

## 🧪 Menjalankan Automated Tests

Seluruh modul dilengkapi dengan automated unit & integration tests:
```bash
./venv/bin/python -m unittest discover tests
```
Pengujian mencakup:
1. Validasi parsing dan persistensi konfigurasi dinamis.
2. Pengujian respon HTTP mock server (200 OK, 502 Bad Gateway, Connection Refused, Timeout).
3. Transisi status state machine (UP -> Pending Failures -> DOWN Alert -> Reminders -> Recovery).
