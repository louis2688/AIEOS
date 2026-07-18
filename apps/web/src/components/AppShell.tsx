import { Sidebar } from "@/components/Sidebar";

const titles: Record<string, { title: string; blurb: string }> = {
  "/": {
    title: "Control",
    blurb: "Kernel status, run a goal, and recent task activity.",
  },
  "/assistant": {
    title: "Assistant",
    blurb: "Chat with the kernel — goals route through agents and tools.",
  },
  "/tasks": {
    title: "Tasks",
    blurb: "History of executed goals and their step traces.",
  },
  "/pipelines": {
    title: "Pipelines",
    blurb: "Multi-step workflows with run history.",
  },
  "/projects": {
    title: "Projects",
    blurb: "Workspace containers for engineering work.",
  },
  "/knowledge": {
    title: "Knowledge",
    blurb: "Search tasks, pipelines, projects, and memory.",
  },
  "/models": {
    title: "Models",
    blurb: "Provider registry for the planner-backed LLM path.",
  },
};

function pageMeta(pathname: string) {
  if (titles[pathname]) return titles[pathname];
  const base = Object.keys(titles)
    .filter((k) => k !== "/" && pathname.startsWith(k))
    .sort((a, b) => b.length - a.length)[0];
  if (base) return titles[base];
  if (pathname.startsWith("/tasks/")) {
    return { title: "Task detail", blurb: "Plan, steps, result, and artifacts." };
  }
  if (pathname.startsWith("/pipelines/")) {
    return { title: "Pipeline detail", blurb: "Run the workflow and inspect history." };
  }
  return { title: "AEIOS", blurb: "Kernel-backed control plane." };
}

export function AppShell({
  children,
  pathname,
}: {
  children: React.ReactNode;
  pathname: string;
}) {
  const meta = pageMeta(pathname);

  return (
    <div className="shell">
      <div className="pointer-events-none absolute inset-0 aeios-grid opacity-35" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-64 aeios-glow" />
      <Sidebar pathname={pathname} />
      <div className="shell-main">
        <header className="shell-header">
          <div>
            <p className="shell-kicker">AEIOS</p>
            <h1 className="shell-title">{meta.title}</h1>
            <p className="shell-blurb">{meta.blurb}</p>
          </div>
        </header>
        <main className="shell-content">{children}</main>
      </div>
    </div>
  );
}
