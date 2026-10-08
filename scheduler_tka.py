import os
import time
import uuid
import requests
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

# Konfigurasi Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Konfigurasi WA Bot Endpoint
WA_BOT_URL = os.getenv("WA_BOT_URL", "https://URL-WA-BOT-ANDA.render.com")
AUTOMATION_SHARED_SECRET = os.getenv("AUTOMATION_SHARED_SECRET", "")

def get_expiring_tkas():
    """Mencari paket TKA yang akan kedaluwarsa dalam 2 Jam ke depan."""
    now = datetime.now(timezone.utc)
    warning_window = now + timedelta(hours=2)
    
    try:
        # Asumsi tabel paket bernama tka_packages (sesuaikan dengan tka_engine Anda)
        res = supabase.table("tka_packages").select("*").execute()
        expiring = []
        for pkg in res.data:
            config = pkg.get("config", {})
            active_until_raw = config.get("active_until")
            if not active_until_raw:
                continue
            
            # Parsing waktu dari string ISO
            active_until = datetime.fromisoformat(active_until_raw.replace("Z", "+00:00"))
            if active_until.tzinfo is None:
                active_until = active_until.replace(tzinfo=timezone.utc)
                
            # Jika sisa waktu antara 0 hingga 2 jam
            if now < active_until <= warning_window:
                expiring.append({
                    "kode_tka": config.get("kode_tka"),
                    "mapel": config.get("mapel", "Mata Uji"),
                    "active_until": active_until
                })
        return expiring
    except Exception as e:
        print(f"Error fetching TKA packages: {e}")
        return []

def get_unfinished_students(kode_tka: str):
    """Mencari siswa yang belum selesai (Status 'BERJALAN') pada kode TKA tertentu."""
    try:
        # Asumsi tabel progres bernama tka_progress
        res = supabase.table("tka_progress") \
            .select("session_id, nama_siswa, status") \
            .eq("kode_tka", kode_tka) \
            .eq("status", "BERJALAN") \
            .execute()
        return res.data
    except Exception as e:
        print(f"Error fetching unfinished students for {kode_tka}: {e}")
        return []

def resolve_person_id(nama_siswa: str):
    """Mencocokkan nama siswa dengan person_id di wa_identities."""
    try:
        res = supabase.table("student_intelligence_profiles") \
            .select("student_key") \
            .ilike("nama_siswa", f"%{nama_siswa}%") \
            .limit(1).execute()
        if res.data:
            return res.data[0].get("student_key")
    except Exception as e:
        print(f"Error resolving person_id for {nama_siswa}: {e}")
    return None

def trigger_wa_bot_reminder():
    print(f"[{datetime.now()}] Memulai Pemindaian Proaktif TKA...")
    expiring_tkas = get_expiring_tkas()
    
    for tka in expiring_tkas:
        kode = tka['kode_tka']
        waktu_habis = tka['active_until'].astimezone(timezone(timedelta(hours=7))).strftime("%H:%M WIB")
        mapel = tka['mapel']
        
        students = get_unfinished_students(kode)
        for std in students:
            nama = std['nama_siswa']
            person_id = resolve_person_id(nama)
            
            if not person_id:
                continue
                
            idempotency_key = f"tka_remind_{kode}_{std['session_id']}"
            
            # Cek apakah sudah pernah diingatkan (agar tidak spam)
            check = supabase.table("automation_deliveries").select("id").eq("idempotency_key", idempotency_key).execute()
            if check.data:
                continue # Sudah dikirim
                
            pesan = (
                f"🚨 *PENGINGAT OTOMATIS TKA* 🚨\n\n"
                f"Halo *{nama}*! 🧕🏼\n"
                f"RoboMANTAP melihat kamu belum menyelesaikan sesi Ujian TKA *{mapel}*.\n\n"
                f"⚠️ *Perhatian:* Akses TKA ini akan segera ditutup pada pukul *{waktu_habis}*.\n\n"
                f"Yuk segera selesaikan sebelum batas waktunya habis! Semangat Santri Hebat! 💪🔥"
            )
            
            # 1. Daftarkan ke tabel antrean automation_deliveries
            supabase.table("automation_deliveries").insert({
                "idempotency_key": idempotency_key,
                "recipient_person_id": person_id,
                "status": "PENDING",
                "message_type": "TKA_REMINDER"
            }).execute()
            
            # 2. Tembak webhook bot untuk memicu pengiriman
            headers = {"X-Automation-Secret": AUTOMATION_SHARED_SECRET}
            payload = {
                "recipient_person_id": person_id,
                "message_text": pesan,
                "idempotency_key": idempotency_key
            }
            try:
                requests.post(f"{WA_BOT_URL}/automation/deliver", json=payload, headers=headers, timeout=10)
                print(f"Berhasil memicu reminder untuk {nama}")
            except Exception as e:
                print(f"Gagal memicu webhook endpoint untuk {nama}: {e}")
