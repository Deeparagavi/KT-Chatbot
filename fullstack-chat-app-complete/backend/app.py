# app.py
import os
import time
import json
from pathlib import Path
from dotenv import load_dotenv
from flask import Flask, request, jsonify, send_from_directory, Response, render_template
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, Table, Column, Integer, String, Text, MetaData
from sqlalchemy.exc import IntegrityError
import bcrypt
from rag_store import store as rag_store
from agents import MasterOrchestrator
import fitz  # PyMuPDF
from pathlib import Path
# Optional OpenAI
try:
    import openai
except Exception:
    openai = None

load_dotenv()

UPLOAD_FOLDER = Path(os.getenv('UPLOAD_FOLDER', './uploads'))
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
DB_PATH = os.getenv('DB_PATH', './chat_app.db')
JWT_SECRET = os.getenv('JWT_SECRET', 'jwt-secret')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
STORAGE_BACKEND = os.getenv('STORAGE_BACKEND', 'local')
AZURE_BLOB_CONNECTION_STRING = os.getenv('AZURE_BLOB_CONNECTION_STRING')
AZURE_BLOB_CONTAINER = os.getenv('AZURE_BLOB_CONTAINER')

# Azure blob optional
azure_blob_client = None
if STORAGE_BACKEND == 'azure_blob' and AZURE_BLOB_CONNECTION_STRING and AZURE_BLOB_CONTAINER:
    try:
        from azure.storage.blob import BlobServiceClient
        azure_blob_client = BlobServiceClient.from_connection_string(AZURE_BLOB_CONNECTION_STRING)
    except Exception:
        azure_blob_client = None

app = Flask(__name__, template_folder='../frontend/templates')
CORS(app)
app.config['JWT_SECRET_KEY'] = JWT_SECRET
jwt = JWTManager(app)

# Database
engine = create_engine(f'sqlite:///{DB_PATH}', echo=False, future=True)
meta = MetaData()

users = Table('users', meta,
    Column('id', Integer, primary_key=True),
    Column('username', String(150), unique=True, nullable=False),
    Column('password_hash', String(200), nullable=False)
)

messages = Table('messages', meta,
    Column('id', Integer, primary_key=True),
    Column('user', String(150), nullable=False),
    Column('role', String(20), nullable=False),
    Column('content', Text, nullable=False),
    Column('meta', Text, nullable=True)
)
meta.create_all(engine)

# Orchestrator
orch = MasterOrchestrator(multi_agent=(os.getenv('MULTI_AGENT','false').lower()=='true'))

# OpenAI config
if openai and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

# helpers
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), password_hash.encode())

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({'msg': 'username and password required'}), 400
    ph = hash_password(password)
    ins = users.insert().values(username=username, password_hash=ph)
    try:
        with engine.begin() as conn:
            conn.execute(ins)
    except IntegrityError:
        return jsonify({'msg': 'username already exists'}), 400
    return jsonify({'msg': 'registered'}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.json or {}
    username = data.get('username')
    password = data.get('password')
    sel = users.select().where(users.c.username == username)
    with engine.connect() as conn:
        row = conn.execute(sel).first()
    if not row or not check_password(password, row.password_hash):
        return jsonify({'msg': 'invalid credentials'}), 401
    token = create_access_token(identity=username)
    return jsonify({'access_token': token})

@app.route('/upload', methods=['POST'])
@jwt_required()
def upload():
    if 'file' not in request.files:
        return jsonify({'msg': 'no file part'}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({'msg': 'no selected file'}), 400
    filename = secure_filename(f.filename)

    if STORAGE_BACKEND == 'azure_blob' and azure_blob_client:
        container_client = azure_blob_client.get_container_client(AZURE_BLOB_CONTAINER)
        blob_name = filename
        try:
            container_client.create_container()
        except Exception:
            pass
        file_bytes = f.read()
        container_client.upload_blob(name=blob_name, data=file_bytes, overwrite=True)
        blob_url = f"https://{azure_blob_client.account_name}.blob.core.windows.net/{AZURE_BLOB_CONTAINER}/{blob_name}"
        rag_store.add_documents([(f"[image-blob]\\nURL:{blob_url}", {'filename': filename, 'type': 'image', 'url': blob_url})])
        return jsonify({'filename': filename, 'url': blob_url})
    else:
        dest = UPLOAD_FOLDER / filename
        f.save(dest)
        rag_store.add_documents([(f"[image-file]\\nPath:{str(dest)}", {'filename': filename, 'type': 'image', 'path': str(dest)})])
        return jsonify({'filename': filename, 'url': f"/uploads/{filename}"})

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(str(UPLOAD_FOLDER), filename)

@app.route('/history', methods=['GET'])
@jwt_required()
def history():
    username = get_jwt_identity()
    sel = messages.select().where(messages.c.user == username).order_by(messages.c.id)
    with engine.connect() as conn:
        rows = conn.execute(sel).fetchall()
    out = [{'role': r.role, 'content': r.content, 'meta': r.meta} for r in rows]
    return jsonify(out)

def generate_assistant_stream_openai(prompt: str):
    if not openai:
        yield json.dumps({'chunk': '[openai library not installed]'})
        return
    if not OPENAI_API_KEY:
        yield json.dumps({'chunk': '[OPENAI_API_KEY not set]'})
        return
    try:
        print("right path")
        response = openai.chat.completions.create(model=OPENAI_MODEL, messages=[{'role':'user','content':prompt}], stream=True)
        print(response)
        for event in response:
            print(event)
            for chunk in response:
                # chunk.choices is a list; usually one element
                delta = chunk.choices[0].delta  # this is a ChoiceDelta object
                if hasattr(delta, 'content') and delta.content:
                    print(delta.content, end='')
                    yield delta.content
    except Exception as e:
        print("rerrer: {}".format(e))
        yield json.dumps({'chunk': f'[openai error] {str(e)}'})

@app.route('/chat', methods=['POST'])
@jwt_required()
def chat():
    data = request.json or {}
    text = data.get('text', '')
    username = get_jwt_identity()
    images = data.get('images', [])
    ins = messages.insert().values(user=username, role='user', content=text, meta=json.dumps({'images': images}))
    with engine.begin() as conn:
        conn.execute(ins)

    retrieved = rag_store.search(text, k=4)
    print("retrieved {}".format(retrieved))
    context_texts = '\\n\\n'.join([r['text'] for r in retrieved])
    prompt_with_context = f"Context:\\n{context_texts}\\n\\nUser: {text}\\nAssistant:"
    print("RAG : {}".format(prompt_with_context))
    def event_stream():
        if OPENAI_API_KEY and openai:
            print("openai")
            for chunk in generate_assistant_stream_openai(prompt_with_context):
                # chunk might be raw text or json string
                # print("chunk: {}".format(chunk))
                if isinstance(chunk, str) and chunk.startswith('{') and 'chunk' in chunk:
                    try:
                        payload = json.loads(chunk)
                        print(payload)
                        yield f"data: {json.dumps({'role':'assistant','chunk': payload.get('chunk')})}\\n\\n"
                    except Exception as e:
                        print(chunk)
                        print("error {}".format(e))
                        yield f"data: {json.dumps({'role':'assistant','chunk': chunk})}\\n\\n"
                else:
                    # print("elseop {}".format(chunk))
                    yield f"data: {json.dumps({'role':'assistant','chunk': chunk})}\\n\\n"
        else:
            print("else")
            simulated = [
                "Processing your question...",
                "I looked through related documents and images.",
                "Top result: {}".format(retrieved[0]['meta'].get('filename','n/a')) if retrieved else "No relevant docs found.",
                "Answer: Here's a helpful summary based on available data."
            ]
            for s in simulated:
                time.sleep(0.5)
                print("p:{}".format(s))
                yield f"data: {json.dumps({'role':'assistant','chunk': s})}\\n\\n"
        ins2 = messages.insert().values(user=username, role='assistant', content='[assistant response saved]', meta=json.dumps({'retrieved': retrieved}))
        with engine.begin() as conn:
            conn.execute(ins2)
        print("l no resp")
        yield 'event: done\\ndata: {}\\n\\n'

    return Response(event_stream(), mimetype='text/event-stream')

@app.route('/search', methods=['GET'])
@jwt_required()
def search():
    q = request.args.get('q', '')
    k = int(request.args.get('k', 5))
    results = rag_store.search(q, k=k)
    return jsonify(results)

if __name__ == '__main__':
    app.run(host=os.getenv('FLASK_HOST', '0.0.0.0'), port=int(os.getenv('FLASK_PORT', 5000)), debug=True)
