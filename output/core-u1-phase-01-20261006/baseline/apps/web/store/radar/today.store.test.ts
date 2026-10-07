import { describe, expect, it, vi } from "vitest";
import { RadarTodayStore } from "./today.store";
import type { RadarTodayQueue } from "../../services/radar/today.types";

const queue: RadarTodayQueue = {
  date: "2026-10-05",
  timezone: "America/Bahia",
  risks: [],
  decisions: [],
  overdue_actions: [],
  suggestions: [],
};

describe("RADAR Today attention store", () => {
  it("loads only the workspace attention projection with the user's timezone", async () => {
    const service = { getToday: vi.fn().mockResolvedValue(queue) };
    const store = new RadarTodayStore("team", service, "America/Bahia");
    await store.load();
    expect(service.getToday).toHaveBeenCalledWith("team", "America/Bahia");
    expect(store.queue).toEqual(queue);
    expect(store.loading).toBe(false);
    expect(store.error).toBeNull();
    expect(new RadarTodayStore("other", service, "UTC").queue).toBeNull();
  });
  it("removes stale suggestions on failure and supports retry", async () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => undefined);
    try {
      const service = {
        getToday: vi
          .fn()
          .mockResolvedValueOnce(queue)
          .mockRejectedValueOnce(new Error("403"))
          .mockResolvedValueOnce(queue),
      };
      const store = new RadarTodayStore("team", service, "UTC");
      await store.load();
      const reload = store.load();
      expect(store.queue).toBeNull();
      expect(store.loading).toBe(true);
      await reload;
      expect(store.error).toBeTruthy();
      expect(store.queue).toBeNull();
      expect(store.loading).toBe(false);
      await store.load();
      expect(store.error).toBeNull();
      expect(store.queue).toEqual(queue);
    } finally {
      log.mockRestore();
    }
  });
  it("deduplicates concurrent refresh events", async () => {
    let complete!: (queue: RadarTodayQueue) => void;
    const service = {
      getToday: vi.fn(
        () =>
          new Promise<RadarTodayQueue>((resolve) => {
            complete = resolve;
          })
      ),
    };
    const store = new RadarTodayStore("team", service, "UTC");
    const first = store.load();
    await store.load();
    expect(service.getToday).toHaveBeenCalledTimes(1);
    complete(queue);
    await first;
    expect(store.queue).toEqual(queue);
  });
});
