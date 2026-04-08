const state = {
  threadId: null,
  companionName: "昔涟",
  pollingHandle: null,
};

const elements = {
  chatTitle: document.getElementById("chat-title"),
  companionStatus: document.getElementById("companion-status"),
  messages: document.getElementById("messages"),
  notice: document.getElementById("notice"),
  composer: document.getElementById("composer"),
  input: document.getElementById("message-input"),
  sendButton: document.getElementById("send-button"),
  refreshButton: document.getElementById("refresh-button"),
  template: document.getElementById("message-template"),
};

document.addEventListener("DOMContentLoaded", () => {
  bindEvents();
  bootstrap();
  state.pollingHandle = window.setInterval(refreshMessages, 4000);
});

function bindEvents() {
  elements.composer.addEventListener("submit", handleSubmit);
  elements.refreshButton.addEventListener("click", refreshMessages);
  elements.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      elements.composer.requestSubmit();
    }
  });
}

async function bootstrap() {
  setStatus("正在把你的信号递向翁法罗斯…");
  setBusy(true);
  try {
    const payload = await requestJson("/api/bootstrap");
    applyPayload(payload);
    clearNotice();
  } catch (error) {
    showNotice("连接失败了，请稍后再试一次。");
    setStatus("通信暂时中断。");
  } finally {
    setBusy(false);
  }
}

async function refreshMessages() {
  if (!state.threadId) {
    return;
  }

  try {
    const payload = await requestJson(
      `/api/messages?thread_id=${encodeURIComponent(state.threadId)}&limit=200`,
    );
    applyPayload(payload);
  } catch (error) {
    showNotice("刷新消息失败了，不过聊天记录还在。");
  }
}

async function handleSubmit(event) {
  event.preventDefault();
  const content = elements.input.value.trim();
  if (!content || !state.threadId) {
    return;
  }

  setBusy(true);
  setStatus("消息已经送达手机，等待昔涟主动查看。");

  try {
    const payload = await requestJson("/api/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        thread_id: state.threadId,
        content,
      }),
    });

    elements.input.value = "";
    applyPayload(payload);
    clearNotice();
  } catch (error) {
    showNotice("发送失败了，这句话还没有写进她的手机。");
    setStatus("消息发送失败。");
  } finally {
    setBusy(false);
  }
}

function applyPayload(payload) {
  state.threadId = payload.thread.thread_id;
  state.companionName = payload.companion.display_name || "昔涟";

  elements.chatTitle.textContent = state.companionName;
  setStatus(buildStatusText(payload));
  renderMessages(payload.messages || []);
}

function buildStatusText(payload) {
  const messages = payload.messages || [];
  if (messages.length === 0) {
    return `${state.companionName}正在等你开口。`;
  }

  const lastMessage = messages[messages.length - 1];
  if (lastMessage.sender === "user") {
    return `你刚刚发来一条消息，时间 ${formatTime(lastMessage.created_at)}。等待${state.companionName}主动查看。`;
  }
  return `最近一条来自${state.companionName}，时间 ${formatTime(lastMessage.created_at)}。`;
}

function renderMessages(messages) {
  elements.messages.innerHTML = "";

  if (!messages.length) {
    const empty = document.createElement("div");
    empty.className = "messages__empty";
    empty.textContent = "聊天记录会在这里慢慢堆积。你可以先发一句话，让这条通信线真正亮起来。";
    elements.messages.appendChild(empty);
    return;
  }

  for (const message of messages) {
    const node = elements.template.content.firstElementChild.cloneNode(true);
    const bubble = node.querySelector(".message__bubble");
    const meta = node.querySelector(".message__meta");
    const senderName = message.sender === "user" ? "你" : state.companionName;

    node.classList.add(message.sender === "user" ? "message--user" : "message--companion");
    bubble.textContent = message.content;
    meta.textContent = `${senderName} · ${formatTime(message.created_at)}`;
    elements.messages.appendChild(node);
  }

  elements.messages.scrollTop = elements.messages.scrollHeight;
}

function setBusy(isBusy) {
  elements.input.disabled = isBusy;
  elements.sendButton.disabled = isBusy;
  elements.refreshButton.disabled = isBusy;
}

function setStatus(text) {
  elements.companionStatus.textContent = text;
}

function showNotice(text) {
  elements.notice.hidden = false;
  elements.notice.textContent = text;
}

function clearNotice() {
  elements.notice.hidden = true;
  elements.notice.textContent = "";
}

function formatTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "未知时间";
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  return response.json();
}
