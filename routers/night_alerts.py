from datetime import datetime
from fastapi import APIRouter, Request
import pytz

router = APIRouter(prefix="/api", tags=["Night Alert"])
last_night_alert_date = None


@router.get("/night-alert")
async def trigger_night_alert(request: Request):
  global last_night_alert_date
  from main import send_whatsapp_message, supabase_client

  wib = pytz.timezone("Asia/Jakarta")
  now_wib = datetime.now(wib)
  today_date_str = now_wib.strftime("%Y-%m-%d")
  is_sunday = now_wib.weekday() == 6

  if last_night_alert_date == today_date_str:
    return {
        "status": "skipped",
        "message": "Night alert hari ini sudah pernah dikirim.",
    }

  try:
    res = (
        supabase_client.table("wa_identities")
        .select("wa_number, nama, role, person_id")
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

      if is_sunday:
        if role == "SISWA":
          pesan = (
              f"Selamat malam, *{nama}*! 🌙✨\n\nSemoga hari liburmu"
              " menyenangkan! Jangan lupa persiapkan kelengkapan sekolah untuk"
              " esok hari, lalu istirahat yang cukup agar esok siap menyambut"
              " pekan baru dengan segar.\n\nSelamat tidur dan bermimpi indah! 😴"
          )
        else:
          pesan = (
              f"Selamat malam, Ustadzah *{nama}*! 🌙☕\n\nSemoga waktu"
              " istirahat di akhir pekan ini menyegarkan kembali semangat Anda."
              " Selamat beristirahat dan menyambut pekan pengabdian besok pagi."
          )
      else:
        if role == "SISWA":
          pesan = (
              f"Selamat malam, *{nama}*! 🌙📖\n\nKerja bagus untuk usahamu hari"
              " ini! Pastikan semua tugas sudah selesai dan persiapkan buku"
              " untuk besok pagi. Kalau butuh bantuan belajar, aku selalu siap"
              " di sini.\n\nSelamat beristirahat dan tidur nyenyak! 💤"
          )
        else:
          pesan = (
              f"Selamat malam, Ustadzah *{nama}*! 🌙✨\n\nTerima kasih atas"
              " segala dedikasi dan bimbingan yang telah diberikan kepada para"
              " santri hari ini. Selamat beristirahat, semoga lelah Anda menjadi"
              " lumbung pahala."
          )

      send_whatsapp_message(to_phone, pesan)
      sent_count += 1

      try:
        delivery_payload = {
            "recipient_person_id": user.get("person_id"),
            "status": "SENT",
            "channel": "WHATSAPP",
            "idempotency_key": f"night_alert_{to_phone}_{today_date_str}",
            "message_text": pesan,
        }
        supabase_client.table("automation_deliveries").insert(
            delivery_payload
        ).execute()
      except Exception as log_err:
        print(f"LOG WARNING: Gagal catat log night alert {to_phone}: {log_err}")

    last_night_alert_date = today_date_str
    print(
        f"LOG Night Alert Berhasil terkirim ke {sent_count} nomor pada"
        f" {today_date_str}."
    )
    return {"status": "success", "sent_count": sent_count}

  except Exception as e:
    print(f"LOG ERROR Night Alert: {e}")
    return {"status": "error", "detail": str(e)}, 500