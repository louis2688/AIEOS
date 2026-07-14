"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "@/components/AppShell";

export function PageFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  const isAuthPage =
    pathname.startsWith("/sign-in") || pathname.startsWith("/sign-up");

  if (isAuthPage) {
    return (
      <div className="relative min-h-full">
        <div className="pointer-events-none absolute inset-0 aeios-grid opacity-40" />
        <div className="relative mx-auto w-full max-w-6xl px-5 py-10">
          <p className="mb-8 text-center font-mono text-xs tracking-[0.22em] text-[var(--accent)] uppercase">
            AEIOS
          </p>
          {children}
        </div>
      </div>
    );
  }

  return <AppShell pathname={pathname}>{children}</AppShell>;
}
