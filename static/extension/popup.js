

const API_BASE = "http://localhost:8000";

const $ = (sel) => document.querySelector(sel);
const app = $("#app");
const chatContainer = $("#chat-container");
const messagesDiv = $("#messages");
const welcomeScreen = $("#welcome-screen");
const messageInput = $("#message-input");
const sendBtn = $("#btn-send");
const clearBtn = $("#btn-clear");
const agentsBtn = $("#btn-agents");
const agentPanel = $("#agent-panel");
const agentList = $("#agent-list");
const closeAgentsBtn = $("#btn-close-agents");
const statusDot = $("#status-dot");
const statusBar = $("#status-bar");
const statusText = $("#status-text");
const quickActions = $("#quick-actions");

let isProcessing = false;

document.addEventListener("DOMContentLoaded", () => {
    checkConnection();
    setupEventListeners();
    setInterval(checkConnection, 30000);
});

function setupEventListeners() {
    messageInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendBtn.addEventListener("click", sendMessage);
    clearBtn.addEventListener("click", clearChat);
    agentsBtn.addEventListener("click", toggleAgentPanel);
    closeAgentsBtn.addEventListener("click", () => agentPanel.classList.remove("visible"));

    messageInput.addEventListener("input", () => {
        messageInput.style.height = "auto";
        messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + "px";
    });

    quickActions.addEventListener("click", (e) => {
        const btn = e.target.closest(".quick-btn");
        if (btn) {
            messageInput.value = btn.dataset.msg;
            sendMessage();
        }
    });
}

async function checkConnection() {
    try {
        const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(3000) });
        if (res.ok) {
            const data = await res.json();
            statusDot.classList.add("connected");
            statusDot.classList.remove("loading");
            statusDot.title = `Connected - ${data.agents_registered} agents`;
            setStatus("ready", `Connected - ${data.agents_registered} agents - ${data.model}`);
            return true;
        }
    } catch (e) {
    }
    statusDot.classList.remove("connected", "loading");
    statusDot.title = "Disconnected - start server with: uvicorn main:app";
    setStatus("error", "Server offline - run: uvicorn main:app --reload");
    return false;
}

const USE_STREAMING = true;

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text || isProcessing) return;

    isProcessing = true;
    sendBtn.disabled = true;

    welcomeScreen.classList.add("hidden");

    addMessage("user", text);
    messageInput.value = "";
    messageInput.style.height = "auto";

    if (USE_STREAMING) {
        await sendMessageStreaming(text);
    } else {
        await sendMessageStandard(text);
    }

    statusDot.classList.remove("loading");
    isProcessing = false;
    sendBtn.disabled = false;
    messageInput.focus();
}

async function sendMessageStreaming(text) {
    const msgDiv = createAssistantPlaceholder();
    const contentEl = msgDiv.querySelector(".message-content");
    let fullText = "";
    let delegations = [];

    setStatus("active", "AI is thinking...");
    statusDot.classList.add("loading");

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, stream: true }),
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Server error" }));
            contentEl.innerHTML = renderMarkdown(` **Error ${res.status}:** ${err.detail || "Unknown error"}`);
            setStatus("error", `Error ${res.status}`);
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";

            for (const line of lines) {
                if (!line.startsWith("data: ")) continue;
                const payload = line.slice(6).trim();
                if (payload === "[DONE]") continue;

                try {
                    const event = JSON.parse(payload);

                    switch (event.type) {
                        case "token":
                            fullText += event.content;
                            contentEl.innerHTML = renderMarkdown(fullText);
                            scrollToBottom();
                            setStatus("active", "Streaming response...");
                            break;

                        case "delegation_start":
                            setStatus("active", `Executing ${event.count} agent task(s)...`);
                            break;

                        case "delegation_result":
                            delegations.push(event.result);
                            break;

                        case "done":
                            if (event.conversation_text) {
                                contentEl.innerHTML = renderMarkdown(event.conversation_text);
                            }
                            delegations = event.delegations || delegations;
                            break;

                        case "error":
                            fullText += `\n\n ${event.content}`;
                            contentEl.innerHTML = renderMarkdown(fullText);
                            break;
                    }
                } catch (e) {
                }
            }
        }

        if (delegations.length > 0) {
            appendDelegationBadges(contentEl, delegations);
            const successCount = delegations.filter((d) => d.success).length;
            setStatus(
                successCount === delegations.length ? "success" : "error",
                `${successCount}/${delegations.length} agent tasks completed`
            );
        } else {
            setStatus("ready", "Ready");
        }
    } catch (err) {
        contentEl.innerHTML = renderMarkdown(
            " **Connection failed.** Make sure the server is running:\n\n```bash\nuvicorn main:app --reload\n```"
        );
        setStatus("error", "Connection failed");
    }
}

async function sendMessageStandard(text) {
    const thinkingEl = addThinkingIndicator();
    setStatus("active", "AI is thinking...");
    statusDot.classList.add("loading");

    try {
        const res = await fetch(`${API_BASE}/api/chat`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ message: text, stream: false }),
        });

        thinkingEl.remove();

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Server error" }));
            addMessage("assistant", ` **Error ${res.status}:** ${err.detail || "Unknown error"}`);
            setStatus("error", `Error ${res.status}`);
        } else {
            const data = await res.json();
            addMessage("assistant", data.conversation_text, data.delegations_executed);

            if (data.delegations_executed?.length > 0) {
                const successCount = data.delegations_executed.filter((d) => d.success).length;
                const total = data.delegations_executed.length;
                setStatus(
                    successCount === total ? "success" : "error",
                    `${successCount}/${total} agent tasks completed`
                );
            } else {
                setStatus("ready", "Ready");
            }
        }
    } catch (err) {
        thinkingEl.remove();
        addMessage(
            "assistant",
            " **Connection failed.** Make sure the server is running:\n\n```bash\nuvicorn main:app --reload\n```"
        );
        setStatus("error", "Connection failed");
    }
}

function createAssistantPlaceholder() {
    const div = document.createElement("div");
    div.className = "message assistant";

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = "";

    const content = document.createElement("div");
    content.className = "message-content";
    content.innerHTML = '<div class="thinking"><div class="thinking-dot"></div><div class="thinking-dot"></div><div class="thinking-dot"></div></div>';

    div.appendChild(avatar);
    div.appendChild(content);
    messagesDiv.appendChild(div);
    scrollToBottom();
    return div;
}

function appendDelegationBadges(contentEl, delegations) {
    const badgeContainer = document.createElement("div");
    badgeContainer.style.marginTop = "8px";
    for (const d of delegations) {
        const badge = document.createElement("span");
        badge.className = `delegation-badge ${d.success ? "success" : "error"}`;
        badge.textContent = `${d.success ? "" : ""} ${d.agent}.${d.action}`;
        badge.title = d.success
            ? JSON.stringify(d.data, null, 2)
            : d.error || "Unknown error";
        badgeContainer.appendChild(badge);
    }
    contentEl.appendChild(badgeContainer);
}

async function clearChat() {
    try {
        await fetch(`${API_BASE}/api/chat/clear`, { method: "POST" });
    } catch (e) {
    }
    messagesDiv.innerHTML = "";
    welcomeScreen.classList.remove("hidden");
    setStatus("ready", "Chat cleared");
}

async function toggleAgentPanel() {
    const isVisible = agentPanel.classList.toggle("visible");
    if (isVisible) {
        await loadAgents();
    }
}

async function loadAgents() {
    agentList.innerHTML = '<div class="agent-loading">Loading agents...</div>';
    try {
        const res = await fetch(`${API_BASE}/api/agents`);
        const data = await res.json();

        let html = "";
        for (const [name, info] of Object.entries(data.agents)) {
            const actions = (info.actions || [])
                .map((a) => `<span class="action-tag" data-agent="${name}" data-action="${a}">${a}</span>`)
                .join("");
            html += `
                <div class="agent-card">
                    <div class="agent-card-name">${name}</div>
                    <div class="agent-card-actions">${actions}</div>
                </div>`;
        }
        agentList.innerHTML = html || '<div class="agent-loading">No agents registered</div>';

        agentList.querySelectorAll(".action-tag").forEach((tag) => {
            tag.addEventListener("click", () => {
                const agent = tag.dataset.agent;
                const action = tag.dataset.action;
                messageInput.value = `Execute ${agent} -> ${action}`;
                agentPanel.classList.remove("visible");
                messageInput.focus();
            });
        });
    } catch (e) {
        agentList.innerHTML = '<div class="agent-loading"> Could not reach server</div>';
    }
}

function addMessage(role, text, delegations = []) {
    const div = document.createElement("div");
    div.className = `message ${role}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "" : "";

    const content = document.createElement("div");
    content.className = "message-content";
    content.innerHTML = renderMarkdown(text);

    if (delegations.length > 0) {
        const badgeContainer = document.createElement("div");
        badgeContainer.style.marginTop = "8px";
        for (const d of delegations) {
            const badge = document.createElement("span");
            badge.className = `delegation-badge ${d.success ? "success" : "error"}`;
            badge.textContent = `${d.success ? "" : ""} ${d.agent}.${d.action}`;
            badge.title = d.success
                ? JSON.stringify(d.data, null, 2)
                : d.error || "Unknown error";
            badgeContainer.appendChild(badge);
        }
        content.appendChild(badgeContainer);
    }

    div.appendChild(avatar);
    div.appendChild(content);
    messagesDiv.appendChild(div);
    scrollToBottom();
}

function addThinkingIndicator() {
    const div = document.createElement("div");
    div.className = "message assistant";
    div.innerHTML = `
        <div class="message-avatar"></div>
        <div class="message-content">
            <div class="thinking">
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
                <div class="thinking-dot"></div>
            </div>
        </div>`;
    messagesDiv.appendChild(div);
    scrollToBottom();
    return div;
}

function scrollToBottom() {
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function renderMarkdown(text) {
    if (!text) return "";

    let html = escapeHtml(text);

    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code class="language-${lang || "text"}">${code.trim()}</code></pre>`;
    });

    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

    html = html.replace(/^---$/gm, "<hr>");

    html = html.replace(/^[\-\*] (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>[\s\S]*?<\/li>)/g, "<ul>$1</ul>");
    html = html.replace(/<\/ul>\s*<ul>/g, "");

    html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

    html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    html = html.replace(/\n\n/g, "</p><p>");
    html = html.replace(/\n/g, "<br>");

    if (!html.startsWith("<")) {
        html = `<p>${html}</p>`;
    }

    return html;
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

function setStatus(type, text) {
    statusBar.className = `status-bar ${type}`;
    statusText.textContent = text;
}
