import { NextResponse } from "next/server";
import { checkAdminCredentials, ADMIN_SECRET_KEY } from "@/lib/adminAuth";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const { email = "", password = "" } = await request.json();
  if (!checkAdminCredentials(email, password)) {
    return NextResponse.json({ error: "Invalid admin credentials." }, { status: 401 });
  }
  return NextResponse.json({
    success: true,
    token: ADMIN_SECRET_KEY,
    admin: { email: (process.env.ADMIN_EMAIL || "admin@evalboard.com").trim().toLowerCase(), role: "admin" },
  });
}
