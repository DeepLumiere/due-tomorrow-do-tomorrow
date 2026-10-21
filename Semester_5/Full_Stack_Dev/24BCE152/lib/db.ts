import mongoose from "mongoose";

const MONGODB_URI =
  process.env.MONGODB_URI ||
  "mongodb://jeelpadsala15_db_user:Mongo%40Pass@ac-avawqsa-shard-00-00.dwk4i6x.mongodb.net:27017,ac-avawqsa-shard-00-01.dwk4i6x.mongodb.net:27017,ac-avawqsa-shard-00-02.dwk4i6x.mongodb.net:27017/evalution?ssl=true&authSource=admin&replicaSet=atlas-12luut-shard-0&retryWrites=true&w=majority&tlsAllowInvalidCertificates=true";

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
