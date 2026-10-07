import { NextResponse } from "next/server";
import { AUTH_COOKIE } from "@/lib/server/config";

export async function POST(): Promise<NextResponse> {
  const res = NextResponse.json({ ok: true });
  res.cookies.set({ name: AUTH_COOKIE, value: "", path: "/", maxAge: 0, httpOnly: true, sameSite: "lax" });
  return res;
}
