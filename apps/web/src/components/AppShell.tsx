import Link from "next/link";
import { UserMenu } from "@/components/UserMenu";

const links = [
  { href: "/", label: "Control" },
  { href: "/tasks", label: "Tasks" },
  { href: "/pipelines", label: "Pipelines" },
  { href: "/knowledge", label: "Knowledge" },
  { href: "/models", label: "Models" },
  { href: "/assistant", label: "Assistant" },
  { href: "/projects", label: "Projects" },
];

export function AppShell({
  children,
  pathname,
}: {
  children: React.ReactNode;
  pathname: string;
}) {
  return (
    <div className="relative min-h-full">
      <div className="pointer-events-none absolute inset-0 aeios-grid opacity-40" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-56 aeios-glow" />
      <div className="relative mx-auto flex min-h-full w-full max-w-6xl flex-col px-5 py-6 md:px-8">
        <header className="mb-8 flex flex-col gap-5 border-b border-[var(--line)] pb-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="font-mono text-xs tracking-[0.22em] text-[var(--accent)] uppercase">
              AEIOS
            </p>
            <h1 className="mt-1 font-display text-3xl tracking-tight text-[var(--ink)] md:text-4xl">
              Engineering OS
            </h1>
            <p className="mt-2 max-w-xl text-sm text-[var(--muted)]">
              Kernel-backed control plane for agents, tasks, and project memory.
            </p>
          </div>
          <div className="flex flex-col items-start gap-3 md:items-end">
            <UserMenu />
            <nav className="flex flex-wrap gap-2">
              {links.map((link) => {
                const active =
                  link.href === "/"
                    ? pathname === "/"
                    : pathname.startsWith(link.href);
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`rounded-md px-3 py-1.5 font-mono text-xs tracking-wide uppercase transition ${
                      active
                        ? "bg-[var(--accent)] text-[#102014]"
                        : "border border-[var(--line)] text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--ink)]"
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </nav>
          </div>
        </header>
        <main className="flex-1 pb-10">{children}</main>
      </div>
    </div>
  );
}
