from datetime import datetime, timedelta
from fastapi import APIRouter, Request
import pytz
import uuid
import random

from wa_prompts import (
    get_night_alert_student_msg,
    get_night_alert_student_fallback_msg,
    get_night_alert_teacher_msg
)

router = APIRouter(prefix="/api", tags=["Night Alert UTS AI"])
last_night_alert_date = None

HARI_INDONESIA = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"
}

# Micro-tips pendek dan santai
STUDY_TIPS = [
    "💡 *Tips:* Siapkan seragam dan alat tulis di meja sekarang ya, biar besok pagi nggak grusa-grusu.",
    "💡 *Tips:* Coba ulas sebentar poin penting materi, habis itu langsung tidur biar otaknya fresh!",
    "💡 *Tips:* Jangan lupa minum air putih dan hindari begadang malam ini yaa.",
    "💡 *Tips:* Belajar 15-20 menit aja malam ini, yang penting konsentrasi!"
]

@router.get("/night-alert")
async def trigger_night_alert(request: Request):
    global last_night_alert_date
    from main import send_whatsapp_message, supabase_client

    wib = pytz.timezone("Asia/Jakarta")
    now_wib = datetime.now(wib)
    today_date_str = now_wib.strftime("%Y-%m-%d")
    
    tomorrow_wib = now_wib + timedelta(days=1)
    tomorrow_date_str = tomorrow_wib.strftime("%Y-%m-%d")
    tomorrow_day_name = HARI_INDONESIA[tomorrow_wib.weekday()]

    if last_night_alert_date == today_date_str:
        return {"status": "skipped", "message": "Night alert UTS hari ini sudah dikirim."}

    try:
        res = (
            supabase_client.table("wa_identities")
            .select("wa_number, nama, role, person_id, kelas, jenjang")
            .eq("status", "ACTIVE")
            .execute()
        )

        if not res.data:
            return {"status": "success", "sent_count": 0, "message": "Tidak ada pengguna aktif."}

        sent_count = 0
        for user in res.data:
            to_phone = user.get("wa_number")
            nama = user.get("nama", "Sobat")
            role = user.get("role", "SISWA")
            user_kelas = user.get("kelas", "7")
            user_jenjang = user.get("jenjang", "MTS")

            if role == "SISWA":
                drill_res = (
                    supabase_client.table("uts_schedules")
                    .select("*")
                    .eq("tanggal_ujian", tomorrow_date_str)
                    .eq("kelas", str(user_kelas))
                    .eq("jenjang", str(user_jenjang).upper())
                    .execute()
                )
                
                uts_info = drill_res.data[0] if drill_res and drill_res.data else None
                random_tip = random.choice(STUDY_TIPS)

                if uts_info:
                    mapel_besok = uts_info.get("mapel", "Mata Pelajaran UTS")
                    soal_list = uts_info.get("soal_pemanasan", [])
                    
                    soal_text = ""
                    if soal_list:
                        for idx, item in enumerate(soal_list, 1):
                            soal_text += f"\n*{idx}. {item.get('pertanyaan')}*\n"
                            soal_text += f"   👉 Kunci: _{item.get('kunci')}_\n"

                    pesan = (
                        f"Haloo *{nama}*! 🌙\n\n"
                        f"Pengingat santai H-1 UTS besok (*{tomorrow_day_name}*):\n"
                        f"📌 *{mapel_besok}* (Kelas {user_kelas})\n\n"
                        f"Coba tebak kuis cepat ini dulu yuk:{soal_text}\n"
                        f"{random_tip}\n\n"
                        f"Kalau mau cobain simulasi UTS yang lebih lengkap, langsung klik di sini ya:\n"
                        f"👉 https://robomantap-app.vercel.app\n\n"
                        f"Semangat dan jangan lupa tidur cukup malam ini! ✨"
                    )
                else:
                    pesan = (
                        f"Haloo *{nama}*! 🌙\n\n"
                        f"Semangat ya buat pekan UTS-nya! Jangan lupa persiapkan materi untuk ujian besok (*{tomorrow_day_name}*).\n\n"
                        f"{random_tip}\n\n"
                        f"📲 Latihan & simulasi soal mandiri:\n"
                        f"👉 https://robomantap-app.vercel.app\n\n"
                        f"Selamat beristirahat! 💤"
                    )
            else:
                pesan = (
                    f"Selamat malam, Ustadzah *{nama}*! 🌙\n\n"
                    f"Pengingat H-1 UTS dan kuis pemanasan untuk santri esok hari ({tomorrow_day_name}) sudah terkirim otomatis.\n\n"
                    f"Selamat beristirahat!"
                )

            send_whatsapp_message(to_phone, pesan)
            sent_count += 1

            try:
                delivery_payload = {
                    "delivery_id": str(uuid.uuid4()),
                    "recipient_person_id": user.get("person_id"),
                    "status": "SENT",
                    "channel": "WHATSAPP",
                    "idempotency_key": f"uts_night_alert_{to_phone}_{today_date_str}",
                    "message_text": pesan,
                }
                supabase_client.table("automation_deliveries").insert(delivery_payload).execute()
            except Exception as log_err:
                print(f"LOG WARNING: Gagal catat log {to_phone}: {log_err}")

        last_night_alert_date = today_date_str
        return {"status": "success", "sent_count": sent_count}

    except Exception as e:
        print(f"LOG ERROR Night Alert: {e}")
        return {"status": "error", "detail": str(e)}, 500
