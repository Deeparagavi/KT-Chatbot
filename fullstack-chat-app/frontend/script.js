const API_BASE = window.location.port === "5500"
  ? "http://127.0.0.1:8000"
  : window.location.origin;
let token = localStorage.getItem("jwt_token");
const authDiv = document.getElementById("auth");
const chatDiv = document.getElementById("chat");
const chatUI = document.getElementById("chatUI");

if(token){
    authDiv.style.display = "none";
    chatUI.style.display = "block";
    loadHistory();
}

document.getElementById("loginBtn").onclick = async () => { await authenticate('/login'); };
document.getElementById("registerBtn").onclick = async () => { await authenticate('/register'); };

async function authenticate(endpoint){
    const username = document.getElementById("username").value;
    const password = document.getElementById("password").value;
    const res = await fetch(`${API_BASE}${endpoint}`, {
        method:"POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({username,password})
    });
    const data = await res.json();
    if(endpoint==="/login" && data.access_token){
        token = data.access_token;
        localStorage.setItem("jwt_token", token);
        authDiv.style.display="none";
        chatUI.style.display="block";
        loadHistory();
    } else if(endpoint==="/register"){
        alert(JSON.stringify(data));
    } else {
        alert(JSON.stringify(data));
    }
}

document.getElementById("logoutBtn").onclick = () => {
    token = null; localStorage.removeItem("jwt_token"); authDiv.style.display = "block"; chatUI.style.display = "none";
}

document.getElementById("send").onclick = async () => {
    const q = document.getElementById("query").value;
    appendMessage(q,"user"); document.getElementById("query").value="";
    const res = await fetch(`${API_BASE}/chat`, {
        method:"POST",
        headers: {"Content-Type":"application/json","Authorization": `Bearer ${token}`},
        body: JSON.stringify({query: q})
    });
    const reader = res.body.getReader(); const decoder = new TextDecoder(); let botMessage = "";
    while(true){ const {done, value} = await reader.read(); if(done) break; botMessage += decoder.decode(value); renderBotTyping(botMessage); }
    console.log("text reply")
    console.log(botMessage)
    finalizeBotMessage(botMessage, "Text Agent");
}

document.getElementById("uploadBtn").onclick = async () => {
    const file = document.getElementById("fileUpload").files[0]; if(!file) return alert("Select a file");
    const form = new FormData(); form.append("file", file);
    const res = await fetch(`${API_BASE}/upload`, { method:"POST", headers: { "Authorization": `Bearer ${token}` }, body: form });
    const data = await res.json(); alert(JSON.stringify(data)); if(file.type.startsWith("image/")){ appendUploadedImage(file); } else { appendUploadedFile(file); }
}

async function loadHistory(){ const res = await fetch(`${API_BASE}/history`, { headers: { "Authorization": `Bearer ${token}` } }); const data = await res.json(); data.forEach(msg => { appendMessage(msg.content, msg.role === 'assistant' ? 'bot' : 'user'); }); }

function appendMessage(text,cls,agent=""){ const container = document.createElement("div"); container.className = `message ${cls}`; if(agent){ const label = document.createElement("div"); label.className = "agent-label"; label.textContent = agent; container.appendChild(label); } const content = document.createElement("div"); content.textContent = text; container.appendChild(content); chatDiv.appendChild(container); chatDiv.scrollTop = chatDiv.scrollHeight; }
function renderBotTyping(text){ let last = chatDiv.querySelector(".bot:last-child div:last-child"); if(last){ last.textContent = text; } else { appendMessage(text,"bot","Text Agent"); } chatDiv.scrollTop = chatDiv.scrollHeight; }
function finalizeBotMessage(text, agent="Text Agent"){ renderBotTyping(text); }
function appendUploadedImage(file){ const div = document.createElement("div"); div.className = "message user"; const img = document.createElement("img"); img.src = URL.createObjectURL(file); img.className = "uploaded"; div.appendChild(img); chatDiv.appendChild(div); chatDiv.scrollTop = chatDiv.scrollHeight; }
function appendUploadedFile(file){ const div = document.createElement("div"); div.className = "message user"; const link = document.createElement("span"); link.className = "file-link"; link.textContent = file.name; div.appendChild(link); chatDiv.appendChild(div); chatDiv.scrollTop = chatDiv.scrollHeight; }
