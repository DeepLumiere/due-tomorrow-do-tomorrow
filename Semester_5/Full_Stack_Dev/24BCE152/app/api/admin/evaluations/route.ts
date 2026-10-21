import { NextResponse } from "next/server";
import { connectToDatabase } from "@/lib/db";
import Evaluation from "@/lib/Evaluation";
import { verifyAdminToken } from "@/lib/adminAuth";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  if (!verifyAdminToken(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const status = searchParams.get("status")?.trim().toLowerCase();

  await connectToDatabase();
  const query = status && ["pending", "approved", "rejected"].includes(status) ? { status } : {};

  const [evaluations, total, pending, approved, rejected] = await Promise.all([
    Evaluation.find(query).sort({ evaluatedAt: -1 }).lean(),
    Evaluation.countDocuments(),
    Evaluation.countDocuments({ status: "pending" }),
    Evaluation.countDocuments({ $or: [{ status: "approved" }, { status: { $exists: false } }] }),
    Evaluation.countDocuments({ status: "rejected" }),
  ]);

  return NextResponse.json({ evaluations, counts: { total, pending, approved, rejected } });
}

export async function PATCH(request: Request) {
  if (!verifyAdminToken(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { id, ...updates } = await request.json();
  await connectToDatabase();

  const updated = await Evaluation.findByIdAndUpdate(id, { $set: updates }, { new: true }).lean();
  return NextResponse.json({ success: true, evaluation: updated });
}

export async function DELETE(request: Request) {
  if (!verifyAdminToken(request)) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = new URL(request.url);
  const id = searchParams.get("id");
  await connectToDatabase();

  await Evaluation.findByIdAndDelete(id).lean();
  return NextResponse.json({ success: true, id });
}
