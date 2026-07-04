from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Form
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from core.database import get_db, User, VerificationCode, ApiKey, SystemSetting, PaymentRequest, ConversationHistory
from core.security import get_current_user, get_current_admin, create_access_token
from services.key_manager import KeyManager
from services.ai_orchestrator import AIOrchestrator
from services.file_processor import FileProcessor
import datetime
import random
import os

app = FastAPI(title="Omega AI Chat")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VIP_LIMITS = {0: 15, 1: 100, 2: 150, 3: 99999}
VIP_PRICES = {1: 1000, 2: 2500, 3: 5000}

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("index.html")

@app.post("/register/request")
def register_request(request: Request, phone_number: str = Form(...), db: Session = Depends(get_db)):
    if db.query(User).filter(User.phone_number == phone_number).first():
        raise HTTPException(status_code=400, detail="Numéro déjà utilisé")
    
    client_ip = request.client.host
    if db.query(User).filter(User.ip_address == client_ip).first():
        raise HTTPException(status_code=403, detail="Un compte existe déjà depuis cette IP")
    
    new_user = User(phone_number=phone_number, ip_address=client_ip, is_verified=False)
    db.add(new_user)
    db.commit()
    
    return {"msg": "Demande enregistrée. Attendez le code de validation sur WhatsApp."}

@app.get("/admin/pending-users")
def get_pending_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = db.query(User).filter(User.is_verified == False).all()
    return [{"id": u.id, "phone": u.phone_number, "ip": u.ip_address} for u in users]

@app.post("/admin/generate-code")
def generate_code(phone_number: str = Form(...), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    code = str(random.randint(100000, 999999))
    verification = VerificationCode(phone_number=phone_number, code=code)
    db.add(verification)
    db.commit()
    return {"code": code, "msg": "Code généré. Envoyez-le via WhatsApp."}

@app.post("/login/verify")
def login_verify(phone_number: str = Form(...), code: str = Form(...), db: Session = Depends(get_db)):
    verification = db.query(VerificationCode).filter(
        VerificationCode.phone_number == phone_number,
        VerificationCode.code == code,
        VerificationCode.is_used == False
    ).first()
    
    if not verification:
        raise HTTPException(status_code=400, detail="Code invalide")
    
    user = db.query(User).filter(User.phone_number == phone_number).first()
    user.is_verified = True
    verification.is_used = True
    db.commit()
    
    token = create_access_token({"sub": user.phone_number})
    return {"token": token}

@app.get("/api/me")
def get_me(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = datetime.datetime.utcnow().date()
    if current_user.last_reset_date.date() < today:
        current_user.daily_message_count = 0
        current_user.last_reset_date = datetime.datetime.utcnow()
        db.commit()
    
    if current_user.vip_expiry and current_user.vip_expiry < datetime.datetime.utcnow():
        current_user.vip_level = 0
        db.commit()
    
    limit = VIP_LIMITS.get(current_user.vip_level, 15)
    return {
        "phone": current_user.phone_number,
        "vip_level": current_user.vip_level,
        "daily_count": current_user.daily_message_count,
        "limit": limit,
        "is_admin": current_user.is_admin
    }

@app.post("/api/chat/send")
async def send_message(
    prompt: str = Form(...),
    use_thinking: bool = Form(False),
    file: UploadFile = File(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    today = datetime.datetime.utcnow().date()
    if current_user.last_reset_date.date() < today:
        current_user.daily_message_count = 0
        current_user.last_reset_date = datetime.datetime.utcnow()
        db.commit()
    
    limit = VIP_LIMITS.get(current_user.vip_level, 15)
    if current_user.daily_message_count >= limit:
        raise HTTPException(status_code=403, detail=f"Quota atteint ({limit}/{limit})")
    
    km = KeyManager(db)
    try:
        api_key = km.get_available_key(max_rpm=5)
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))
    
    settings = db.query(SystemSetting).first()
    system_prompt = settings.prompt_system if settings else "Tu es une IA utile."
    thinking_budget = settings.thinking_budget if settings and use_thinking else 0
    
    file_info = None
    if file:
        file_info = await FileProcessor.process_file(file)
    
    orchestrator = AIOrchestrator(api_key, system_prompt, thinking_budget)
    full_prompt = orchestrator.build_prompt(prompt, file_info)
    
    current_user.daily_message_count += 1
    db.commit()
    
    if current_user.vip_level >= 2:
        history = ConversationHistory(user_id=current_user.id, role="user", content=prompt)
        db.add(history)
        db.commit()
    
    async def generate():
        full_response = ""
        async for chunk in orchestrator.stream_response(full_prompt, file_info):
            full_response += chunk
            yield chunk
        
        if current_user.vip_level >= 2:
            history = ConversationHistory(user_id=current_user.id, role="assistant", content=full_response)
            db.add(history)
            db.commit()
    
    return StreamingResponse(generate(), media_type="text/plain")

@app.get("/api/history")
def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.vip_level < 2:
        return {"history": []}
    
    messages = db.query(ConversationHistory).filter(
        ConversationHistory.user_id == current_user.id
    ).order_by(ConversationHistory.created_at.desc()).limit(50).all()
    
    return {"history": [{"role": m.role, "content": m.content, "date": m.created_at.isoformat()} for m in reversed(messages)]}

@app.post("/api/payment/request")
def request_payment(plan_level: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if plan_level not in VIP_PRICES:
        raise HTTPException(status_code=400, detail="Plan invalide")
    
    payment = PaymentRequest(
        user_phone=current_user.phone_number,
        plan_level=plan_level,
        amount_fcfa=VIP_PRICES[plan_level]
    )
    db.add(payment)
    db.commit()
    
    return {
        "payment_id": payment.id,
        "amount": VIP_PRICES[plan_level],
        "whatsapp": f"https://wa.me/24174569963?text=Je souhaite payer VIP {plan_level} ({VIP_PRICES[plan_level]} FCFA). ID: #{payment.id}"
    }

@app.post("/api/payment/upload/{payment_id}")
async def upload_proof(payment_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    payment = db.query(PaymentRequest).filter(PaymentRequest.id == payment_id).first()
    if not payment or payment.user_phone != current_user.phone_number:
        raise HTTPException(status_code=403)
    
    os.makedirs("proofs", exist_ok=True)
    filename = f"proofs/{payment_id}_{file.filename}"
    with open(filename, "wb") as f:
        content = await file.read()
        f.write(content)
    
    payment.proof_image_url = filename
    db.commit()
    
    return {"msg": "Preuve envoyée"}

@app.get("/admin/payments")
def get_pending_payments(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    payments = db.query(PaymentRequest).filter(PaymentRequest.status == "pending").all()
    return [{"id": p.id, "phone": p.user_phone, "level": p.plan_level, "amount": p.amount_fcfa, "proof": p.proof_image_url} for p in payments]

@app.post("/admin/validate-payment/{payment_id}")
def validate_payment(payment_id: int, db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    payment = db.query(PaymentRequest).filter(PaymentRequest.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404)
    
    payment.status = "paid"
    user = db.query(User).filter(User.phone_number == payment.user_phone).first()
    user.vip_level = payment.plan_level
    user.vip_expiry = datetime.datetime.utcnow() + datetime.timedelta(weeks=1)
    db.commit()
    
    return {"msg": "VIP activé"}

@app.get("/admin/users")
def get_all_users(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    users = db.query(User).all()
    return [{"id": u.id, "phone": u.phone_number, "vip": u.vip_level, "verified": u.is_verified} for u in users]

@app.post("/admin/set-vip/{user_id}")
def set_vip(user_id: int, level: int = Form(...), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.vip_level = level
        user.vip_expiry = datetime.datetime.utcnow() + datetime.timedelta(weeks=1)
        db.commit()
    return {"msg": "VIP mis à jour"}

@app.get("/admin/keys")
def get_keys(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    keys = db.query(ApiKey).all()
    return [{"id": k.id, "count": k.request_count_minute} for k in keys]

@app.post("/admin/add-key")
def add_key(key_value: str = Form(...), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    new_key = ApiKey(key_value=key_value)
    db.add(new_key)
    db.commit()
    return {"msg": "Clé ajoutée"}

@app.get("/admin/prompt")
def get_prompt(db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    settings = db.query(SystemSetting).first()
    return {"prompt": settings.prompt_system if settings else ""}

@app.post("/admin/update-prompt")
def update_prompt(new_prompt: str = Form(...), db: Session = Depends(get_db), admin: User = Depends(get_current_admin)):
    settings = db.query(SystemSetting).first()
    if not settings:
        settings = SystemSetting(prompt_system=new_prompt)
        db.add(settings)
    else:
        settings.prompt_system = new_prompt
    db.commit()
    return {"msg": "Prompt mis à jour"}

app.mount("/", StaticFiles(directory=".", html=True), name="static")
