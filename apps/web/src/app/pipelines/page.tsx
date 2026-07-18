import Link from "next/link";
import { PipelineForm } from "@/components/PipelineForm";
import { PipelineList } from "@/components/PipelineList";
import { getStatus, listPipelines, listProjects } from "@/lib/aeios";
import type { Pipeline, Project } from "@/lib/types";

export default async function PipelinesPage({
  searchParams,
}: {
  searchParams: Promise<{ template?: string }>;
}) {
  const params = await searchParams;
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

  const applyStarter = params.template === "starter";

  return (
    <div className="space-y-5">
      <div>
        <h2 className="font-display text-2xl text-[var(--ink)]">Pipelines</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          Multi-step agent workflows executed by the kernel.
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-[0.95fr_1.05fr]">
        <PipelineForm
          projects={projects}
          agents={agents}
          applyStarter={applyStarter}
        />
        {pipelines.length === 0 ? (
          <section className="panel">
            <h2 className="panel-title">Pipelines</h2>
            <p className="mt-3 text-sm text-[var(--muted)]">
              No pipelines yet. Prefill a ready-made architect → engineer → echo
              flow and run it from the dashboard.
            </p>
            <Link
              href="/pipelines?template=starter#new-pipeline"
              className="btn-primary mt-4"
            >
              Use starter template
            </Link>
          </section>
        ) : (
          <PipelineList pipelines={pipelines} />
        )}
      </div>
    </div>
  );
}
