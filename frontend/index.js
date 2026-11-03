const API_URL =
  window.location.port === "8000"
    ? window.location.origin
    : "http://127.0.0.1:8000";

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

// BACKEND HEALTH

async function checkHealth() {
  try {
    const response = await fetch(`${API_URL}/health`, {
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error("Backend unavailable");
    }

    const data = await response.json();

    if (corpusCount) {
      corpusCount.textContent =
        typeof data.chunks === "number"
          ? `${data.chunks} legislation chunks indexed`
          : "Legislation index connected";
    }
  } catch (error) {
    if (corpusCount) {
      corpusCount.textContent = "Backend unavailable";
    }

    console.error("Health check failed:", error);
  }
}

// OLLAMA STATUS

function setOllamaStatus(state, message) {
  if (!ollamaBadge || !ollamaText) return;

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
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const data = await response.json();

    if (data.running === true) {
      if (data.model_available === false) {
        setOllamaStatus("offline", "Ollama online · model missing");
      } else {
        const model = data.model || "Ollama";
        setOllamaStatus("online", `Ollama ready · ${model}`);
      }
    } else {
      setOllamaStatus("offline", "Ollama offline");
    }
  } catch (error) {
    setOllamaStatus("offline", "Ollama status unavailable");

    console.error("Ollama status check failed:", error);
  }
}

// SAFE LEGISLATION LINKS

function getLegislationUrl(source) {
  if (!source || typeof source.uri !== "string") {
    return null;
  }

  try {
    const url = new URL(source.uri);

    const allowedHosts = ["legislation.gov.uk", "www.legislation.gov.uk"];

    if (url.protocol === "https:" && allowedHosts.includes(url.hostname)) {
      return url;
    }
  } catch {
    return null;
  }

  return null;
}

// FILTER SOURCES

function filterSources(sources) {
  if (!Array.isArray(sources)) return [];

  return sources.filter(
    (source) =>
      source &&
      typeof source.text === "string" &&
      source.text.trim().length > 0,
  );
}

// RECEIPTS

function renderSources(sources) {
  if (!sourcesList) return;

  sourcesList.replaceChildren();

  const validSources = filterSources(sources);

  if (validSources.length === 0) {
    return;
  }

  validSources.forEach((source, index) => {
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
    excerpt.textContent = source.text;

    card.append(number, title, excerpt);

    if (url) {
      const link = document.createElement("a");

      link.className = "source-link";
      link.href = url.href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "See it on legislation.gov.uk";

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

// SHOW A CASE

function showMatter(matter) {
  const sources = filterSources(matter.sources);
  const count = sources.length;

  if (displayQuestion) {
    displayQuestion.textContent = matter.query;
  }

  if (findingTitle) {
    findingTitle.textContent = "Here's what the wig found.";
  }

  if (answerContent) {
    answerContent.textContent = matter.answer || "No answer was returned.";
  }

  if (questionMeta) {
    questionMeta.textContent =
      count > 0
        ? `${count} ${count === 1 ? "law" : "laws"} fetched`
        : "No sources found";
  }

  if (sourcesSummary) {
    sourcesSummary.textContent =
      count > 0
        ? `${count} ${count === 1 ? "source" : "sources"} available in Receipts.`
        : "No supporting legislation found.";
  }

  renderSources(sources);
}

// CASE HISTORY

function renderMatters() {
  if (!matterList) return;

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

// SUBMIT QUESTION

if (form && input && submitButton) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    if (isLoading) return;

    const question = input.value.trim();

    if (!question) return;

    isLoading = true;
    submitButton.disabled = true;

    if (submitLabel) {
      submitLabel.textContent = "Thinking...";
    }

    if (requestStatus) {
      requestStatus.textContent = "Searching legislation...";
    }

    if (displayQuestion) {
      displayQuestion.textContent = question;
    }

    if (findingTitle) {
      findingTitle.textContent = "The wig is thinking...";
    }

    if (answerContent) {
      answerContent.textContent = "Retrieving relevant laws...";
    }

    if (sourcesSummary) {
      sourcesSummary.textContent = "";
    }

    if (sourcesList) {
      sourcesList.replaceChildren();
    }

    try {
      const url = new URL(`${API_URL}/ask`);
      url.searchParams.set("query", question);

      const response = await fetch(url.toString());

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

      const sources = filterSources(data.sources);

      const matter = {
        query: question,
        answer: data.answer,
        sources: data.answered === false ? [] : sources,
      };

      matters.push(matter);
      activeMatter = matters.length - 1;

      showMatter(matter);
      renderMatters();

      input.value = "";

      if (requestStatus) {
        requestStatus.textContent = "Research complete.";
      }
    } catch (error) {
      if (findingTitle) {
        findingTitle.textContent = "Something went wrong.";
      }

      if (answerContent) {
        answerContent.textContent = (
          matter.answer || "No answer was returned."
        ).trim();
      }

      if (sourcesSummary) {
        sourcesSummary.textContent = "";
      }

      if (sourcesList) {
        sourcesList.replaceChildren();
      }

      if (requestStatus) {
        requestStatus.textContent = "Check your backend connection.";
      }

      console.error("Question request failed:", error);
    } finally {
      isLoading = false;
      submitButton.disabled = false;

      if (submitLabel) {
        submitLabel.textContent = "Ask the wig";
      }
    }
  });
}

// NEW CASE

if (newMatterButton) {
  newMatterButton.addEventListener("click", () => {
    if (isLoading) return;

    activeMatter = -1;

    if (displayQuestion) {
      displayQuestion.textContent = "Ask the wig a question about UK law.";
    }

    if (questionMeta) {
      questionMeta.textContent = "Ask about UK legislation";
    }

    if (findingTitle) {
      findingTitle.textContent = "Let's find some wiggle room.";
    }

    if (answerContent) {
      answerContent.textContent =
        "Ask a question and the wig will search the legislation.";
    }

    if (sourcesSummary) {
      sourcesSummary.textContent =
        "Supporting legislation will appear in Receipts.";
    }

    if (sourcesList) {
      sourcesList.replaceChildren();
    }

    if (requestStatus) {
      requestStatus.textContent = "";
    }

    if (input) {
      input.value = "";
      input.focus();
    }

    renderMatters();
  });
}

// INITIALISE

checkHealth();
checkOllamaStatus();

setInterval(checkOllamaStatus, 15000);
