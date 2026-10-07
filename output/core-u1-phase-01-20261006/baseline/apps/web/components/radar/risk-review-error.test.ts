import { describe, expect, it } from "vitest";
import { riskReviewError } from "./risk-review-error";

describe("human review errors", () => {
  it("explains concurrent versions without exposing Object IDs", () => {
    const text = riskReviewError({
      response: { status: 409, data: { code: "revision_conflict", object_id: "private-object-id" } },
    });
    expect(text).toContain("Use Edit");
    expect(text).not.toContain("private-object-id");
  });
  it.each(["authorization_stale", "approval_stale"])("%s asks for a new review", (code) => {
    expect(riskReviewError({ response: { status: 409, data: { code } } })).toContain("new review");
  });
  it("reports runtime unavailability without provider details", () => {
    expect(riskReviewError({ response: { status: 503, data: { detail: "provider_secret_error" } } })).toContain(
      "agent service is unavailable"
    );
  });
});
