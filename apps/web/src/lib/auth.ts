import { auth } from "@clerk/nextjs/server";

/** Require a signed-in user for server actions / data mutations. */
export async function requireUser() {
  const { userId } = await auth();
  if (!userId) {
    throw new Error("Unauthorized — sign in required");
  }
  return userId;
}

/** Clerk session JWT for forwarding to the AEIOS FastAPI control plane. */
export async function getSessionToken(): Promise<string | null> {
  const session = await auth();
  if (!session.userId) {
    return null;
  }
  return session.getToken();
}
