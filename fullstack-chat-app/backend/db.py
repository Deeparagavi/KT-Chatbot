\
import os
from sqlalchemy import create_engine, Table, Column, Integer, String, Text, MetaData
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql import select
from dotenv import load_dotenv
load_dotenv()

DB_BACKEND = os.getenv("DB_BACKEND","sqlite")
SQLITE_PATH = os.getenv("SQLITE_PATH","./chatbot.db")
AZURE_SQL_CONN_STRING = os.getenv("AZURE_SQL_CONN_STRING","")

if DB_BACKEND == "azure" and AZURE_SQL_CONN_STRING:
    DB_URL = AZURE_SQL_CONN_STRING
else:
    DB_URL = f"sqlite:///{SQLITE_PATH}"

engine = create_engine(DB_URL, echo=False, future=True)
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

def init_db():
    meta.create_all(engine)

def create_user(username, password_hash):
    ins = users.insert().values(username=username, password_hash=password_hash)
    try:
        with engine.begin() as conn:
            conn.execute(ins)
        return {"message":"user created"}
    except IntegrityError:
        return {"error":"username exists"}

def authenticate_user(username, password_plain):
    sel = select(users).where(users.c.username == username)
    with engine.connect() as conn:
        row = conn.execute(sel).first()
    if not row:
        return False
    # Note: in app.py we use bcrypt to check password properly; this is a simple placeholder
    return True if row else False

def add_chat_history(user, role, content, meta=None):
    ins = messages.insert().values(user=user, role=role, content=content, meta=(meta or ""))
    with engine.begin() as conn:
        conn.execute(ins)

def get_user_history(user):
    sel = select(messages).where(messages.c.user == user).order_by(messages.c.id)
    with engine.connect() as conn:
        rows = conn.execute(sel).fetchall()
    return [{"role": r.role, "content": r.content, "meta": r.meta} for r in rows]
