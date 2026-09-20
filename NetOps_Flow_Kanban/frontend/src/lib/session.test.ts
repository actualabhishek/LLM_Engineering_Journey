import { beforeEach, describe, expect, it } from "vitest";
import { clearToken, getStoredToken, storeToken } from "./session";

describe("session token storage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("returns null when no token is stored", () => {
    expect(getStoredToken()).toBeNull();
  });

  it("stores and retrieves a token", () => {
    storeToken("abc123");
    expect(getStoredToken()).toBe("abc123");
  });

  it("clears a stored token", () => {
    storeToken("abc123");
    clearToken();
    expect(getStoredToken()).toBeNull();
  });
});
