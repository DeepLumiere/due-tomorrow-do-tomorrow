import { NextResponse } from "next/server";
import { connectToDatabase } from "@/lib/db";
import mongoose, { Schema } from "mongoose";

const UserSchema = new Schema({
  email: { type: String, required: true, unique: true, lowercase: true, trim: true },
  password: { type: String, required: true },
  name: { type: String, default: "" },
  createdAt: { type: Date, default: Date.now },
});

const User = mongoose.models.User || mongoose.model("User", UserSchema);

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const { email = "", password = "" } = await request.json();
  const trimmedEmail = email.trim().toLowerCase();
  const name = trimmedEmail.split("@")[0] || "User";

  await connectToDatabase();
  let user = await User.findOne({ email: trimmedEmail });
  if (!user) {
    user = await User.create({ email: trimmedEmail, password: password || "password123", name });
  }

  const userData = { id: user._id.toString(), email: user.email, name: user.name || name };
  const res = NextResponse.json({ success: true, user: userData });
  res.cookies.set("evalboard_user", JSON.stringify(userData), { path: "/", maxAge: 60 * 60 * 24 * 30 });
  return res;
}

export async function DELETE() {
  const res = NextResponse.json({ success: true });
  res.cookies.set("evalboard_user", "", { path: "/", maxAge: 0 });
  return res;
}
