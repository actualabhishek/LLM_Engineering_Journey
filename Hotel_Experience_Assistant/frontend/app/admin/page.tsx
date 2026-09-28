"use client";

import { useEffect, useState } from "react";
import {
  checkAuth,
  login,
  logout,
  fetchBookings,
  fetchCheckins,
  fetchConversations,
  fetchConversationMessages,
  type Booking,
  type Checkin,
  type Conversation,
  type Message,
} from "@/lib/admin";

function formatPaise(paise: number) {
  return `₹${(paise / 100).toLocaleString("en-IN")}`;
}

export default function AdminPage() {
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState<string | null>(null);

  const [bookings, setBookings] = useState<Booking[]>([]);
  const [checkins, setCheckins] = useState<Checkin[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [transcript, setTranscript] = useState<Message[] | null>(null);
  const [transcriptId, setTranscriptId] = useState<number | null>(null);

  useEffect(() => {
    checkAuth()
      .then(setAuthenticated)
      .finally(() => setAuthChecked(true));
  }, []);

  useEffect(() => {
    if (!authenticated) return;
    fetchBookings().then(setBookings);
    fetchCheckins().then(setCheckins);
    fetchConversations().then(setConversations);
  }, [authenticated]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoginError(null);
    const ok = await login(password);
    if (ok) {
      setAuthenticated(true);
    } else {
      setLoginError("Incorrect password");
    }
    setPassword("");
  }

  async function handleLogout() {
    await logout();
    setAuthenticated(false);
    setBookings([]);
    setCheckins([]);
    setConversations([]);
    setTranscript(null);
    setTranscriptId(null);
  }

  async function viewTranscript(id: number) {
    if (transcriptId === id) {
      setTranscriptId(null);
      setTranscript(null);
      return;
    }
    const messages = await fetchConversationMessages(id);
    setTranscriptId(id);
    setTranscript(messages);
  }

  if (!authChecked) {
    return null;
  }

  if (!authenticated) {
    return (
      <div className="flex flex-1 flex-col items-center px-4 mt-16">
        <h1 className="text-2xl font-semibold mb-6">Admin Login</h1>
        <form
          data-testid="admin-login"
          onSubmit={handleLogin}
          className="flex flex-col gap-3 w-full max-w-xs"
        >
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="border border-gray-300 rounded px-3 py-2"
          />
          <button
            type="submit"
            className="rounded bg-blue-600 text-white px-4 py-2 font-medium"
          >
            Log in
          </button>
          {loginError && <p className="text-red-600 text-sm">{loginError}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-8 gap-10 w-full">
      <div className="w-full max-w-4xl flex justify-between items-center">
        <h1 className="text-2xl font-semibold">Admin</h1>
        <button
          onClick={handleLogout}
          className="rounded bg-gray-200 px-4 py-2 text-sm font-medium"
        >
          Log out
        </button>
      </div>

      <section className="w-full max-w-4xl">
        <h2 className="text-xl font-semibold mb-3">Bookings</h2>
        {bookings.length === 0 ? (
          <p className="text-gray-500">No bookings yet</p>
        ) : (
          <table data-testid="bookings-table" className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b border-gray-300">
                <th className="py-1 pr-2">Reference</th>
                <th className="py-1 pr-2">Guest</th>
                <th className="py-1 pr-2">Room Type</th>
                <th className="py-1 pr-2">Check-in</th>
                <th className="py-1 pr-2">Check-out</th>
                <th className="py-1 pr-2">Guests</th>
                <th className="py-1 pr-2">Status</th>
                <th className="py-1 pr-2">Price</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((b) => (
                <tr key={b.reference} className="border-b border-gray-100">
                  <td className="py-1 pr-2">{b.reference}</td>
                  <td className="py-1 pr-2">{b.guest_name}</td>
                  <td className="py-1 pr-2">{b.room_type_name}</td>
                  <td className="py-1 pr-2">{b.check_in_date}</td>
                  <td className="py-1 pr-2">{b.check_out_date}</td>
                  <td className="py-1 pr-2">{b.num_guests}</td>
                  <td className="py-1 pr-2">{b.status}</td>
                  <td className="py-1 pr-2">{formatPaise(b.total_price_paise)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="w-full max-w-4xl">
        <h2 className="text-xl font-semibold mb-3">Check-ins</h2>
        {checkins.length === 0 ? (
          <p className="text-gray-500">No check-ins yet</p>
        ) : (
          <table data-testid="checkins-table" className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b border-gray-300">
                <th className="py-1 pr-2">Booking Reference</th>
                <th className="py-1 pr-2">Guest</th>
                <th className="py-1 pr-2">Arrival Time</th>
                <th className="py-1 pr-2">Status</th>
                <th className="py-1 pr-2">Special Requests</th>
              </tr>
            </thead>
            <tbody>
              {checkins.map((c) => (
                <tr key={c.booking_reference} className="border-b border-gray-100">
                  <td className="py-1 pr-2">{c.booking_reference}</td>
                  <td className="py-1 pr-2">{c.guest_name}</td>
                  <td className="py-1 pr-2">{c.arrival_time}</td>
                  <td className="py-1 pr-2">{c.status}</td>
                  <td className="py-1 pr-2">{c.special_requests ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="w-full max-w-4xl">
        <h2 className="text-xl font-semibold mb-3">Conversations</h2>
        {conversations.length === 0 ? (
          <p className="text-gray-500">No conversations yet</p>
        ) : (
          <table data-testid="conversations-table" className="w-full text-sm border-collapse">
            <thead>
              <tr className="text-left border-b border-gray-300">
                <th className="py-1 pr-2">Guest</th>
                <th className="py-1 pr-2">Started</th>
                <th className="py-1 pr-2">Ended</th>
                <th className="py-1 pr-2">Language</th>
                <th className="py-1 pr-2">Messages</th>
                <th className="py-1 pr-2"></th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((c) => (
                <tr key={c.id} className="border-b border-gray-100">
                  <td className="py-1 pr-2">{c.guest_name ?? "—"}</td>
                  <td className="py-1 pr-2">{c.started_at}</td>
                  <td className="py-1 pr-2">{c.ended_at ?? "—"}</td>
                  <td className="py-1 pr-2">{c.language ?? "—"}</td>
                  <td className="py-1 pr-2">{c.message_count}</td>
                  <td className="py-1 pr-2">
                    <button
                      onClick={() => viewTranscript(c.id)}
                      className="text-blue-600 underline text-sm"
                    >
                      {transcriptId === c.id ? "Hide" : "View"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {transcript && (
          <div data-testid="transcript" className="mt-4 border border-gray-300 rounded p-4">
            <h3 className="font-semibold mb-2">Transcript</h3>
            <div className="space-y-2 text-sm">
              {transcript.map((m, i) => (
                <p key={i}>
                  <span className="font-medium">{m.role}: </span>
                  {m.content}
                </p>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
