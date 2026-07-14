import { AssistantClient } from "@/components/AssistantClient";
import { getStatus } from "@/lib/aeios";

export default async function AssistantPage() {
  let agents = ["software_engineer", "architect", "echo"];
  try {
    const status = await getStatus();
    if (status.agents?.length) agents = status.agents;
  } catch {
    // keep defaults
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-[var(--ink)]">Assistant</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Chat-style interface over the same kernel task syscalls.
        </p>
      </div>
      <AssistantClient agents={agents} />
    </div>
  );
}
