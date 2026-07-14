import { auth } from "@clerk/nextjs/server";

/** Require a signed-in user for server actions / data mutations. */
export async function requireUser() {
  const { userId } = await auth();
  if (!userId) {
    throw new Error("Unauthorized — sign in required");
  }
  return userId;
}
