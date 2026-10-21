export const ADMIN_DEFAULT_EMAIL = "admin@evalboard.com";
export const ADMIN_DEFAULT_PASSWORD = "admin123";
export const ADMIN_SECRET_KEY = process.env.ADMIN_SECRET_KEY || "evalboard_secret_admin_session_key_2026";

export function checkAdminCredentials(email: string, pass: string): boolean {
  const configuredEmail = (process.env.ADMIN_EMAIL || ADMIN_DEFAULT_EMAIL).trim().toLowerCase();
  const configuredPassword = process.env.ADMIN_PASSWORD || ADMIN_DEFAULT_PASSWORD;
  return email.trim().toLowerCase() === configuredEmail && pass === configuredPassword;
}

export function verifyAdminToken(request: Request): boolean {
  const token = request.headers.get("x-admin-token") || request.headers.get("authorization")?.replace(/^Bearer\s+/i, "");
  return Boolean(token && token === ADMIN_SECRET_KEY);
}
