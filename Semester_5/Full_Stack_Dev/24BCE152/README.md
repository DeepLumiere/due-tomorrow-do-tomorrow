# Evalboard — Technical Architecture & Flow Documentation

Evalboard is a full-stack Next.js application for exploring, submitting, and comparing AI model evaluation benchmarks. It includes an evidence-based Model Advisor powered by Google's Gemini API and a dedicated administrator moderation portal.

---

## Table of Contents

1. [Libraries & Technologies](#1-libraries--technologies)
2. [Project Layout & Function Inventory](#2-project-layout--function-inventory)
3. [System Architecture Diagram](#3-system-architecture-diagram)
4. [Flow 1: Database Connection & DNS Handling (`lib/db.ts`)](#4-flow-1-database-connection--dns-handling-libdbts)
5. [Flow 2: Authentication & User Session (`/api/auth` & `/login`)](#5-flow-2-authentication--user-session-apiauth--login)
6. [Flow 3: Evaluation Cards & Submissions (`/api/evaluations` & `/`)](#6-flow-3-evaluation-cards--submissions-apievaluations--)
7. [Flow 4: Model Advisor & Gemini Recommendation (`/api/recommendations`)](#7-flow-4-model-advisor--gemini-recommendation-apirecommendations)
8. [Flow 5: Admin Moderation Console (`/admin` & `/api/admin/*`)](#8-flow-5-admin-moderation-console-admin--apiadmin)
9. [Environment Settings & Setup](#9-environment-settings--setup)

---

## 1. Libraries & Technologies

| Library / Tool | Version | Purpose in Project |
| :--- | :--- | :--- |
| **Next.js** | `^14.2.21` | React App Router framework handling client pages and serverless API route handlers. |
| **React & React-DOM** | `^18.3.1` | Client-side reactive UI components, hooks (`useState`, `useEffect`, `useMemo`). |
| **Mongoose** | `^8.9.5` | ODM for MongoDB schema modeling, queries, updates, and connection caching. |
| **Lucide React** | `^0.468.0` | SVG icons for navigation, status indicators, badges, and modal actions. |
| **Node.js `dns` & `net`** | Native | Custom DNS lookup fallback to resolve Atlas replica set hosts without Windows `querySrv` failures. |
| **Fetch API** | Native | Server-side communication with Google's Generative Language API (Gemini). |
| **TypeScript** | `^5.7.3` | Type definitions and compile-time validation. |

---

## 2. Project Layout & Function Inventory

```text
├── app/
│   ├── layout.tsx                     Shared HTML shell & metadata
│   ├── globals.css                    Global responsive CSS stylesheet
│   ├── page.tsx                       Public Scoreboard & Model Advisor modal
│   ├── login/page.tsx                 User Login & Account Creation page
│   ├── admin/page.tsx                 Admin Login & Moderation console
│   └── api/
│       ├── auth/route.ts              User authentication & account persistence
│       ├── evaluations/route.ts       Public evaluation listing & card submissions
│       ├── recommendations/route.ts   Model Advisor ranking & Gemini generation
│       └── admin/
│           ├── auth/route.ts          Admin credential verification & token issue
│           └── evaluations/route.ts   Admin CRUD & moderation actions
├── lib/
│   ├── db.ts                          Cached Mongoose connection with custom DNS lookup
│   ├── Evaluation.ts                  Mongoose schema & model for evaluations
│   └── adminAuth.ts                   Admin credential checks & token verification
├── .env                               Environment configuration
└── README.md                          This documentation
```

### File-by-File Function Inventory

| File | Exported Functions / Handlers | Description |
| :--- | :--- | :--- |
| `lib/db.ts` | `connectToDatabase()` | Connects to MongoDB, manages singleton cache, and uses `lookup` mapping to bypass Windows DNS `EREFUSED` errors. |
| `lib/Evaluation.ts` | `default Evaluation` | Mongoose Model for evaluation documents. |
| `lib/adminAuth.ts` | `checkAdminCredentials(email, pass)`<br>`verifyAdminToken(request)` | Compares email/password with configured admin credentials; validates `x-admin-token` header. |
| `app/api/auth/route.ts` | `POST(request)`<br>`DELETE()` | Signs in or creates user in MongoDB, issues `evalboard_user` cookie; deletes cookie on logout. |
| `app/api/evaluations/route.ts` | `GET(request)`<br>`POST(request)` | Fetches public approved cards (or user submissions); creates pending evaluation card. |
| `app/api/recommendations/route.ts`| `inferCategories(work)`<br>`POST(request)` | Categorizes work, ranks database evaluation candidates, queries Gemini, returns recommended model. |
| `app/api/admin/auth/route.ts` | `POST(request)` | Authenticates administrator and returns secret session token. |
| `app/api/admin/evaluations/route.ts`| `GET(request)`<br>`PATCH(request)`<br>`DELETE(request)` | Lists all status cards with counts; approves/rejects cards; deletes cards permanently. |
| `app/page.tsx` | `Home()` (Component)<br>`loadEvaluations()`<br>`loadUserEvaluations()`<br>`createEvaluation()`<br>`findModel()`<br>`handleLogout()` | Main scoreboard, category filter, search, submission modal, and Model Advisor dialog. |
| `app/login/page.tsx` | `LoginPage()` (Component)<br>`handleSubmit()`<br>`handleQuickDemo()` | Sign-in and account creation form with direct redirect to home. |
| `app/admin/page.tsx` | `AdminPage()` (Component)<br>`handleAdminLogin()`<br>`loadData()`<br>`updateStatus()`<br>`deleteEvaluation()`<br>`handleAdminLogout()` | Admin login gate and moderation dashboard. |

---

## 3. System Architecture Diagram

```mermaid
flowchart TD
    subgraph Client ["Browser / Client-Side (React 18)"]
        UI_Home["app/page.tsx (Scoreboard & Advisor)"]
        UI_Login["app/login/page.tsx (Sign In / Register)"]
        UI_Admin["app/admin/page.tsx (Admin Console)"]
    end

    subgraph API ["Next.js Server Route Handlers"]
        API_Auth["/api/auth (POST, DELETE)"]
        API_Eval["/api/evaluations (GET, POST)"]
        API_Rec["/api/recommendations (POST)"]
        API_AdminAuth["/api/admin/auth (POST)"]
        API_AdminEval["/api/admin/evaluations (GET, PATCH, DELETE)"]
    end

    subgraph Core ["Shared Library Layer"]
        DB["lib/db.ts (connectToDatabase)"]
        Model_Eval["lib/Evaluation.ts (Mongoose)"]
        Model_User["User Model (in auth/route.ts)"]
        Admin_Auth["lib/adminAuth.ts"]
    end

    subgraph External ["External Services"]
        MongoDB[("MongoDB Atlas Database\n(Cluster 'evalution')")]
        GeminiAPI["Google AI Studio API\n(models/gemini-2.5-flash)"]
    end

    UI_Home -->|Fetch cards / submit| API_Eval
    UI_Home -->|Task description| API_Rec
    UI_Home -->|Sign out| API_Auth
    UI_Login -->|Email & Password| API_Auth
    UI_Admin -->|Admin credentials| API_AdminAuth
    UI_Admin -->|Moderate / Delete| API_AdminEval

    API_Auth --> DB
    API_Auth --> Model_User
    API_Eval --> DB
    API_Eval --> Model_Eval
    API_Rec --> DB
    API_Rec --> Model_Eval
    API_Rec -->|Generate content| GeminiAPI
    API_AdminAuth --> Admin_Auth
    API_AdminEval --> DB
    API_AdminEval --> Model_Eval
    API_AdminEval --> Admin_Auth

    DB -->|Static Host IP Resolution| MongoDB
```

---

## 4. Flow 1: Database Connection & DNS Handling (`lib/db.ts`)

### Why Custom DNS is Needed
On Windows systems, Node.js's standard `dns.lookup` and `mongodb+srv://` SRV queries often trigger `querySrv EREFUSED` or `queryA EREFUSED` due to local ISP/router DNS limitations. 

`lib/db.ts` solves this by:
1. Using the direct standard replica set URI (`atlas-12luut-shard-0`).
2. Providing a custom `lookup` function that maps Atlas shard hostnames directly to their public IP addresses (`159.41.206.101`, `159.41.206.123`, `159.41.206.113`), achieving zero-latency DNS resolution and eliminating connection drops.
3. Reusing a cached `mongoose` connection on `globalThis` across server requests.

### Implementation Snippet (`lib/db.ts`)

```typescript
import mongoose from "mongoose";

const MONGODB_URI =
  process.env.MONGODB_URI ||
  "mongodb://jeelpadsala15_db_user:Mongo%40Pass@ac-avawqsa-shard-00-00.dwk4i6x.mongodb.net:27017,ac-avawqsa-shard-00-01.dwk4i6x.mongodb.net:27017,ac-avawqsa-shard-00-02.dwk4i6x.mongodb.net:27017/evalution?ssl=true&authSource=admin&replicaSet=atlas-12luut-shard-0&retryWrites=true&w=majority&tlsAllowInvalidCertificates=true";

// Direct IP lookup prevents Windows / ISP querySrv & queryA EREFUSED DNS failures
const SHARD_IPS: Record<string, string> = {
  "ac-avawqsa-shard-00-00.dwk4i6x.mongodb.net": "159.41.206.101",
  "ac-avawqsa-shard-00-01.dwk4i6x.mongodb.net": "159.41.206.123",
  "ac-avawqsa-shard-00-02.dwk4i6x.mongodb.net": "159.41.206.113",
};

const lookup: any = (hostname: string, _opts: any, cb: any) => {
  const callback = typeof _opts === "function" ? _opts : cb;
  if (SHARD_IPS[hostname]) return callback(null, SHARD_IPS[hostname], 4);
  require("dns").lookup(hostname, callback);
};

let cached = (global as any).mongoose || { conn: null, promise: null };
(global as any).mongoose = cached;

export async function connectToDatabase() {
  if (cached.conn) return cached.conn;
  if (!cached.promise) {
    cached.promise = mongoose.connect(MONGODB_URI, { lookup, family: 4 });
  }
  cached.conn = await cached.promise;
  return cached.conn;
}
```

---

## 5. Flow 2: Authentication & User Session (`/api/auth` & `/login`)

### The Flow
1. **User Input (`app/login/page.tsx`)**:
   - User inputs email and password, or clicks **"Use sample credentials"**.
   - Calls `handleSubmit()` which sends `POST /api/auth` with `{ email, password }`.
2. **Server Handler (`app/api/auth/route.ts`)**:
   - Invokes `connectToDatabase()`.
   - Checks if user exists via `User.findOne({ email })`.
   - If user doesn't exist, automatically creates the user record in MongoDB: `User.create({ email, password, name })`.
   - Sets a 30-day `evalboard_user` HTTP cookie containing `{ id, email, name }`.
   - Returns JSON: `{ success: true, user: { id, email, name } }`.
3. **Client State Update**:
   - `localStorage.setItem("evalboard_user", JSON.stringify(data.user))`.
   - Redirects to `/`.
   - In `app/page.tsx`, `useEffect` loads the stored user, sets `user` state, shows user avatar in topbar, and displays the **"My Submissions"** tab.
4. **Sign Out Flow**:
   - Clicking **"Sign out"** calls `handleLogout()`.
   - Calls `DELETE /api/auth` to clear the cookie.
   - Removes `evalboard_user` from `localStorage` and resets state.

### Code Snippet (`app/api/auth/route.ts`)

```typescript
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
```

---

## 6. Flow 3: Evaluation Cards & Submissions (`/api/evaluations` & `/`)

### 1. Loading Evaluations (GET)
- **Public Board**: Client calls `GET /api/evaluations`.
  - Server runs `Evaluation.find({ $or: [{ status: "approved" }, { status: { $exists: false } }] }).sort({ evaluatedAt: -1 }).limit(100).lean()`.
  - Returns verified live cards to display in the main scoreboard table.
- **My Submissions**: If a user is logged in, client calls `GET /api/evaluations?user=you@example.com`.
  - Server queries `Evaluation.find({ submittedByEmail: user })`.
  - Returns cards submitted by that user with status badges (**Pending Review**, **Approved**, or **Rejected**).

### 2. Submitting an Evaluation (POST)
- User clicks **"Submit a result"** or **"Add evaluation"**, fills in the modal form (`model`, `organization`, `benchmark`, `score`, `metric`, `category`, `source`).
- Submits form via `createEvaluation()` in `app/page.tsx`.
- Handler `POST /api/evaluations`:
  - Inserts card into MongoDB with `status: "pending"` and submitter's email.
  - Returns newly created document.
  - Client updates `userEvaluations` and switches category tab to **"My Submissions"**.

### Code Snippet (`app/api/evaluations/route.ts`)

```typescript
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
```

---

## 7. Flow 4: Model Advisor & Gemini Recommendation (`/api/recommendations`)

### The Flow
1. **User Description (`app/page.tsx`)**:
   - User opens **"Find my model"** dialog and enters a description (e.g. *"I need a fast reasoning model to debug and write python algorithms"*).
   - Calls `findModel()` which sends `POST /api/recommendations` with `{ work }`.
2. **Category Inference (`inferCategories`)**:
   - Evaluates keywords in the work text against category dictionaries (`Coding`, `Reasoning`, `Knowledge`, `Safety`).
3. **Database Candidate Aggregation**:
   - Reads evaluation cards from MongoDB.
   - Cleans names (strips legacy `Demo ·` prefixes).
   - Calculates average scores for each candidate model across matching categories and sorts descending.
4. **Gemini AI Recommendation**:
   - If `GEMINI_API_KEY` is present, sends candidate list to Google's Generative Language API (`models/gemini-2.5-flash:generateContent`) with `responseMimeType: "application/json"`.
   - Receives JSON response with `{ model, reason }`.
5. **Fallback Response**:
   - If Gemini is unavailable, rate-limited, or unconfigured, it immediately falls back to the top database match:
     `GPT-4.1 has the highest benchmark average (89.8%) in the relevant evaluation categories.`
6. **Modal Rendering**:
   - Displays the **Top Match Card**, average score percentage, concise reason text, and **Supporting Benchmarks** evidence list.

### Code Snippet (`app/api/recommendations/route.ts`)

```typescript
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
    } catch {}
  }

  return NextResponse.json({ recommendation: best, reason, candidates });
}
```

---

## 8. Flow 5: Admin Moderation Console (`/admin` & `/api/admin/*`)

### Security & Token Check (`lib/adminAuth.ts`)
- Admin actions are protected by `x-admin-token` header matching `ADMIN_SECRET_KEY`.
- Verified using `verifyAdminToken(request)`.

### 1. Admin Login
- Administrator logs in at `/admin`.
- Submits credentials to `POST /api/admin/auth`.
- If valid, returns `{ success: true, token, admin: { email, role } }`.
- Client saves `token` in `sessionStorage` (`evalboard_admin_token`).

### 2. Loading All Submissions (GET)
- Client calls `GET /api/admin/evaluations` with `x-admin-token`.
- Returns all evaluations regardless of status, plus live counts:
  `{ evaluations, counts: { total, pending, approved, rejected } }`.

### 3. Review Actions (PATCH & DELETE)
- **Approve / Reject**: Clicking **Approve** or **Reject** calls `PATCH /api/admin/evaluations` with `{ id, status: "approved" | "rejected" }`.
- **Delete**: Clicking the trash icon calls `DELETE /api/admin/evaluations?id=...`, which runs `Evaluation.findByIdAndDelete(id)`.

### Code Snippet (`app/api/admin/evaluations/route.ts`)

```typescript
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
```

---

## 9. Environment Settings & Setup

### Environment Variables (`.env`)

```dotenv
env
```

### Running Locally

```bash
# Install dependencies
npm install

# Start development server on port 3000
npm run dev

# Or build and run in production mode
npm run build
npm start
```
