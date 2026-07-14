"use client";

import { usePathname } from "next/navigation";
import { AppShell } from "@/components/AppShell";

export function PageFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/";
  return <AppShell pathname={pathname}>{children}</AppShell>;
}
