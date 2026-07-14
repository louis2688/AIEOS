import Link from "next/link";
import { notFound } from "next/navigation";
import { PipelineRunViewer } from "@/components/PipelineRunViewer";
import { RunPipelineForm } from "@/components/RunPipelineForm";
import { getPipeline, listPipelineRuns } from "@/lib/aeios";
import type { Pipeline, PipelineRun } from "@/lib/types";

export default async function PipelineDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let pipeline: Pipeline;
  let runs: PipelineRun[] = [];
  try {
    [pipeline, runs] = await Promise.all([getPipeline(id), listPipelineRuns(id, 20)]);
  } catch {
    notFound();
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] tracking-widest text-[var(--accent)] uppercase">
            Pipeline
          </p>
          <h2 className="font-display text-2xl text-[var(--ink)]">{pipeline.name}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {pipeline.description || "No description"}
          </p>
        </div>
        <Link
          href="/pipelines"
          className="font-mono text-xs text-[var(--muted)] hover:text-[var(--ink)]"
        >
          ← Back
        </Link>
      </div>

      <section className="panel">
        <h3 className="panel-title">Steps</h3>
        <ol className="mt-4 space-y-2">
          {pipeline.steps.map((step, index) => (
            <li
              key={`${step.agent}-${index}`}
              className="rounded-md border border-[var(--line)] px-3 py-2"
            >
              <p className="font-mono text-[10px] text-[var(--muted)] uppercase">
                Step {index + 1} · {step.agent}
              </p>
              <p className="mt-1 text-sm text-[var(--ink)]">{step.goal}</p>
            </li>
          ))}
        </ol>
      </section>

      <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
        <RunPipelineForm pipelineId={pipeline.id} />
        <PipelineRunViewer runs={runs} />
      </div>
    </div>
  );
}
