from datetime import datetime
from fastapi import APIRouter, Request
import pytz
import uuid

from wa_prompts import (
    get_morning_alert_student_msg,
    get_morning_alert_student_fallback_msg,
    get_morning_alert_sunday_student_msg,
    get_morning_alert_teacher_msg
)

router = APIRouter(prefix="/api", tags=["Morning Alert UTS AI"])
last_morning_alert_date = None

HARI_INDONESIA = {
    0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis", 4: "Jumat", 5: "Sabtu", 6: "Minggu"
}

@router.get("/morning-alert")
async def trigger_morning_alert(request: Request):
    global last_morning_alert_date
    from main import send_whatsapp_message, supabase_client, fetch_uts_schedule_rows, is_notification_enabled

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
        res = (
            supabase_client.table("wa_identities")
            .select("wa_number, nama, role, person_id, metadata")
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
            metadata = user.get("metadata") or {}
            user_kelas = str(metadata.get("kelas") or user.get("kelas") or "7")
            user_jenjang = str(metadata.get("jenjang") or user.get("jenjang") or "MTS").upper()

            if role == "SISWA" and not is_notification_enabled(to_phone, "morning_alert_enabled"):
                continue

            if is_sunday:
                if role == "SISWA":
                    pesan = get_morning_alert_sunday_student_msg(nama)
                else:
                    pesan = get_morning_alert_teacher_msg(nama, today_day_name, is_sunday=True)
            else:
                if role == "SISWA":
                    schedule_rows = fetch_uts_schedule_rows(
                        user_kelas, user_jenjang, tanggal_ujian=today_date_str
                    )
                    uts_info = schedule_rows[0] if schedule_rows else None

                    if uts_info:
                        mapel_hari_ini = uts_info.get("mapel", "Mata Pelajaran UTS")
                        pesan = get_morning_alert_student_msg(
                            nama, today_day_name, mapel_hari_ini, user_kelas
                        )
                    else:
                        pesan = get_morning_alert_student_fallback_msg(nama, today_day_name)
                else:
                    pesan = get_morning_alert_teacher_msg(nama, today_day_name, is_sunday=False)

            send_whatsapp_message(to_phone, pesan)
            sent_count += 1

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
