from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import os
import requests
import firebase_admin
from firebase_admin import credentials, firestore, auth

app = FastAPI()

# إعداد Firebase
cred = credentials.Certificate("firebase-config.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class Message(BaseModel):
    text: str
    user_id: str = None

class UserRegister(BaseModel):
    email: str
    password: str
    name: str

class UserLogin(BaseModel):
    email: str
    password: str

# دالة للتحقق من Firebase Token
def verify_firebase_token(id_token: str):
    try:
        decoded_token = auth.verify_id_token(id_token)
        return decoded_token['uid']  # إرجاع user_id من Firebase
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

# التسجيل (اختياري - يمكن استخدام Firebase Auth مباشرة)
@app.post("/register")
def register(user: UserRegister):
    try:
        # التحقق إذا الإيميل موجود مسبقاً
        existing_user = db.collection('users').where('email', '==', user.email).get()
        if len(existing_user) > 0:
            raise HTTPException(status_code=400, detail="Email already exists")
        
        # إنشاء مستخدم جديد
        user_ref = db.collection('users').document()
        user_ref.set({
            'email': user.email,
            'password': user.password,
            'name': user.name,
            'provider': 'email',
            'created_at': firestore.SERVER_TIMESTAMP
        })
        
        return {"message": "User created successfully", "user_id": user_ref.id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# تسجيل الدخول (اختياري)
@app.post("/login")
def login(user: UserLogin):
    try:
        # البحث عن المستخدم
        users_ref = db.collection('users')
        query = users_ref.where('email', '==', user.email).where('password', '==', user.password)
        results = query.get()
        
        if len(results) == 0:
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        user_data = results[0].to_dict()
        return {
            "message": "Login successful", 
            "user_id": results[0].id,
            "user_name": user_data.get('name')
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# الدردشة مع دعم Firebase Auth
@app.post("/chat")
def chat(msg: Message, authorization: str = Header(None)):
    user_id = None
    
    # المحاولة 1: استخدام Firebase Token
    if authorization and authorization.startswith("Bearer "):
        id_token = authorization.replace("Bearer ", "")
        user_id = verify_firebase_token(id_token)
    
    # المحاولة 2: استخدام user_id من الجسم (للتوافق مع النظام القديم)
    if not user_id and msg.user_id:
        user_id = msg.user_id
    
    # إذا لا يوجد user_id، يمكنك رفض الطلب أو السماح بدون حفظ
    # هنا سأسمح ولكن بدون حفظ المحادثة
    can_save_chat = bool(user_id)

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "user", "content": msg.text}
        ]
    }

    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        json=payload,
        headers=headers
    )

    result = response.json()
    ai_response = result["choices"][0]["message"]["content"]
    
    # حفظ المحادثة إذا كان هناك user_id
    if can_save_chat:
        chat_ref = db.collection('chats').document()
        chat_ref.set({
            'user_id': user_id,
            'message_text': msg.text,
            'ai_response': ai_response,
            'created_at': firestore.SERVER_TIMESTAMP
        })
    
    return {"reply": ai_response, "user_id": user_id}

# جلب محادثات المستخدم مع دعم Firebase Auth
@app.get("/user_chats")
def get_user_chats(authorization: str = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    id_token = authorization.replace("Bearer ", "")
    user_id = verify_firebase_token(id_token)
    
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    try:
        chats_ref = db.collection('chats')
        query = chats_ref.where('user_id', '==', user_id).order_by('created_at')
        results = query.get()
        
        chats = []
        for doc in results:
            chat_data = doc.to_dict()
            chat_data['id'] = doc.id
            chats.append(chat_data)
            
        return {"chats": chats}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/")
def home():
    return {"message": "AI Chat API is running!"}
