(function () {
  const TURN_RETRY_DELAYS_MS = [2000, 4000, 8000, 16000];
  const STORAGE_KEYS = {
    selectedScenarioId: "incident_sim.selectedScenarioId",
    currentScenarioId: "incident_sim.currentScenarioId",
    currentSessionId: "incident_sim.currentSessionId",
    latestNarration: "incident_sim.latestNarration",
    debrief: "incident_sim.debrief",
    authoringSourceText: "incident_sim.authoringSourceText",
    authoringDraft: "incident_sim.authoringDraft",
  };

  class ApiError extends Error {
    constructor(message, { status, body } = {}) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.body = body || null;
    }
  }

  function sleep(ms) {
    return new Promise((resolve) => window.setTimeout(resolve, ms));
  }

  function getErrorMessage(error) {
    if (error instanceof ApiError) {
      if (typeof error.body?.detail === "string") {
        return error.body.detail;
      }

      if (Array.isArray(error.body?.detail)) {
        return error.body.detail
          .map((item) => item?.msg || item?.message || JSON.stringify(item))
          .join(" | ");
      }
    }

    if (error instanceof Error && typeof error.message === "string") {
      return error.message;
    }

    if (typeof error === "string") {
      return error;
    }

    try {
      return JSON.stringify(error);
    } catch {
      return "Ett okänt fel inträffade.";
    }
  }

  async function readJsonFile(file) {
    const content = await file.text();

    try {
      return JSON.parse(content);
    } catch {
      throw new Error("Filen innehåller inte giltig JSON.");
    }
  }

  async function apiRequest(path, options = {}) {
    const { headers: optionHeaders = {}, ...restOptions } = options;

    const response = await fetch(path, {
      ...restOptions,
      headers: {
        "Content-Type": "application/json",
        ...optionHeaders,
      },
    });

    const isJson = response.headers.get("content-type")?.includes("application/json");
    const body = isJson ? await response.json() : null;

    if (!response.ok) {
      throw new ApiError(body?.detail || `Request failed: ${response.status}`, {
        status: response.status,
        body,
      });
    }

    return body;
  }

  function loadStoredJson(key, fallback = null) {
    const rawValue = window.localStorage.getItem(key);
    if (!rawValue) {
      return fallback;
    }

    try {
      return JSON.parse(rawValue);
    } catch {
      return fallback;
    }
  }

  function saveStoredJson(key, value) {
    if (value === null || value === undefined) {
      window.localStorage.removeItem(key);
      return;
    }

    window.localStorage.setItem(key, JSON.stringify(value));
  }

  function loadStoredText(key, fallback = "") {
    const rawValue = window.localStorage.getItem(key);
    return rawValue === null ? fallback : rawValue;
  }

  function saveStoredText(key, value) {
    if (!value) {
      window.localStorage.removeItem(key);
      return;
    }

    window.localStorage.setItem(key, value);
  }

  function setSelectedScenarioId(scenarioId) {
    saveStoredText(STORAGE_KEYS.selectedScenarioId, scenarioId);
  }

  function getSelectedScenarioId() {
    return loadStoredText(STORAGE_KEYS.selectedScenarioId);
  }

  function setCurrentScenarioId(scenarioId) {
    saveStoredText(STORAGE_KEYS.currentScenarioId, scenarioId);
    if (scenarioId) {
      setSelectedScenarioId(scenarioId);
    }
  }

  function getCurrentScenarioId() {
    return loadStoredText(STORAGE_KEYS.currentScenarioId);
  }

  function getPreferredScenarioId() {
    return getCurrentScenarioId() || getSelectedScenarioId();
  }

  function setCurrentSessionId(sessionId) {
    saveStoredText(STORAGE_KEYS.currentSessionId, sessionId);
  }

  function getCurrentSessionId() {
    return loadStoredText(STORAGE_KEYS.currentSessionId);
  }

  function clearCurrentSessionState() {
    saveStoredText(STORAGE_KEYS.currentSessionId, "");
    saveStoredJson(STORAGE_KEYS.latestNarration, null);
    saveStoredJson(STORAGE_KEYS.debrief, null);
  }

  function setLatestNarration(narration) {
    saveStoredJson(STORAGE_KEYS.latestNarration, narration);
  }

  function getLatestNarration() {
    return loadStoredJson(STORAGE_KEYS.latestNarration);
  }

  function setStoredDebrief(debrief) {
    saveStoredJson(STORAGE_KEYS.debrief, debrief);
  }

  function getStoredDebrief() {
    return loadStoredJson(STORAGE_KEYS.debrief);
  }

  function setAuthoringSourceText(text) {
    saveStoredText(STORAGE_KEYS.authoringSourceText, text);
  }

  function getAuthoringSourceText() {
    return loadStoredText(STORAGE_KEYS.authoringSourceText);
  }

  function setAuthoringDraft(draft) {
    saveStoredJson(STORAGE_KEYS.authoringDraft, draft);
  }

  function getAuthoringDraft() {
    return loadStoredJson(STORAGE_KEYS.authoringDraft);
  }

  function resolveStateNarration(stateDefinition, audience) {
    const narration = stateDefinition?.narration;
    if (!narration) {
      return null;
    }

    return narration.by_audience?.[audience] || narration.default || null;
  }

  function deriveLatestNarration({ session, scenario, timeline }) {
    if (Array.isArray(timeline) && timeline.length > 0) {
      return timeline[timeline.length - 1].narrator_response || null;
    }

    const matchingState = (scenario?.states || []).find(
      (item) => item.phase === session?.phase
    );
    return resolveStateNarration(matchingState, session?.audience);
  }

  function getPreferredManualInjectId(scenario, session) {
    const injects = scenario?.inject_catalog || [];
    if (injects.length === 0) {
      return "";
    }

    const activeInjects = session?.active_injects || [];
    const availableInject = injects.find((item) => !activeInjects.includes(item.id));
    return availableInject?.id || injects[0]?.id || "";
  }

  function getAvailableScenarioPhases(scenario) {
    return (scenario?.states || [])
      .map((state) => state.phase)
      .filter((phase, index, items) => phase && items.indexOf(phase) === index);
  }

  function getCurrentTurnScenarioEvents(session) {
    if (!session) {
      return [];
    }

    return session.exercise_log.filter(
      (item) =>
        item.turn === session.turn_number &&
        (item.type === "scenario_event" || item.type === "phase_change")
    );
  }

  function getSessionEventLog(session) {
    if (!session) {
      return [];
    }

    return session.exercise_log
      .filter((item) => item.type !== "participant_action")
      .slice()
      .reverse();
  }

  function getActiveInjectDetails(scenario, session) {
    const availableInjects = scenario?.inject_catalog || [];
    return (session?.active_injects || []).map((injectId) => {
      const definition = availableInjects.find((item) => item.id === injectId);
      return (
        definition || {
          id: injectId,
          title: injectId,
          type: "okand",
          description: "Ingen inject-beskrivning hittades i scenariots katalog.",
        }
      );
    });
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function escapeHtmlAttribute(value) {
    return escapeHtml(value).replaceAll("`", "&#96;");
  }

  function sanitizeLinkUrl(rawUrl) {
    const trimmed = String(rawUrl || "").trim();
    if (!trimmed) {
      return null;
    }

    if (
      trimmed.startsWith("/") ||
      trimmed.startsWith("./") ||
      trimmed.startsWith("../") ||
      trimmed.startsWith("#")
    ) {
      return trimmed;
    }

    try {
      const parsed = new URL(trimmed, window.location.origin);
      if (["http:", "https:", "mailto:"].includes(parsed.protocol)) {
        return parsed.href;
      }
    } catch {
      return null;
    }

    return null;
  }

  function renderInlineMarkdown(text) {
    const codeSegments = [];
    const withCodePlaceholders = String(text).replace(/`([^`]+)`/g, (_, code) => {
      const placeholder = `__CODE_SEGMENT_${codeSegments.length}__`;
      codeSegments.push(`<code>${escapeHtml(code)}</code>`);
      return placeholder;
    });

    let html = escapeHtml(withCodePlaceholders);

    html = html.replace(
      /\[([^\]]+)\]\(([^)\s]+(?:\s+"[^"]*")?)\)/g,
      (_, label, rawTarget) => {
        const href = sanitizeLinkUrl(rawTarget.split(/\s+"/, 1)[0]);
        if (!href) {
          return escapeHtml(label);
        }

        return `<a href="${escapeHtmlAttribute(
          href
        )}" target="_blank" rel="noreferrer">${escapeHtml(label)}</a>`;
      }
    );
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/__([^_]+)__/g, "<strong>$1</strong>");
    html = html.replace(/(^|[\s(])\*([^*]+)\*(?=[\s).,!?]|$)/g, "$1<em>$2</em>");
    html = html.replace(/(^|[\s(])_([^_]+)_(?=[\s).,!?]|$)/g, "$1<em>$2</em>");
    html = html.replace(/~~([^~]+)~~/g, "<del>$1</del>");

    codeSegments.forEach((segment, index) => {
      html = html.replace(`__CODE_SEGMENT_${index}__`, segment);
    });

    return html;
  }

  function renderMarkdownToHtml(markdown) {
    const normalized = String(markdown || "").replace(/\r\n?/g, "\n");
    const lines = normalized.split("\n");
    const html = [];
    let paragraphLines = [];
    let listType = null;
    let listItems = [];
    let quoteLines = [];
    let inCodeBlock = false;
    let codeLanguage = "";
    let codeLines = [];

    function flushParagraph() {
      if (paragraphLines.length === 0) {
        return;
      }

      html.push(
        `<p>${paragraphLines.map((line) => renderInlineMarkdown(line)).join("<br />")}</p>`
      );
      paragraphLines = [];
    }

    function flushList() {
      if (!listType || listItems.length === 0) {
        listType = null;
        listItems = [];
        return;
      }

      const tagName = listType === "ordered" ? "ol" : "ul";
      const itemsHtml = listItems
        .map((item) => `<li>${item.map((line) => renderInlineMarkdown(line)).join("<br />")}</li>`)
        .join("");
      html.push(`<${tagName}>${itemsHtml}</${tagName}>`);
      listType = null;
      listItems = [];
    }

    function flushQuote() {
      if (quoteLines.length === 0) {
        return;
      }

      html.push(`<blockquote>${renderMarkdownToHtml(quoteLines.join("\n"))}</blockquote>`);
      quoteLines = [];
    }

    function flushCodeBlock() {
      if (!inCodeBlock) {
        return;
      }

      const languageClass = codeLanguage
        ? ` class="language-${escapeHtmlAttribute(codeLanguage)}"`
        : "";
      html.push(
        `<pre><code${languageClass}>${escapeHtml(codeLines.join("\n"))}</code></pre>`
      );
      inCodeBlock = false;
      codeLanguage = "";
      codeLines = [];
    }

    function flushOpenBlocks() {
      flushParagraph();
      flushList();
      flushQuote();
    }

    lines.forEach((line) => {
      const trimmed = line.trim();

      if (inCodeBlock) {
        if (trimmed.startsWith("```")) {
          flushCodeBlock();
        } else {
          codeLines.push(line);
        }
        return;
      }

      const codeFenceMatch = line.match(/^```(\S+)?\s*$/);
      if (codeFenceMatch) {
        flushOpenBlocks();
        inCodeBlock = true;
        codeLanguage = codeFenceMatch[1] || "";
        return;
      }

      if (!trimmed) {
        flushOpenBlocks();
        return;
      }

      const quoteMatch = line.match(/^>\s?(.*)$/);
      if (quoteMatch) {
        flushParagraph();
        flushList();
        quoteLines.push(quoteMatch[1]);
        return;
      }
      flushQuote();

      const headingMatch = line.match(/^(#{1,6})\s+(.*)$/);
      if (headingMatch) {
        flushOpenBlocks();
        const level = headingMatch[1].length;
        html.push(`<h${level}>${renderInlineMarkdown(headingMatch[2])}</h${level}>`);
        return;
      }

      if (/^([-*_]\s*){3,}$/.test(trimmed)) {
        flushOpenBlocks();
        html.push("<hr />");
        return;
      }

      const unorderedMatch = line.match(/^[-*+]\s+(.*)$/);
      const orderedMatch = line.match(/^\d+\.\s+(.*)$/);
      if (unorderedMatch || orderedMatch) {
        flushParagraph();
        const nextListType = orderedMatch ? "ordered" : "unordered";
        if (listType && listType !== nextListType) {
          flushList();
        }
        listType = nextListType;
        listItems.push([unorderedMatch?.[1] || orderedMatch[1]]);
        return;
      }

      if (listType && listItems.length > 0) {
        listItems[listItems.length - 1].push(trimmed);
        return;
      }

      paragraphLines.push(trimmed);
    });

    flushCodeBlock();
    flushOpenBlocks();

    return html.join("");
  }

  window.IncidentSimCommon = {
    TURN_RETRY_DELAYS_MS,
    ApiError,
    sleep,
    getErrorMessage,
    readJsonFile,
    apiRequest,
    setSelectedScenarioId,
    getSelectedScenarioId,
    setCurrentScenarioId,
    getCurrentScenarioId,
    getPreferredScenarioId,
    setCurrentSessionId,
    getCurrentSessionId,
    clearCurrentSessionState,
    setLatestNarration,
    getLatestNarration,
    setStoredDebrief,
    getStoredDebrief,
    setAuthoringSourceText,
    getAuthoringSourceText,
    setAuthoringDraft,
    getAuthoringDraft,
    deriveLatestNarration,
    getPreferredManualInjectId,
    getAvailableScenarioPhases,
    getCurrentTurnScenarioEvents,
    getSessionEventLog,
    getActiveInjectDetails,
    renderMarkdownToHtml,
  };
})();
