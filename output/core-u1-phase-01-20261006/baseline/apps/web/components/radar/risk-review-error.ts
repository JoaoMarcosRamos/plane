import { semanticError } from "./semantic-utils";

export function riskReviewError(cause: unknown): string {
  if (cause && typeof cause === "object" && "response" in cause) {
    const response = cause.response;
    if (response && typeof response === "object") {
      const status = "status" in response ? response.status : null;
      const data = "data" in response ? response.data : null;
      const code = data && typeof data === "object" && "code" in data ? data.code : null;
      if (status === 409) {
        if (code === "authorization_stale") return "Agent permissions or configuration changed. Run a new review.";
        if (code === "approval_stale") return "Approval expired or its context changed. Run a new review.";
        if (code === "revision_conflict")
          return "Objects changed since this preview. Use Edit to save a fresh proposal, then review it before accepting.";
        return "This review is no longer current. Reload reviews or start a new review.";
      }
      if (status === 403 || status === 404)
        return "This review or its context is no longer available under your permissions.";
      if (status === 503)
        return "The agent service is unavailable. Retry or check the review before starting another one.";
    }
  }
  return semanticError(cause);
}
