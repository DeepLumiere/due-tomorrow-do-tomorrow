import { NextResponse } from "next/server";
import { connectToDatabase } from "@/lib/db";
import Evaluation from "@/lib/Evaluation";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const user = searchParams.get("user")?.trim().toLowerCase();

  await connectToDatabase();
  const query = user ? { submittedByEmail: user } : { $or: [{ status: "approved" }, { status: { $exists: false } }] };
  const evaluations = await Evaluation.find(query).sort({ evaluatedAt: -1 }).limit(100).lean();

  return NextResponse.json({ evaluations, database: "connected" });
}

export async function POST(request: Request) {
  const body = await request.json();
  await connectToDatabase();

  const evaluation = await Evaluation.create({
    model: body.model?.trim(),
    organization: body.organization?.trim(),
    benchmark: body.benchmark?.trim(),
    score: Number(body.score),
    metric: body.metric?.trim(),
    category: body.category?.trim(),
    source: body.source?.trim() || "",
    status: "pending",
    submittedBy: body.submittedBy?.trim() || "community",
    submittedByEmail: body.submittedByEmail?.trim().toLowerCase() || "",
  });

  return NextResponse.json({ evaluation }, { status: 201 });
}
