const API_URL = "http://127.0.0.1:8000";

const $ = (id) => document.getElementById(id);

const form = $("question-form");
const input = $("question-input");
const submitButton = $("submit-button");
const submitLabel = $("submit-label");
const displayQuestion = $("display-question");
const questionMeta = $("question-meta");
const findingTitle = $("finding-title");
const answerContent = $("answer-content");
const sourcesSummary = $("answer-sources-summary");
const sourcesList = $("sources-list");
const matterList = $("matter-list");
const newMatterButton = $("new-matter");
const requestStatus = $("request-status");
const corpusCount = $("corpus-count");
const ollamaBadge = $("ollama-status");
const ollamaText = $("ollama-status-text");

const matters = [];
let activeMatter = -1;
let isLoading = false;

// BACKEND STATUS

async function checkHealth() {
  try {
    const response = await fetch(`${API_URL}/health`);

    if (!response.ok) {
      throw new Error("Backend unavailable");
    }

    const data = await response.json();

    corpusCount.textContent =
      typeof data.chunks === "number"
        ? `${data.chunks} legislation chunks indexed`
        : "Legislation index connected";
  } catch {
    corpusCount.textContent = "Backend unavailable";
  }
}

// OLLAMA STATUS

function setOllamaStatus(state, message) {
  ollamaBadge.classList.remove(
    "status-online",
    "status-offline",
    "status-checking",
  );

  ollamaBadge.classList.add(`status-${state}`);
  ollamaText.textContent = message;
}

async function checkOllamaStatus() {
  try {
    const response = await fetch(`${API_URL}/ollama-status`, {
      signal: AbortSignal.timeout(4000),
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("Status endpoint unavailable");
    }

    const data = await response.json();

    if (data.online && data.model_available) {
      setOllamaStatus("online", "Ollama ready · llama3.1");
    } else if (data.online) {
      setOllamaStatus("offline", "Ollama online · model missing");
    } else {
      setOllamaStatus("offline", "Ollama offline");
    }
  } catch {
    setOllamaStatus("offline", "Ollama status unavailable");
  }
}

// SAFE LEGISLATION URL

function getLegislationUrl(source) {
  if (typeof source.uri !== "string") return null;

  try {
    const url = new URL(source.uri);

    const allowedHosts = ["legislation.gov.uk", "www.legislation.gov.uk"];

    if (url.protocol === "https:" && allowedHosts.includes(url.hostname)) {
      return url;
    }
  } catch {
    // Invalid source URL.
  }

  return null;
}

// SOURCE CARDS

function renderSources(sources) {
  sourcesList.replaceChildren();

  if (!Array.isArray(sources) || sources.length === 0) {
    const message = document.createElement("p");
    message.className = "empty-message";
    message.textContent = "No legislation sources returned.";
    sourcesList.appendChild(message);
    return;
  }

  sources.forEach((source, index) => {
    const card = document.createElement("article");
    card.className = "source-card";

    const number = document.createElement("span");
    number.className = "source-number";
    number.textContent = String(index + 1);

    const title = document.createElement("h3");
    title.className = "source-title";

    const url = getLegislationUrl(source);

    if (url) {
      const parts = url.pathname.split("/").filter(Boolean);

      title.textContent =
        parts.length > 0
          ? parts.join(" / ")
          : `Legislation source ${index + 1}`;
    } else {
      title.textContent = `Retrieved authority ${index + 1}`;
    }

    const excerpt = document.createElement("div");
    excerpt.className = "source-excerpt";
    excerpt.textContent =
      typeof source.text === "string" ? source.text : "No passage provided.";

    card.append(number, title, excerpt);

    if (url) {
      const link = document.createElement("a");
      link.className = "source-link";
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "See it on legislation.gov.uk →";

      card.appendChild(link);
    } else {
      const unavailable = document.createElement("p");
      unavailable.className = "source-unavailable";
      unavailable.textContent = "Direct legislation link unavailable.";

      card.appendChild(unavailable);
    }

    sourcesList.appendChild(card);
  });
}

// DISPLAY A CASE

function showMatter(matter) {
  displayQuestion.textContent = matter.query;
  findingTitle.textContent = "Here's what the wig found.";

  answerContent.textContent = matter.answer || "No answer was returned.";

  const count = matter.sources.length;

  questionMeta.textContent = `${count} ${count === 1 ? "law" : "laws"} fetched`;

  sourcesSummary.textContent =
    count > 0
      ? `${count} ${count === 1 ? "source" : "sources"} available in Receipts.`
      : "No supporting sources were returned.";

  renderSources(matter.sources);
}

// CASE HISTORY

function renderMatters() {
  matterList.replaceChildren();

  matters.forEach((matter, index) => {
    const button = document.createElement("button");

    button.type = "button";
    button.className = "matter-item";
    button.textContent = matter.query;
    button.title = matter.query;

    if (index === activeMatter) {
      button.classList.add("active");
    }

    button.addEventListener("click", () => {
      if (isLoading) return;

      activeMatter = index;
      showMatter(matter);
      renderMatters();
    });

    matterList.appendChild(button);
  });
}

// QUESTION SUBMISSION

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (isLoading) return;

  const question = input.value.trim();
  if (!question) return;

  isLoading = true;
  submitButton.disabled = true;
  submitLabel.textContent = "Thinking...";

  requestStatus.textContent = "Searching legislation...";
  displayQuestion.textContent = question;
  findingTitle.textContent = "The wig is thinking...";
  answerContent.textContent = "Retrieving relevant laws...";

  sourcesSummary.textContent = "Waiting for retrieved sources.";

  sourcesList.textContent = "Searching...";

  try {
    const url = new URL(`${API_URL}/ask`);
    url.searchParams.set("query", question);

    const response = await fetch(url);

    if (!response.ok) {
      if (response.status === 429) {
        throw new Error("Too many requests. Try again in a minute.");
      }

      throw new Error(`Backend returned HTTP ${response.status}.`);
    }

    const data = await response.json();

    if (typeof data.answer !== "string") {
      throw new Error("The backend returned an invalid answer.");
    }

    const matter = {
      query: question,
      answer: data.answer,
      sources: Array.isArray(data.sources) ? data.sources : [],
    };

    matters.push(matter);
    activeMatter = matters.length - 1;

    showMatter(matter);
    renderMatters();

    input.value = "";
    requestStatus.textContent = "Research complete.";
  } catch (error) {
    findingTitle.textContent = "Something went wrong.";
    answerContent.textContent = error.message;

    sourcesSummary.textContent = "No results available.";

    sourcesList.textContent = "Sources could not be retrieved.";

    requestStatus.textContent = "Check your backend connection.";
  } finally {
    isLoading = false;
    submitButton.disabled = false;
    submitLabel.textContent = "Ask the wig";
  }
});

// NEW CASE

newMatterButton.addEventListener("click", () => {
  if (isLoading) return;

  activeMatter = -1;

  displayQuestion.textContent = "Ask the wig a question about UK law.";

  questionMeta.textContent = "Ask about UK legislation";

  findingTitle.textContent = "Let's find some wiggle room.";

  answerContent.textContent =
    "Ask a question and the wig will search the legislation.";

  sourcesSummary.textContent =
    "Supporting legislation will appear in Receipts.";

  sourcesList.textContent = "Retrieved legislation will appear here.";

  requestStatus.textContent = "";
  input.value = "";

  renderMatters();
  input.focus();
});

// INITIALISE

checkHealth();
checkOllamaStatus();

setInterval(checkOllamaStatus, 15000);
