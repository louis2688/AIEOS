"use client";

import { SignInButton, UserButton, useAuth } from "@clerk/nextjs";

export function UserMenu() {
  const { isSignedIn, isLoaded } = useAuth();

  if (!isLoaded) {
    return (
      <span className="font-mono text-[10px] tracking-wide text-[var(--muted)] uppercase">
        …
      </span>
    );
  }

  if (!isSignedIn) {
    return (
      <SignInButton mode="modal">
        <button
          type="button"
          className="rounded-md border border-[var(--line)] bg-[var(--panel)] px-3 py-1.5 font-mono text-xs tracking-wide text-[var(--muted)] uppercase transition hover:border-[var(--accent)] hover:text-[var(--ink)]"
        >
          Sign in
        </button>
      </SignInButton>
    );
  }

  return (
    <UserButton
      appearance={{
        elements: {
          avatarBox: "h-8 w-8",
        },
      }}
    />
  );
}
