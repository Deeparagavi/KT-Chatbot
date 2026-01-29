import sqlite3
DB = "chatbot.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS users(username TEXT PRIMARY KEY, password TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS history(user TEXT, query TEXT, response TEXT)")
    conn.commit()
    conn.close()

def create_user(username,password):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO users(username,password) VALUES (?,?)",(username,password))
    conn.commit()
    conn.close()
    return {"message":"User created"}

def authenticate_user(username,password):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username=?",(username,))
    row = c.fetchone()
    conn.close()
    if row:
        return password == row[0]
    return False

def add_chat_history(user,query,response):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("INSERT INTO history(user,query,response) VALUES (?,?,?)",(user,query,response))
    conn.commit()
    conn.close()

def get_user_history(user):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT query,response FROM history WHERE user=?",(user,))
    rows = c.fetchall()
    conn.close()
    return [{"query":q,"response":r} for q,r in rows]
