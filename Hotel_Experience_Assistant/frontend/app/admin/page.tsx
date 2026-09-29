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
import { Logo } from "@/components/Logo";

function Header() {
  return (
    <div className="flex items-center gap-3 mb-6">
      <Logo size={32} />
      <span className="font-serif text-xl font-semibold text-parchment">Velvet Vista Hotel</span>
    </div>
  );
}

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
        <Header />
        <h1 className="text-2xl font-semibold mb-6 text-parchment">Admin Login</h1>
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
            className="border border-gold/40 bg-parchment text-velvet-deep rounded px-3 py-2"
          />
          <button
            type="submit"
            className="rounded bg-gold text-velvet-deep px-4 py-2 font-medium"
          >
            Log in
          </button>
          {loginError && <p className="text-error text-sm">{loginError}</p>}
        </form>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-8 gap-10 w-full">
      <div className="w-full max-w-4xl flex justify-between items-center">
        <Header />
        <button
          onClick={handleLogout}
          className="rounded bg-parchment text-velvet-deep px-4 py-2 text-sm font-medium"
        >
          Log out
        </button>
      </div>

      <section className="w-full max-w-4xl">
        <h2 className="text-xl font-semibold mb-3 text-parchment">Bookings</h2>
        {bookings.length === 0 ? (
          <p className="text-parchment/60">No bookings yet</p>
        ) : (
          <table data-testid="bookings-table" className="w-full text-sm border-collapse bg-parchment text-velvet-deep">
            <thead>
              <tr className="text-left border-b border-velvet-deep/20">
                <th className="py-1 px-2">Reference</th>
                <th className="py-1 px-2">Guest</th>
                <th className="py-1 px-2">Room Type</th>
                <th className="py-1 px-2">Check-in</th>
                <th className="py-1 px-2">Check-out</th>
                <th className="py-1 px-2">Guests</th>
                <th className="py-1 px-2">Status</th>
                <th className="py-1 px-2">Price</th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((b) => (
                <tr key={b.reference} className="border-b border-velvet-deep/10">
                  <td className="py-1 px-2">{b.reference}</td>
                  <td className="py-1 px-2">{b.guest_name}</td>
                  <td className="py-1 px-2">{b.room_type_name}</td>
                  <td className="py-1 px-2">{b.check_in_date}</td>
                  <td className="py-1 px-2">{b.check_out_date}</td>
                  <td className="py-1 px-2">{b.num_guests}</td>
                  <td className="py-1 px-2">{b.status}</td>
                  <td className="py-1 px-2">{formatPaise(b.total_price_paise)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="w-full max-w-4xl">
        <h2 className="text-xl font-semibold mb-3 text-parchment">Check-ins</h2>
        {checkins.length === 0 ? (
          <p className="text-parchment/60">No check-ins yet</p>
        ) : (
          <table data-testid="checkins-table" className="w-full text-sm border-collapse bg-parchment text-velvet-deep">
            <thead>
              <tr className="text-left border-b border-velvet-deep/20">
                <th className="py-1 px-2">Booking Reference</th>
                <th className="py-1 px-2">Guest</th>
                <th className="py-1 px-2">Arrival Time</th>
                <th className="py-1 px-2">Status</th>
                <th className="py-1 px-2">Special Requests</th>
              </tr>
            </thead>
            <tbody>
              {checkins.map((c) => (
                <tr key={c.booking_reference} className="border-b border-velvet-deep/10">
                  <td className="py-1 px-2">{c.booking_reference}</td>
                  <td className="py-1 px-2">{c.guest_name}</td>
                  <td className="py-1 px-2">{c.arrival_time}</td>
                  <td className="py-1 px-2">{c.status}</td>
                  <td className="py-1 px-2">{c.special_requests ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="w-full max-w-4xl">
        <h2 className="text-xl font-semibold mb-3 text-parchment">Conversations</h2>
        {conversations.length === 0 ? (
          <p className="text-parchment/60">No conversations yet</p>
        ) : (
          <table data-testid="conversations-table" className="w-full text-sm border-collapse bg-parchment text-velvet-deep">
            <thead>
              <tr className="text-left border-b border-velvet-deep/20">
                <th className="py-1 px-2">Guest</th>
                <th className="py-1 px-2">Started</th>
                <th className="py-1 px-2">Ended</th>
                <th className="py-1 px-2">Language</th>
                <th className="py-1 px-2">Messages</th>
                <th className="py-1 px-2"></th>
              </tr>
            </thead>
            <tbody>
              {conversations.map((c) => (
                <tr key={c.id} className="border-b border-velvet-deep/10">
                  <td className="py-1 px-2">{c.guest_name ?? "—"}</td>
                  <td className="py-1 px-2">{c.started_at}</td>
                  <td className="py-1 px-2">{c.ended_at ?? "—"}</td>
                  <td className="py-1 px-2">{c.language ?? "—"}</td>
                  <td className="py-1 px-2">{c.message_count}</td>
                  <td className="py-1 px-2">
                    <button
                      onClick={() => viewTranscript(c.id)}
                      className="text-wine underline text-sm"
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
          <div data-testid="transcript" className="mt-4 border border-gold/40 bg-parchment text-velvet-deep rounded p-4">
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
