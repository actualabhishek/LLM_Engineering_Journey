import { describe, expect, it } from "vitest";
import { colorForInitials } from "./avatarColor";

describe("colorForInitials", () => {
  it("returns the same color for the same initials", () => {
    expect(colorForInitials("AS")).toBe(colorForInitials("AS"));
  });

  it("returns a valid hex color", () => {
    expect(colorForInitials("JR")).toMatch(/^#[0-9a-f]{6}$/);
  });

  it("distributes different initials across the palette", () => {
    const colors = new Set(
      ["AS", "JR", "MK", "TL", "ZZ", "QQ"].map(colorForInitials)
    );
    expect(colors.size).toBeGreaterThan(1);
  });
});
