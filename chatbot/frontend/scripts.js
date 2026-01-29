const API_BASE = window.location.origin.includes("localhost") ? "http://127.0.0.1:8000" : window.location.origin;
const chatDiv = document.getElementById("chat");

document.getElementById("send").onclick = async () => {
    const q = document.getElementById("query").value;
    const evtSource = new EventSource(`${API_BASE}/chat?query=${encodeURIComponent(q)}`);
    evtSource.onmessage = (e) => {
        const msg = document.createElement("div");
        msg.textContent = e.data;
        chatDiv.appendChild(msg);
        chatDiv.scrollTop = chatDiv.scrollHeight;
    };
};

document.getElementById("uploadBtn").onclick = async () => {
    const file = document.getElementById("fileUpload").files[0];
    const form = new FormData();
    form.append("file", file);
    await fetch(`${API_BASE}/upload`, {method:"POST", body: form});
};
