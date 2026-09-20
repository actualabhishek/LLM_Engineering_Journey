"use client";

import { useState, type FormEvent } from "react";
import { ApiError, login } from "@/lib/api";

function signInError(err: unknown): string {
  if (err instanceof ApiError) {
    return err.status === 401
      ? "Invalid username or password"
      : `Sign in failed (server error ${err.status}). Try again.`;
  }
  // fetch rejects outright when nothing is listening
  return "Cannot reach the server. Check that it is running, then try again.";
}

interface LoginFormProps {
  onSuccess: (token: string) => void;
}

export function LoginForm({ onSuccess }: LoginFormProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const token = await login(username, password);
      onSuccess(token);
    } catch (err) {
      setError(signInError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-field">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-xl border border-line bg-surface p-8"
      >
        <h1 className="mb-1 text-lg font-semibold text-ink">
          NetOps Flow
        </h1>
        <p className="mb-6 text-sm text-muted">Sign in to your board</p>

        <label className="mb-3 block text-xs font-medium text-muted">
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            required
            autoFocus
            className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
          />
        </label>

        <label className="mb-4 block text-xs font-medium text-muted">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            className="mt-1 w-full rounded-md border border-line bg-field px-2 py-1.5 text-sm text-ink"
          />
        </label>

        {error && (
          <p className="mb-4 text-xs font-medium text-danger-red">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-accent-solid px-3 py-2 text-sm font-medium text-white hover:bg-accent-solid-hover disabled:opacity-60"
        >
          {submitting ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
