from datetime import datetime, timedelta
from fastapi import APIRouter, Request
import pytz
import uuid

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

@router.get("/night-alert")
async def trigger_night_alert(request: Request):
    global last_night_alert_date
    from main import send_whatsapp_message, supabase_client, fetch_uts_schedule_rows, is_notification_enabled

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
            .select("wa_number, nama, role, person_id, metadata")
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
            metadata = user.get("metadata") or {}
            user_kelas = str(metadata.get("kelas") or user.get("kelas") or "7")
            user_jenjang = str(metadata.get("jenjang") or user.get("jenjang") or "MTS").upper()

            if role == "SISWA" and not is_notification_enabled(to_phone, "night_alert_enabled"):
                continue

            if role == "SISWA":
                schedule_rows = fetch_uts_schedule_rows(
                    user_kelas, user_jenjang, tanggal_ujian=tomorrow_date_str
                )
                uts_info = schedule_rows[0] if schedule_rows else None

                if uts_info:
                    mapel_besok = uts_info.get("mapel", "Mata Pelajaran UTS")
                    soal_list = uts_info.get("soal_pemanasan", [])
                    pesan = get_night_alert_student_msg(
                        nama, tomorrow_day_name, mapel_besok, user_kelas, soal_list
                    )
                else:
                    pesan = get_night_alert_student_fallback_msg(nama, tomorrow_day_name)
            else:
                pesan = get_night_alert_teacher_msg(nama, tomorrow_day_name)

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
