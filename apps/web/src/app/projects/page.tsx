import { ProjectForm } from "@/components/ProjectForm";
import { ProjectList } from "@/components/ProjectList";
import { listProjects } from "@/lib/aeios";
import type { Project } from "@/lib/types";

export default async function ProjectsPage() {
  let projects: Project[] = [];
  try {
    projects = await listProjects(50);
  } catch {
    projects = [];
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
      <ProjectForm />
      <ProjectList projects={projects} />
    </div>
  );
}
