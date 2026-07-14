"use server";

import { revalidatePath } from "next/cache";
import { createProject, createTask, deleteProject } from "@/lib/aeios";

export async function runGoalAction(formData: FormData) {
  const goal = String(formData.get("goal") || "").trim();
  const agent = String(formData.get("agent") || "").trim() || undefined;
  if (!goal) {
    return { ok: false as const, error: "Goal is required" };
  }
  try {
    const task = await createTask(goal, agent);
    revalidatePath("/");
    revalidatePath("/tasks");
    revalidatePath("/assistant");
    return { ok: true as const, task };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to run goal",
    };
  }
}

export async function createProjectAction(formData: FormData) {
  const name = String(formData.get("name") || "").trim();
  const description = String(formData.get("description") || "").trim();
  if (!name) {
    return { ok: false as const, error: "Name is required" };
  }
  try {
    const project = await createProject(name, description);
    revalidatePath("/projects");
    return { ok: true as const, project };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to create project",
    };
  }
}

export async function deleteProjectAction(formData: FormData) {
  const id = String(formData.get("id") || "").trim();
  if (!id) return { ok: false as const, error: "Missing id" };
  try {
    await deleteProject(id);
    revalidatePath("/projects");
    return { ok: true as const };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to delete",
    };
  }
}
