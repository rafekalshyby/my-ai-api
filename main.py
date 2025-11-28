from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
import os
import requests
import firebase_admin
from firebase_admin import credentials, firestore, auth
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AI Chat API", description="API for AI Chat Conversations Only")

# إعداد CORS للسماح لجميع المصادر (لتطبيقات الويب والموبايل)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # يمكنك تحديد domians محددة لاحقاً
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# إعداد Firebase
cred = credentials.Certificate("firebase-config.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class ChatMessage(BaseModel):
    text: str

# دالة للتحقق من Firebase Token
def verify_firebase_token(id_token: str):
    try:
        decoded_token = auth.verify_id_token(id_token)
        return {
            "user_id": decoded_token['uid'],
            "email": decoded_token.get('email', ''),
            "name": decoded_token.get('name', 'User')
        }
    except Exception as e:
        print(f"Token verification failed: {e}")
        return None

@app.get("/")
def home():
    return {
        "message": "AI Chat API is running!",
        "endpoints": {
            "chat": "POST /chat - Send message to AI",
            "user_chats": "GET /user_chats - Get user chat history"
        }
    }

@app.post("/chat")
async def chat_with_ai(
    message: ChatMessage,
    authorization: str = Header(..., description="Firebase ID Token in format: Bearer <token>")
):
    """
    إرسال رسالة للذكاء الاصطناعي وحفظ المحادثة
    """
    # التحقق من التوكن
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    id_token = authorization.replace("Bearer ", "")
    user_data = verify_firebase_token(id_token)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_id = user_data["user_id"]
    
    # الاتصال بـ Groq API
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROQ_API_KEY}"
    }

    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "user", "content": message.text}
        ],
        "temperature": 0.7,
        "max_tokens": 1000
    }

    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code, 
                detail=f"Groq API error: {response.text}"
            )
        
        result = response.json()
        ai_response = result["choices"][0]["message"]["content"]
        
        # حفظ المحادثة في Firebase
        chat_ref = db.collection('chats').document()
        chat_data = {
            'user_id': user_id,
            'user_email': user_data["email"],
            'user_name': user_data["name"],
            'message_text': message.text,
            'ai_response': ai_response,
            'created_at': firestore.SERVER_TIMESTAMP
        }
        
        chat_ref.set(chat_data)
        
        return {
            "success": True,
            "reply": ai_response,
            "message_id": chat_ref.id,
            "user_info": {
                "user_id": user_id,
                "name": user_data["name"]
            }
        }
        
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=408, detail="Request timeout - AI service is slow")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.get("/user_chats")
async def get_user_chats(
    authorization: str = Header(..., description="Firebase ID Token in format: Bearer <token>"),
    limit: int = 50
):
    """
    جلب سجل محادثات المستخدم
    """
    # التحقق من التوكن
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    id_token = authorization.replace("Bearer ", "")
    user_data = verify_firebase_token(id_token)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    user_id = user_data["user_id"]
    
    try:
        # جلب محادثات المستخدم
        chats_ref = db.collection('chats')
        query = chats_ref.where('user_id', '==', user_id).order_by('created_at', direction=firestore.Query.DESCENDING).limit(limit)
        results = query.get()
        
        chats = []
        for doc in results:
            chat_data = doc.to_dict()
            # تحويل Timestamp إلى string
            if 'created_at' in chat_data:
                chat_data['created_at'] = chat_data['created_at'].isoformat() if hasattr(chat_data['created_at'], 'isoformat') else str(chat_data['created_at'])
            
            chats.append({
                "id": doc.id,
                "user_message": chat_data.get('message_text', ''),
                "ai_response": chat_data.get('ai_response', ''),
                "timestamp": chat_data.get('created_at', '')
            })
        
        return {
            "success": True,
            "user_id": user_id,
            "chats": chats,
            "total": len(chats)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching chats: {str(e)}")

@app.delete("/chat/{chat_id}")
async def delete_chat(
    chat_id: str,
    authorization: str = Header(..., description="Firebase ID Token in format: Bearer <token>")
):
    """
    حذف محادثة محددة
    """
    # التحقق من التوكن
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization format")
    
    id_token = authorization.replace("Bearer ", "")
    user_data = verify_firebase_token(id_token)
    
    if not user_data:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    try:
        # التحقق أن المحادثة تخص المستخدم
        chat_doc = db.collection('chats').document(chat_id).get()
        if not chat_doc.exists:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        if chat_doc.to_dict().get('user_id') != user_data["user_id"]:
            raise HTTPException(status_code=403, detail="Not authorized to delete this chat")
        
        # حذف المحادثة
        db.collection('chats').document(chat_id).delete()
        
        return {
            "success": True,
            "message": "Chat deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting chat: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "AI Chat API",
        "timestamp": firestore.SERVER_TIMESTAMP
    }
