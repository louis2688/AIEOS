import { PipelineForm } from "@/components/PipelineForm";
import { PipelineList } from "@/components/PipelineList";
import { getStatus, listPipelines, listProjects } from "@/lib/aeios";
import type { Pipeline, Project } from "@/lib/types";

export default async function PipelinesPage() {
  let pipelines: Pipeline[] = [];
  let projects: Project[] = [];
  let agents = ["software_engineer", "architect", "echo"];

  try {
    const [p, proj, status] = await Promise.all([
      listPipelines(50),
      listProjects(50),
      getStatus(),
    ]);
    pipelines = p;
    projects = proj;
    if (status.agents?.length) agents = status.agents;
  } catch {
    // API offline — empty state
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-[var(--ink)]">Pipelines</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Multi-step agent workflows executed by the kernel.
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
        <PipelineForm projects={projects} agents={agents} />
        <PipelineList pipelines={pipelines} />
      </div>
    </div>
  );
}
