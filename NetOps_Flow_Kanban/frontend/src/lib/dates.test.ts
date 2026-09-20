import { describe, expect, it } from "vitest";
import {
  daysBetween,
  daysFromNow,
  endOfWeek,
  formatDate,
  formatMaintenanceWindow,
  startOfWeek,
} from "./dates";

describe("daysFromNow", () => {
  it("returns an ISO date offset from the given base date", () => {
    const base = new Date("2026-09-18T10:00:00");
    expect(daysFromNow(0, base)).toBe("2026-09-18");
    expect(daysFromNow(5, base)).toBe("2026-09-23");
    expect(daysFromNow(-2, base)).toBe("2026-09-16");
  });
});

describe("daysBetween", () => {
  it("computes the day difference between two ISO dates", () => {
    expect(daysBetween("2026-09-18", "2026-09-20")).toBe(2);
    expect(daysBetween("2026-09-18", "2026-09-16")).toBe(-2);
    expect(daysBetween("2026-09-18", "2026-09-18")).toBe(0);
  });
});

describe("formatDate", () => {
  it("formats an ISO date as a readable string", () => {
    expect(formatDate("2026-09-18")).toBe("Sep 18, 2026");
  });
});

describe("formatMaintenanceWindow", () => {
  it("formats a maintenance window from an ISO date", () => {
    expect(formatMaintenanceWindow("2026-09-18")).toBe(
      "Fri, Sep 18 - 22:00 to 02:00 UTC"
    );
  });
});

describe("startOfWeek / endOfWeek", () => {
  it("treats Monday as the start of the week", () => {
    const friday = new Date("2026-09-18T10:00:00");
    const monday = startOfWeek(friday);
    const sunday = endOfWeek(friday);
    expect(monday.getDay()).toBe(1);
    expect(sunday.getDay()).toBe(0);
    expect(monday.getDate()).toBe(14);
    expect(sunday.getDate()).toBe(20);
  });
});
