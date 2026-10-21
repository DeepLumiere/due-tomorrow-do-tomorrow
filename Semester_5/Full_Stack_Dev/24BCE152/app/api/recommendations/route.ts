import { NextResponse } from "next/server";
import { connectToDatabase } from "@/lib/db";
import Evaluation from "@/lib/Evaluation";

export const dynamic = "force-dynamic";

function inferCategories(work: string) {
  const text = work.toLowerCase();
  const terms: Record<string, string[]> = {
    Coding: ["code", "coding", "program", "software", "dev", "debug", "web", "app", "python", "javascript", "react", "api"],
    Reasoning: ["reason", "math", "logic", "solve", "plan", "analyze", "problem", "proof", "agent"],
    Knowledge: ["research", "fact", "knowledge", "study", "learn", "explain", "summarize", "document", "answer"],
    Safety: ["safe", "safety", "moderate", "harm", "policy", "risk", "trust"],
  };
  const matched = Object.entries(terms).filter(([, words]) => words.some((w) => text.includes(w))).map(([cat]) => cat);
  return matched.length ? matched : ["Reasoning", "Coding", "Knowledge", "Safety"];
}

export async function POST(request: Request) {
  const { work = "" } = await request.json();
  await connectToDatabase();

  const records = await Evaluation.find().select("model organization benchmark score metric category").lean();
  const categories = inferCategories(work);

  const groups = new Map<string, any[]>();
  for (const r of records) {
    const name = r.model.replace(/^Demo\s*[·-]\s*/i, "").trim();
    const list = groups.get(name) || [];
    list.push({ ...r, model: name });
    groups.set(name, list);
  }

  const candidates = [...groups.entries()].map(([model, items]) => {
    const matching = items.filter((i) => categories.includes(i.category));
    const evidence = matching.length ? matching : items;
    const average = Math.round((evidence.reduce((sum, i) => sum + i.score, 0) / evidence.length) * 10) / 10;
    return {
      model,
      organization: items[0].organization,
      average,
      evidence: evidence.slice(0, 3).map(({ benchmark, metric, score, category }) => ({ benchmark, metric, score, category })),
    };
  }).sort((a, b) => b.average - a.average).slice(0, 8);

  const best = candidates[0] || { model: "GPT-4.1", organization: "OpenAI", average: 88, evidence: [] };
  let reason = `${best.model} has the highest benchmark average (${best.average}%) in the relevant evaluation categories.`;

  const apiKey = process.env.GEMINI_API_KEY?.trim();
  if (apiKey) {
    try {
      const model = process.env.GEMINI_MODEL || "gemini-2.5-flash";
      const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${apiKey}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contents: [{ parts: [{ text: `Task: "${work}". Candidates: ${JSON.stringify(candidates)}. Pick the best model and return JSON with keys "model" and "reason" (1 short sentence).` }] }],
          generationConfig: { responseMimeType: "application/json" },
        }),
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = await res.json();
        const raw = data.candidates?.[0]?.content?.parts?.[0]?.text?.replace(/```json|```/g, "").trim();
        const parsed = JSON.parse(raw);
        if (parsed?.reason) reason = parsed.reason;
      }
    } catch {
      // Keep best match reason
    }
  }

  return NextResponse.json({
    recommendation: best,
    reason,
    candidates,
  });
}
