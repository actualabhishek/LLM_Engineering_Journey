export type Booking = {
  reference: string;
  guest_name: string;
  room_type_name: string;
  check_in_date: string;
  check_out_date: string;
  num_guests: number;
  status: string;
  total_price_paise: number;
  created_at: string;
};

export type Checkin = {
  booking_reference: string;
  guest_name: string;
  arrival_time: string;
  status: string;
  special_requests: string | null;
  created_at: string;
};

export type Conversation = {
  id: number;
  guest_name: string | null;
  started_at: string;
  ended_at: string | null;
  language: string | null;
  message_count: number;
};

export type Message = {
  role: string;
  content: string;
  created_at: string;
};

export async function checkAuth(): Promise<boolean> {
  const res = await fetch("/api/admin/me");
  const data = await res.json();
  return data.authenticated;
}

export async function login(password: string): Promise<boolean> {
  const res = await fetch("/api/admin/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ password }),
  });
  return res.ok;
}

export async function logout(): Promise<void> {
  await fetch("/api/admin/logout", { method: "POST" });
}

export async function fetchBookings(): Promise<Booking[]> {
  const res = await fetch("/api/admin/bookings");
  return res.json();
}

export async function fetchCheckins(): Promise<Checkin[]> {
  const res = await fetch("/api/admin/checkins");
  return res.json();
}

export async function fetchConversations(): Promise<Conversation[]> {
  const res = await fetch("/api/admin/conversations");
  return res.json();
}

export async function fetchConversationMessages(id: number): Promise<Message[]> {
  const res = await fetch(`/api/admin/conversations/${id}`);
  return res.json();
}
