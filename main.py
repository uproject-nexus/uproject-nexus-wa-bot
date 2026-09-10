import os
import random
import requests
from fastapi import FastAPI, Request, Response
import google.generativeai as genai

app = FastAPI()

# --- CONFIGURATION ---
VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "robomantap_secret_token")
WHATSAPP_TOKEN = os.getenv("WA_ACCESS_TOKEN")
PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")

# Rotasi API Key Gratis Gemini (Dipisahkan koma di Render)
GEMINI_KEYS_RAW = os.getenv("GEMINI_KEYS", "")
GEMINI_KEYS = [k.strip() for k in GEMINI_KEYS_RAW.split(",") if k.strip()]

def get_random_gemini_key():
    """Mengambil salah satu API key gratis secara acak"""
    if GEMINI_KEYS:
        return random.choice(GEMINI_KEYS)
    return os.getenv("GEMINI_API_KEY", "")

def generate_ai_response(prompt_text):
    """Panggil Gemini Flash-Lite dengan Rotasi Key"""
    selected_key = get_random_gemini_key()
    if not selected_key:
        return "Sistem AI belum mengonfigurasi API Key."
        
    try:
        genai.configure(api_key=selected_key)
        # Menggunakan model Flash-Lite gratis
        model = genai.GenerativeModel("gemini-2.5-flash-lite")
        
        system_instruction = (
            "Anda adalah Asisten AI U.Project Nexus (RoboMANTAP) untuk Madrasah Al-Irsyad Al-Islamiyah Putri Bondowoso. "
            "Jawablah pertanyaan dengan ramah, santun, cerdas, dan membantu."
        )
        
        response = model.generate_content(f"{system_instruction}\n\nPertanyaan: {prompt_text}")
        return response.text
    except Exception as e:
        print(f"Error Gemini API ({selected_key[:6]}...): {e}")
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
        requests.post(url, json=payload, headers=headers)
    except Exception as e:
        print(f"Error sending WA message: {e}")

# --- WEBHOOK ENDPOINTS ---
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
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        if "messages" in entry:
            message = entry["messages"][0]
            from_number = message["from"]
            
            if message.get("type") == "text":
                user_text = message["text"]["body"]
                
                # Proses dengan Gemini AI
                ai_reply = generate_ai_response(user_text)
                
                # Kirim balasan ke WA
                send_whatsapp_message(from_number, ai_reply)
    except Exception as e:
        print(f"Error processing payload: {e}")
        
    return {"status": "success"}
