import mongoose, { Schema } from "mongoose";

const EvaluationSchema = new Schema({
  model: { type: String, required: true, trim: true, maxlength: 100 },
  organization: { type: String, required: true, trim: true, maxlength: 100 },
  benchmark: { type: String, required: true, trim: true, maxlength: 120 },
  score: { type: Number, required: true, min: 0, max: 100 },
  metric: { type: String, required: true, trim: true, maxlength: 60 },
  category: { type: String, required: true, enum: ["Reasoning", "Coding", "Knowledge", "Safety"] },
  source: { type: String, trim: true, maxlength: 300, default: "" },
  status: { type: String, enum: ["pending", "approved", "rejected"], default: "pending" },
  submittedBy: { type: String, trim: true, maxlength: 100, default: "anonymous" },
  submittedByEmail: { type: String, trim: true, lowercase: true, maxlength: 120, default: "" },
  reviewedAt: { type: Date },
  reviewedBy: { type: String, trim: true, default: "" },
  evaluatedAt: { type: Date, default: Date.now },
}, { timestamps: true });

export default mongoose.models.Evaluation || mongoose.model("Evaluation", EvaluationSchema);
