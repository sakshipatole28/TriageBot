// TriageBot front end: checks /health, sends the bug report to POST /triage, shows the result.

const form = document.getElementById("triageForm");
const input = document.getElementById("issueInput");
const submitBtn = document.getElementById("submitBtn");
const charCount = document.getElementById("charCount");
const steps = document.querySelectorAll("#pipeline li");
const resultCard = document.getElementById("resultCard");
const errorCard = document.getElementById("errorCard");

// 1. Show whether the backend is up and whether an API key is configured.
async function checkHealth() {
  const box = document.getElementById("status");
  const text = document.getElementById("statusText");
  try {
    const res = await fetch("/health");
    const data = await res.json();
    box.className = "status " + (data.llm_configured ? "ok" : "bad");
    text.textContent = data.llm_configured ? `Ready: ${data.model}` : "Backend up, but no API key set";
  } catch (err) {
    box.className = "status bad";
    text.textContent = "Backend not reachable";
  }
}

// 2. Example buttons fill the text box.
document.querySelectorAll("[data-example]").forEach((btn) => {
  btn.addEventListener("click", () => {
    input.value = btn.dataset.example;
    updateCount();
  });
});

function updateCount() {
  charCount.textContent = `${input.value.length} / 4000`;
}
input.addEventListener("input", updateCount);

// 3. Light up the agent steps one by one while we wait (the server runs them in order).
let stepTimer = null;
function animateSteps() {
  let current = 0;
  steps.forEach((s) => (s.className = ""));
  steps[0].className = "active";
  stepTimer = setInterval(() => {
    if (current < steps.length - 1) {
      steps[current].className = "done";
      current += 1;
      steps[current].className = "active";
    }
  }, 4000);
}
function finishSteps(ok) {
  clearInterval(stepTimer);
  steps.forEach((s) => (s.className = ok ? "done" : ""));
}

// 4. Very small markdown renderer. We escape HTML FIRST so the LLM output cannot inject tags.
function escapeHtml(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function renderMarkdown(md) {
  return escapeHtml(md)
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h3>$1</h3>")
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

function showResult(data) {
  const badges = [
    data.severity && `Severity ${data.severity}`,
    data.priority && `Priority ${data.priority}`,
    data.team && data.team,
  ].filter(Boolean);
  document.getElementById("badges").innerHTML = badges
    .map((b) => `<span class="badge">${escapeHtml(b)}</span>`)
    .join("");
  document.getElementById("meta").textContent =
    `Related past issues: ${data.related_issues.join(", ") || "none"}  |  ` +
    `Tools called: ${data.tools_used.join(", ") || "none"}`;
  document.getElementById("report").innerHTML = renderMarkdown(data.report);
  resultCard.classList.remove("hidden");
}

function showError(message) {
  errorCard.textContent = message;
  errorCard.classList.remove("hidden");
}

// 5. Submit the form.
form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resultCard.classList.add("hidden");
  errorCard.classList.add("hidden");

  submitBtn.disabled = true;
  submitBtn.textContent = "Agents working...";
  animateSteps();

  try {
    const res = await fetch("/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ issue: input.value }),
    });
    const data = await res.json();
    if (!res.ok) {
      // 422 gives a list of validation errors; other errors give a string.
      const detail = Array.isArray(data.detail) ? data.detail.map((d) => d.msg).join("; ") : data.detail;
      throw new Error(`${res.status}: ${detail}`);
    }
    finishSteps(true);
    showResult(data);
  } catch (err) {
    finishSteps(false);
    showError(err.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Triage this bug";
  }
});

checkHealth();
