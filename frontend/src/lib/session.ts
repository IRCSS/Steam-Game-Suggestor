// A "session" matches the legacy semantics: one page load. Seen/history state lives in the backend
// (view_events) keyed by this id, so nothing here mutates persistent study status.
function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export const SESSION_ID = newSessionId();
