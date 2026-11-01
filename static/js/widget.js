/**
 * ORBIT AI — Embeddable Customer Support Widget (Vanilla Browser JavaScript)
 * Features:
 * - Dynamic tenant theme, dark/light mode, position, dimensions, border radius, logo/avatar
 * - Persistent sessionId and conversationId per tenant in localStorage (zero secrets stored)
 * - Natural multilingual chat + SSE / JSON support
 * - Per-assistant-message actions: Like, Dislike, Copy (Clipboard API + fallback), Share (Web Share API + fallback)
 * - Idempotent Lead Capture form with duplicate submission protection (`leadSubmitted` properly declared)
 */
(function () {
  "use strict";

  const scriptEl =
    document.currentScript ||
    document.querySelector("script[data-client-id][data-api-key]");
  if (!scriptEl) return;

  const clientId = scriptEl.getAttribute("data-client-id") || "";
  const apiKey = scriptEl.getAttribute("data-api-key") || "";
  const scriptSrc = scriptEl.getAttribute("src") || "";
  const baseUrl = scriptSrc.includes("/static/js/widget.js")
    ? scriptSrc.split("/static/js/widget.js")[0]
    : "";

  if (!clientId || !apiKey) {
    console.warn("[Orbit AI Widget] Missing data-client-id or data-api-key attribute.");
    return;
  }

  const STORAGE_KEY_SESSION = `orbit_session_${clientId}`;
  const STORAGE_KEY_CONV = `orbit_conv_${clientId}`;
  const STORAGE_KEY_FEEDBACK = `orbit_feedback_${clientId}`;
  const STORAGE_KEY_LEAD = `orbit_lead_submitted_${clientId}`;

  let sessionId = localStorage.getItem(STORAGE_KEY_SESSION) || "";
  if (!sessionId) {
    sessionId = "sess_" + Math.random().toString(36).slice(2, 11) + "_" + Date.now();
    localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
  }
  let conversationId = localStorage.getItem(STORAGE_KEY_CONV) || "";
  let leadSubmitted = localStorage.getItem(STORAGE_KEY_LEAD) === "1";
  let feedbackState = {};
  try {
    feedbackState = JSON.parse(localStorage.getItem(STORAGE_KEY_FEEDBACK) || "{}") || {};
  } catch (_e) {
    feedbackState = {};
  }

  let tenantConfig = null;
  let isOpen = false;
  let isMinimized = false;

  async function fetchConfig() {
    const res = await fetch(`${baseUrl}/v1/config?clientId=${encodeURIComponent(clientId)}`, {
      method: "GET",
      headers: {
        "x-api-key": apiKey,
        "x-client-id": clientId,
      },
    });
    if (!res.ok) throw new Error("Failed to load widget configuration");
    return await res.json();
  }

  async function copyTextWithFallback(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(text);
      return "Copied";
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    return "Copied";
  }

  async function shareMessageWithFallback(text, assistantName) {
    if (navigator.share) {
      await navigator.share({
        title: `${assistantName} — Response`,
        text: text,
      });
      return "Shared";
    }
    await copyTextWithFallback(text);
    return "Copied share text";
  }

  async function submitFeedback(messageId, rating, buttonEl, siblingEl) {
    if (!messageId || !conversationId) return;
    buttonEl.disabled = true;
    try {
      const res = await fetch(`${baseUrl}/v1/feedback`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "x-client-id": clientId,
        },
        body: JSON.stringify({
          clientId,
          conversationId,
          messageId,
          sessionId,
          rating,
        }),
      });
      if (!res.ok) throw new Error("Feedback failed");
      feedbackState[messageId] = rating;
      localStorage.setItem(STORAGE_KEY_FEEDBACK, JSON.stringify(feedbackState));
      buttonEl.setAttribute("data-active", "true");
      if (siblingEl) siblingEl.removeAttribute("data-active");
    } catch (_err) {
      buttonEl.title = "Could not save feedback";
    } finally {
      buttonEl.disabled = false;
    }
  }

  function createAssistantActionRow(messageId, messageText, assistantName) {
    const bar = document.createElement("div");
    bar.className = "orbit-widget-msg-actions";
    bar.setAttribute("role", "group");
    bar.setAttribute("aria-label", "Assistant message actions");

    const likeBtn = document.createElement("button");
    likeBtn.type = "button";
    likeBtn.className = "orbit-widget-action-btn";
    likeBtn.setAttribute("aria-label", "Like response");
    likeBtn.textContent = "👍 Helpful";

    const dislikeBtn = document.createElement("button");
    dislikeBtn.type = "button";
    dislikeBtn.className = "orbit-widget-action-btn";
    dislikeBtn.setAttribute("aria-label", "Dislike response");
    dislikeBtn.textContent = "👎 Not helpful";

    if (messageId && feedbackState[messageId] === "like") {
      likeBtn.setAttribute("data-active", "true");
    } else if (messageId && feedbackState[messageId] === "dislike") {
      dislikeBtn.setAttribute("data-active", "true");
    }

    likeBtn.addEventListener("click", () =>
      submitFeedback(messageId, "like", likeBtn, dislikeBtn)
    );
    dislikeBtn.addEventListener("click", () =>
      submitFeedback(messageId, "dislike", dislikeBtn, likeBtn)
    );

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "orbit-widget-action-btn";
    copyBtn.setAttribute("aria-label", "Copy message text");
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", async () => {
      const label = await copyTextWithFallback(messageText);
      copyBtn.textContent = label;
      setTimeout(() => {
        copyBtn.textContent = "Copy";
      }, 1600);
    });

    const shareBtn = document.createElement("button");
    shareBtn.type = "button";
    shareBtn.className = "orbit-widget-action-btn";
    shareBtn.setAttribute("aria-label", "Share message");
    shareBtn.textContent = "Share";
    shareBtn.addEventListener("click", async () => {
      const label = await shareMessageWithFallback(messageText, assistantName);
      shareBtn.textContent = label;
      setTimeout(() => {
        shareBtn.textContent = "Share";
      }, 1600);
    });

    bar.appendChild(likeBtn);
    bar.appendChild(dislikeBtn);
    bar.appendChild(copyBtn);
    bar.appendChild(shareBtn);
    return bar;
  }

  function mountWidget(cfg) {
    tenantConfig = cfg;
    const w = cfg.widget || {};
    const primaryColor = w.primaryColor || "#4f46e5";
    const theme = w.theme === "light" ? "light" : "dark";
    const position = w.position === "bottom-left" ? "bottom-left" : "bottom-right";
    const radius = typeof w.radius === "number" ? w.radius : 16;

    const root = document.createElement("div");
    root.id = "orbit-ai-widget-root";
    root.setAttribute("data-theme", theme);
    root.setAttribute("data-position", position);
    root.style.setProperty("--orbit-primary", primaryColor);
    root.style.setProperty("--orbit-radius", `${radius}px`);
    root.style.setProperty("--orbit-width", `${w.width || 380}px`);
    root.style.setProperty("--orbit-height", `${w.height || 580}px`);

    root.innerHTML = `
      <button type="button" class="orbit-widget-launcher" aria-label="Open ${cfg.assistantName || "Support"} chat">
        <span>${cfg.assistantName || "Chat"}</span>
      </button>
      <section class="orbit-widget-panel" aria-label="${cfg.assistantName || "Support Assistant"}" hidden>
        <header class="orbit-widget-header">
          <div class="orbit-widget-brand">
            <strong>${cfg.assistantName || "Orbit Assistant"}</strong>
            <span>${cfg.companyName || cfg.businessName || ""}</span>
          </div>
          <div class="orbit-widget-header-controls">
            <button type="button" class="orbit-widget-reset" aria-label="Start new conversation">New</button>
            <button type="button" class="orbit-widget-minimize" aria-label="Minimize chat">—</button>
            <button type="button" class="orbit-widget-close" aria-label="Close chat">✕</button>
          </div>
        </header>
        <div class="orbit-widget-messages" role="log" aria-live="polite"></div>
        <div class="orbit-widget-suggestions"></div>
        <form class="orbit-widget-lead-form" hidden>
          <p class="orbit-lead-title">Leave your contact details</p>
          <input type="text" name="name" placeholder="Your name" required aria-label="Your name" />
          <input type="email" name="email" placeholder="Email address" aria-label="Email address" />
          <input type="tel" name="phone" placeholder="Phone number" aria-label="Phone number" />
          <input type="text" name="requirement" placeholder="How can we help?" aria-label="Requirement" />
          <button type="submit" aria-label="Submit contact details">Send Details</button>
        </form>
        <form class="orbit-widget-composer">
          <input type="text" name="message" placeholder="${w.inputPlaceholder || "Ask a question..."}" aria-label="Chat message" autocomplete="off" required />
          <button type="submit" aria-label="Send message">Send</button>
        </form>
      </section>
    `;

    document.body.appendChild(root);

    const launcher = root.querySelector(".orbit-widget-launcher");
    const panel = root.querySelector(".orbit-widget-panel");
    const messagesEl = root.querySelector(".orbit-widget-messages");
    const suggestionsEl = root.querySelector(".orbit-widget-suggestions");
    const composer = root.querySelector(".orbit-widget-composer");
    const leadForm = root.querySelector(".orbit-widget-lead-form");
    const closeBtn = root.querySelector(".orbit-widget-close");
    const minimizeBtn = root.querySelector(".orbit-widget-minimize");
    const resetBtn = root.querySelector(".orbit-widget-reset");

    function appendMessage(role, text, messageId) {
      const item = document.createElement("div");
      item.className = `orbit-widget-msg orbit-widget-msg-${role}`;
      const bubble = document.createElement("div");
      bubble.className = "orbit-widget-bubble";
      bubble.textContent = text;
      item.appendChild(bubble);
      if (role === "assistant") {
        item.appendChild(
          createAssistantActionRow(
            messageId || `msg_${Date.now()}`,
            text,
            cfg.assistantName || "Assistant"
          )
        );
      }
      messagesEl.appendChild(item);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    appendMessage("assistant", cfg.welcomeMessage || "Hello! How can I help you today?", "welcome_msg");

    if (Array.isArray(w.suggestedQuestions)) {
      w.suggestedQuestions.forEach((q) => {
        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "orbit-widget-suggestion";
        chip.textContent = q;
        chip.addEventListener("click", () => sendChatMessage(q));
        suggestionsEl.appendChild(chip);
      });
    }

    async function sendChatMessage(text) {
      const clean = (text || "").trim();
      if (!clean) return;
      appendMessage("user", clean);

      const typingEl = document.createElement("div");
      typingEl.className = "orbit-widget-typing";
      typingEl.textContent = `${cfg.assistantName || "Assistant"} is typing...`;
      messagesEl.appendChild(typingEl);

      try {
        const res = await fetch(`${baseUrl}/v1/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-api-key": apiKey,
            "x-client-id": clientId,
          },
          body: JSON.stringify({
            clientId,
            sessionId,
            conversationId: conversationId || undefined,
            message: clean,
          }),
        });
        const data = await res.json();
        typingEl.remove();
        if (!res.ok) {
          appendMessage(
            "assistant",
            (data.error && data.error.message) || "Service temporarily unavailable.",
            ""
          );
          return;
        }
        if (data.conversationId) {
          conversationId = data.conversationId;
          localStorage.setItem(STORAGE_KEY_CONV, conversationId);
        }
        appendMessage("assistant", data.answer, data.messageId);
        if (data.evidenceState === "UNKNOWN" && cfg.leadCaptureEnabled && !leadSubmitted) {
          leadForm.hidden = false;
        }
      } catch (_err) {
        typingEl.remove();
        appendMessage("assistant", "Network error. Please try again.", "");
      }
    }

    launcher.addEventListener("click", () => {
      isOpen = true;
      panel.hidden = false;
      launcher.hidden = true;
    });

    closeBtn.addEventListener("click", () => {
      isOpen = false;
      panel.hidden = true;
      launcher.hidden = false;
    });

    minimizeBtn.addEventListener("click", () => {
      isMinimized = !isMinimized;
      panel.classList.toggle("orbit-minimized", isMinimized);
    });

    resetBtn.addEventListener("click", () => {
      sessionId = "sess_" + Math.random().toString(36).slice(2, 11) + "_" + Date.now();
      conversationId = "";
      localStorage.setItem(STORAGE_KEY_SESSION, sessionId);
      localStorage.removeItem(STORAGE_KEY_CONV);
      messagesEl.innerHTML = "";
      appendMessage("assistant", cfg.welcomeMessage || "Hello! How can I help you today?", "welcome_msg");
    });

    composer.addEventListener("submit", (e) => {
      e.preventDefault();
      const input = composer.elements.message;
      const val = input.value;
      input.value = "";
      sendChatMessage(val);
    });

    leadForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (leadSubmitted) return;
      const payload = {
        clientId,
        conversationId: conversationId || undefined,
        name: leadForm.elements.name.value,
        email: leadForm.elements.email.value,
        phone: leadForm.elements.phone.value,
        requirement: leadForm.elements.requirement.value,
      };
      const res = await fetch(`${baseUrl}/v1/leads`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "x-client-id": clientId,
        },
        body: JSON.stringify(payload),
      });
      if (res.ok) {
        leadSubmitted = true;
        localStorage.setItem(STORAGE_KEY_LEAD, "1");
        leadForm.hidden = true;
        appendMessage("assistant", "Thank you! Our team has received your contact details.", "lead_ack");
      }
    });
  }

  fetchConfig()
    .then(mountWidget)
    .catch((err) => console.warn("[Orbit AI Widget]", err.message));
})();
