import os, uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Depends
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel
import bcrypt, fitz, pytesseract

from storage_manager import StorageManager
from rag_engine import RAGStore
from agents import TextAgent, ImageAgent, ConfluenceAgent, MasterAgent
from db import init_db, create_user, authenticate_user, get_user_history, add_chat_history

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND","local")
UPLOAD_FOLDER = Path("./uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True, parents=True)

app = FastAPI(title="Fullstack ChatBot")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

storage = StorageManager(STORAGE_BACKEND)
rag_store = RAGStore()
text_agent = TextAgent()
img_agent = ImageAgent()
conf_agent = ConfluenceAgent()
master_agent = MasterAgent([text_agent,img_agent,conf_agent])
init_db()

class Settings(BaseModel):
    authjwt_secret_key: str = os.getenv("JWT_SECRET_KEY","supersecret")

@AuthJWT.load_config
def get_config():
    return Settings()

class UserCreds(BaseModel):
    username: str
    password: str

class Query(BaseModel):
    query: str

@app.post("/register")
def register(creds: UserCreds):
    hashed = bcrypt.hashpw(creds.password.encode(), bcrypt.gensalt()).decode()
    return create_user(creds.username, hashed)

@app.post("/login")
def login(creds: UserCreds, Authorize: AuthJWT=Depends()):
    user = authenticate_user(creds.username, creds.password)
    if not user:
        return JSONResponse({"error":"Invalid credentials"}, status_code=401)
    token = Authorize.create_access_token(subject=creds.username)
    return {"access_token": token}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), Authorize: AuthJWT=Depends()):
    Authorize.jwt_required()
    user = Authorize.get_jwt_subject()
    filename = f"{uuid.uuid4()}_{file.filename}"
    local_path = UPLOAD_FOLDER / filename
    with open(local_path, "wb") as f:
        f.write(await file.read())
    blob_path = storage.save_file(local_path)

    text_content = ""
    ext = Path(file.filename).suffix.lower()
    if ext == ".pdf":
        doc = fitz.open(local_path)
        pdf_text = ""
        for page in doc:
            pdf_text += page.get_text("text") + "\\n"
        doc.close()
        text_content = pdf_text
    elif ext in [".png",".jpg",".jpeg"]:
        ocr_text = pytesseract.image_to_string(str(local_path))
        text_content = ocr_text
    else:
        text_content = local_path.read_text(encoding="utf-8", errors="ignore")

    rag_store.add_documents([(text_content, {"user": user, "source": file.filename})])
    rag_store.save()
    return {"message":"File indexed", "path": str(blob_path)}

@app.post("/chat")
async def chat_endpoint(query: Query, Authorize: AuthJWT=Depends()):
    Authorize.jwt_required()
    user = Authorize.get_jwt_subject()
    results = rag_store.search(query.query, k=5)
    context = "\\n\\n".join([r["text"] for r in results])

    if os.getenv("MULTI_AGENT","false").lower()=="true":
        answer = master_agent.generate(query.query, context)
    else:
        answer = text_agent.generate(query.query, context)

    add_chat_history(user, query.query, answer)
    print("answer : {}".format(answer))
    async def stream():
        for word in answer.split():
            yield f"data: {word}\\n\\n"

    return StreamingResponse(stream(), media_type="text/event-stream")

@app.get("/history")
def history(Authorize: AuthJWT=Depends()):
    Authorize.jwt_required()
    user = Authorize.get_jwt_subject()
    return get_user_history(user)

@app.get("/uploads/{filename}")
def get_file(filename: str):
    path = UPLOAD_FOLDER / filename
    if path.exists():
        return FileResponse(str(path))
    return JSONResponse({"error":"file not found"}, status_code=404)

@app.get("/")
def home():
    return {"status":"running","storage":STORAGE_BACKEND}
