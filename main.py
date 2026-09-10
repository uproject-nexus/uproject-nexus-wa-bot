import os
import random
import requests
from fastapi import FastAPI, Request, Response
import google.generativeai as genai

app = FastAPI()

# --- KONFIGURASI ENV ---
VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "robomantap_secret_token")
WHATSAPP_TOKEN = os.getenv("WA_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")

# Rotasi API Key Gemini (Pisahkan koma di Render)
GEMINI_KEYS_RAW = os.getenv("GEMINI_KEYS", "")
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS_RAW.split(",") if k.strip()]

# Tuple Model Pilihan
MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite")

def get_random_gemini_key():
    """Mengambil salah satu API key gratis secara acak"""
    if GEMINI_KEYS:
        return random.choice(GEMINI_KEYS)
    return os.getenv("GEMINI_API_KEY", "")

def generate_ai_response(prompt_text):
    """Panggil Gemini AI menggunakan rotasi Key & Model"""
    selected_key = get_random_gemini_key()
    if not selected_key:
        print("LOG ERROR: Variabel GEMINI_KEYS kosong atau tidak terdeteksi.")
        return "Sistem AI belum mengonfigurasi API Key."
        
    # Memilih model secara acak dari tuple MODELS
    selected_model = random.choice(MODELS)
        
    try:
        genai.configure(api_key=selected_key)
        model = genai.GenerativeModel(selected_model)
        
        system_instruction = (
            "Anda adalah Asisten AI U.Project Nexus (RoboMANTAP) untuk Madrasah Al-Irsyad Al-Islamiyah Putri Bondowoso. "
            "Jawablah pertanyaan dengan ramah, santun, cerdas, dan membantu."
        )
        
        response = model.generate_content(f"{system_instruction}\n\nPertanyaan: {prompt_text}")
        print(f"LOG Sukses AI -> Model: {selected_model} | Key: {selected_key[:6]}...")
        return response.text
    except Exception as e:
        print(f"LOG ERROR Gemini API ({selected_model} | Key: {selected_key[:6]}...): {e}")
        return "Mohon maaf, sistem AI sedang padat. Silakan kirim ulang pesan Anda beberapa saat lagi."

def send_whatsapp_message(to_phone, message_text):
    """Kirim balik balasan ke WhatsApp via Meta API"""
    url = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message_text}
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        print(f"LOG Send WA Status Code: {res.status_code}")
        if res.status_code != 200:
            print(f"LOG Meta API Error Response: {res.text}")
    except Exception as e:
        print(f"LOG ERROR Sending WA Message: {e}")

# --- ENDPOINT WEBHOOK ---
@app.get("/")
async def root():
    return {"message": "U.Project Nexus WhatsApp Webhook Running!"}

@app.get("/webhook")
async def verify_webhook(request: Request):
    """Verifikasi Webhook oleh Meta"""
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return Response(content=challenge, status_code=200)
    return Response(content="Verification failed", status_code=403)

@app.post("/webhook")
async def receive_whatsapp(request: Request):
    """Menerima Pesan Masuk dari WhatsApp"""
    data = await request.json()
    print(f"LOG Incoming Webhook Payload: {data}")
    try:
        entry = data.get("entry", [])[0]
        changes = entry.get("changes", [])[0]
        value = changes.get("value", {})
        
        if "messages" in value:
            message = value["messages"][0]
            from_number = message["from"]
            
            if message.get("type") == "text":
                user_text = message["text"]["body"]
                print(f"LOG Pesan Masuk ({from_number}): {user_text}")
                
                # Olah dengan Gemini AI
                ai_reply = generate_ai_response(user_text)
                print(f"LOG Balasan AI Terbentuk: {ai_reply[:50]}...")
                
                # Kirim ke WhatsApp
                send_whatsapp_message(from_number, ai_reply)
    except Exception as e:
        print(f"LOG ERROR Processing Webhook Payload: {e}")
        
    return {"status": "success"}
