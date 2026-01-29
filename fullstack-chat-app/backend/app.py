import os, time, json, uuid
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi_jwt_auth import AuthJWT
from pydantic import BaseModel
from dotenv import load_dotenv
import bcrypt, fitz
load_dotenv()
from storage_manager import StorageManager
from rag_engine import RAGStore
from agents import TextAgent, ImageAgent, ConfluenceAgent, MasterAgent
from db import init_db, create_user, authenticate_user, add_chat_history, get_user_history



HOST = os.getenv("HOST","0.0.0.0")
PORT = int(os.getenv("PORT","8000"))
UPLOAD_FOLDER = Path(os.getenv("UPLOAD_FOLDER","./uploads"))
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Fullstack Chat App")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

storage = StorageManager()
rag = RAGStore()
text_agent = TextAgent()
img_agent = ImageAgent()
conf_agent = ConfluenceAgent()
master = MasterAgent([text_agent, img_agent, conf_agent])
init_db()

class Settings(BaseModel):
    authjwt_secret_key: str = os.getenv("JWT_SECRET_KEY", "supersecret")

@AuthJWT.load_config
def get_config():
    return Settings()

class RegisterModel(BaseModel):
    username: str
    password: str

class LoginModel(BaseModel):
    username: str
    password: str

@app.post("/register")
def register(data: RegisterModel):
    ph = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    return create_user(data.username, ph)

@app.post("/login")
def login(data: LoginModel, Authorize: AuthJWT = Depends()):
    sel = authenticate_user(data.username, data.password)
    if not sel:
        raise HTTPException(status_code=401, detail="invalid credentials")
    access_token = Authorize.create_access_token(subject=data.username)
    return {"access_token": access_token}

@app.post("/upload")
def upload(file: UploadFile = File(...), Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    username = Authorize.get_jwt_subject()
    filename = f"{uuid.uuid4()}_{file.filename}"
    dest = UPLOAD_FOLDER / filename
    with open(dest, "wb") as f:
        f.write(file.file.read())
    url = storage.save_file(dest)
    text_content = ""
    if file.filename.lower().endswith(".pdf"):
        try:
            doc = fitz.open(dest)
            txt = ""
            for p in doc:
                txt += p.get_text("text") + "\\n"
            doc.close()
            text_content = txt
        except Exception as e:
            text_content = f"[pdf error] {e}"
    elif file.filename.lower().endswith((".png",".jpg",".jpeg")):
        ocr = img_agent.analyze_image(str(dest))
        text_content = ocr.get("text","")
    else:
        try:
            text_content = dest.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text_content = "[binary file stored]"
    rag.add_documents([(text_content, {"filename": file.filename, "path": str(dest)})])
    return {"filename": file.filename, "url": url}

@app.post("/chat")
async def chat(request: Request, Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    username = Authorize.get_jwt_subject()
    body = await request.json()
    query = body.get("query","")
    retrieved = rag.search(query, k=5)
    context = "\\n\\n".join([r["text"] for r in retrieved])
    prompt = f"Context:\\n{context}\\n\\nUser: {query}\\nAssistant:"
    def gen_stream_from_text(text):
        for token in text.split():
            yield f"data: {json.dumps({'role':'assistant','chunk': token + ' '})}\\n\\n"
            time.sleep(0.02)
        yield "event: done\\ndata: {}\\n\\n"
    if os.getenv("OPENAI_API_KEY"):
        try:
            full = text_agent.generate(query, context)
            add_chat_history(username, "assistant", full, json.dumps({"retrieved": retrieved}))
            print("Answer : {}".format(full))
            return StreamingResponse(gen_stream_from_text(full), media_type="text/event-stream")
        except Exception as e:
            full = text_agent.generate(query, context)
            add_chat_history(username, "assistant", full, json.dumps({"error": str(e)}))
            print("Answer2 : {}".format(full))
            return StreamingResponse(gen_stream_from_text(full), media_type="text/event-stream")
    else:
        full = text_agent.generate(query, context)
        add_chat_history(username, "assistant", full, json.dumps({"retrieved": retrieved}))
        print("Answer3 : {}".format(full))
        return StreamingResponse(gen_stream_from_text(full), media_type="text/event-stream")

@app.get("/history")
def history(Authorize: AuthJWT = Depends()):
    Authorize.jwt_required()
    username = Authorize.get_jwt_subject()
    return get_user_history(username)

@app.get("/uploads/{filename}")
def serve_upload(filename: str):
    p = UPLOAD_FOLDER / filename
    if p.exists():
        return FileResponse(str(p))
    return JSONResponse({"error":"not found"}, status_code=404)

@app.get("/", response_class=HTMLResponse)
def root():
    return HTMLResponse(content="<h2>Fullstack Chat App backend running</h2>", status_code=200)
