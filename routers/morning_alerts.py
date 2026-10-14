from datetime import datetime
from fastapi import APIRouter, Request
import pytz
import uuid
import random

router = APIRouter(prefix="/api", tags=["Morning Alert UTS AI"])
last_morning_alert_date = None

HARI_INDONESIA = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"
}

# Motivasi & reminder santai pagi hari sebelum ujian
MORNING_MOTIVATION = [
    "✨ *Pesan Pagi:* Jangan lupa sarapan secukupnya, berdoa, dan cek kembali alat tulismu ya!",
    "✨ *Pesan Pagi:* Awali ujian hari ini dengan tenang dan basmalah. Percaya pada persiapanmu!",
    "✨ *Pesan Pagi:* Kerjakan soal yang paling mudah dulu dan jangan terburu-buru!",
    "✨ *Pesan Pagi:* Tetap rileks dan optimis. Kamu pasti bisa memberikan yang terbaik hari ini!"
]

@router.get("/morning-alert")
async def trigger_morning_alert(request: Request):
    global last_morning_alert_date
    from main import send_whatsapp_message, supabase_client

    wib = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib)
    today_date_str = now_wib.strftime("%Y-%m-%d")
    today_day_name = HARI_INDONESIA[now_wib.weekday()]
    is_sunday = now_wib.weekday() == 6

    if last_morning_alert_date == today_date_str:
        return {
            "status": "skipped",
            "message": "Morning alert hari ini sudah pernah dikirim sebelumnya.",
        }

    try:
        # 1. Ambil data pengguna aktif
        res = (
            supabase_client.table("wa_identities")
            .select("wa_number, nama, role, person_id, kelas, jenjang")
            .eq("status", "ACTIVE")
            .execute()
        )

        if not res.data:
            return {
                "status": "success",
                "sent_count": 0,
                "message": "Tidak ada pengguna aktif.",
            }

        sent_count = 0
        for user in res.data:
            to_phone = user.get("wa_number")
            nama = user.get("nama", "Sobat")
            role = user.get("role", "SISWA")
            user_kelas = user.get("kelas", "7")
            user_jenjang = user.get("jenjang", "MTS")

            if is_sunday:
                if role == "SISWA":
                    pesan = (
                        f"Selamat pagi, *{nama}*! ☀️🌴\n\n"
                        f"Selamat hari Minggu! Selamat beristirahat sejenak dan menikmati akhir pekan bersama keluarga.\n\n"
                        f"Isi ulang semangatmu untuk menyambut pekan baru esok hari ya! ✨"
                    )
                else:
                    pesan = (
                        f"Selamat pagi, Ustadzah *{nama}*! ☀️☕\n\n"
                        f"Selamat menikmati hari Minggu yang tenang bersama keluarga. Semoga waktu istirahat ini membawa kesegaran untuk pekan pengabdian berikutnya."
                    )
            else:
                if role == "SISWA":
                    # Query jadwal UTS HARI INI
                    drill_res = (
                        supabase_client.table("uts_schedules")
                        .select("*")
                        .eq("tanggal_ujian", today_date_str)
                        .eq("kelas", str(user_kelas))
                        .eq("jenjang", str(user_jenjang).upper())
                        .execute()
                    )
                    
                    uts_info = drill_res.data[0] if drill_res and drill_res.data else None
                    motivation_tip = random.choice(MORNING_MOTIVATION)

                    if uts_info:
                        mapel_hari_ini = uts_info.get("mapel", "Mata Pelajaran UTS")
                        pesan = (
                            f"Selamat pagi, *{nama}*! ☀️🎒\n\n"
                            f"🔥 *HARI-H UTS ({today_day_name.upper()})*\n"
                            f"Ujian kamu hari ini: *{mapel_hari_ini}* (Kelas {user_kelas})\n\n"
                            f"{motivation_tip}\n\n"
                            f"📚 *Ulas Rumus Cepat (5 Menit):*\n"
                            f"Cek cheat sheet & rumus penting di PWA RoboMANTAP:\n"
                            f"👉 https://robomantap-app.vercel.app\n\n"
                            f"Bismillah, fokus dan sukses ujiannya hari ini ya! 💯"
                        )
                    else:
                        pesan = (
                            f"Selamat pagi, *{nama}*! ☀️🎒\n\n"
                            f"Selamat menyambut hari {today_day_name}! Jangan lupa persiapkan kelengkapan sekolah dan niat terbaik dalam menuntut ilmu.\n\n"
                            f"{motivation_tip}\n\n"
                            f"📲 Akses Portal Belajar RoboMANTAP:\n"
                            f"👉 https://robomantap-app.vercel.app\n\n"
                            f"Semangat beraktivitas! ✨"
                        )
                else:
                    pesan = (
                        f"Selamat pagi, Ustadzah *{nama}*! ☀️☕\n\n"
                        f"Semoga senantiasa diberikan kesehatan dan kelancaran dalam mendampingi para santri pada ujian hari {today_day_name} ini.\n\n"
                        f"Salam hangat dari RoboMANTAP!"
                    )

            # Kirim pesan via WhatsApp
            send_whatsapp_message(to_phone, pesan)
            sent_count += 1

            # Log audit pengiriman
            try:
                delivery_payload = {
                    "delivery_id": str(uuid.uuid4()),
                    "recipient_person_id": user.get("person_id"),
                    "status": "SENT",
                    "channel": "WHATSAPP",
                    "idempotency_key": f"morning_alert_{to_phone}_{today_date_str}",
                    "message_text": pesan
                }

                supabase_client.table("automation_deliveries").insert(
                    delivery_payload
                ).execute()
            except Exception as log_err:
                print(f"LOG WARNING: Gagal catat log delivery {to_phone}: {log_err}")

        last_morning_alert_date = today_date_str

        print(
            f"LOG Morning Alert (Sunday: {is_sunday}) Berhasil terkirim ke "
            f"{sent_count} nomor pada {today_date_str}."
        )
        return {
            "status": "success",
            "is_sunday": is_sunday,
            "sent_count": sent_count,
        }

    except Exception as e:
        print(f"LOG ERROR Morning Alert: {e}")
        return {"status": "error", "detail": str(e)}, 500
