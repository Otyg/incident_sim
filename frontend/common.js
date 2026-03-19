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
  };
})();
