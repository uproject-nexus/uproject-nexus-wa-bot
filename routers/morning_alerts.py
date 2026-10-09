from datetime import datetime
from fastapi import APIRouter, Request
import pytz

router = APIRouter(prefix="/api", tags=["Morning Alert"])
last_morning_alert_date = None

@app.get("/morning-alert")
async def trigger_morning_alert(request: Request):
  global last_morning_alert_date
  from main import send_whatsapp_message, supabase_client

  # Tentukan Zona Waktu Indonesia Barat (WIB)
  wib = pytz.timezone("Asia/Jakarta")
  now_wib = datetime.now(wib)
  today_date_str = now_wib.strftime("%Y-%m-%d")  # Contoh: "2026-10-11"

  # Cek apakah hari ini hari Minggu (weekday == 6)
  is_sunday = now_wib.weekday() == 6

  # PENGAMAN: Jika hari ini sudah pernah dikirim, tolak eksekusi berikutnya!
  if last_morning_alert_date == today_date_str:
    return {
        "status": "skipped",
        "message": "Morning alert hari ini sudah pernah dikirim sebelumnya.",
    }

  try:
    # 1. PERUBAHAN: Tambahkan person_id pada select query
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
      person_id = user.get("person_id")

      # --- CABANG PESAN: HARI MINGGU VS HARI EFEKTIF ---
      if is_sunday:
        if role == "SISWA":
          pesan = (
              f"Selamat pagi, *{nama}*! ☀️🌴\n\n"
              f"Selamat hari Minggu dan menikmati hari libur! Waktunya"
              f" beristirahat sejenak, melepas penat, dan berkumpul bersama"
              f" keluarga tercinta.\n\nMeskipun libur, aku asisten setiamu"
              f" tetap siaga di sini kalau kamu butuh teman belajar nanti."
              f" Selamat menikmati akhir pekan! ✨"
          )
        else:
          pesan = (
              f"Selamat pagi, Ustadzah *{nama}*! ☀️☕\n\nSelamat menikmati"
              f" akhir pekan di hari Minggu yang tenang. Semoga waktu libur"
              f" ini membawa kebugaran dan kebahagiaan bersama keluarga"
              f" tercinta."
          )
      else:
        if role == "SISWA":
          pesan = (
              f"Selamat pagi, *{nama}*! ☀️🎒\n\nWaktunya bersiap-siap dengan"
              f" gembira menuju sekolah! Semoga hari ini penuh dengan ilmu yang"
              f" bermanfaat.\n\nOh iya, jangan lupa... aku adalah asistenmu"
              f" yang hebat di WA, siap membantumu belajar kapan saja!"
              f" Semangat! ✨"
          )
        else:
          pesan = (
              f"Selamat pagi, Ustadzah *{nama}*! ☀️☕\n\nSemoga hari ini"
              f" senantiasa diberikan kesehatan, kelancaran, dan keberkahan"
              f" dalam membersamai para santri menuntut ilmu.\n\nSalam hangat"
              f" dari asisten digital Anda di WhatsApp!"
          )

      # Kirim pesan menggunakan fungsi WhatsApp yang ada
      send_whatsapp_message(to_phone, pesan)
      sent_count += 1

      # 2. PERUBAHAN: Sisipkan log pengiriman ke automation_deliveries di sini
      try:
        delivery_payload = {
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

    # Tandai bahwa hari ini alert sudah sukses dikirim
    last_morning_alert_date = today_date_str

    print(
        f"LOG Morning Alert (Sunday: {is_sunday}) Berhasil terkirim ke"
        f" {sent_count} nomor pada {today_date_str}."
    )
    return {
        "status": "success",
        "is_sunday": is_sunday,
        "sent_count": sent_count,
    }

  except Exception as e:
    print(f"LOG ERROR Morning Alert: {e}")
    return {"status": "error", "detail": str(e)}, 500