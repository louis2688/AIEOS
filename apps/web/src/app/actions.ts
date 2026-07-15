"use server";

import { revalidatePath } from "next/cache";
import {
  createModel,
  createPipeline,
  createProject,
  createTask,
  deleteModel,
  deletePipeline,
  deleteProject,
  runPipeline,
  setDefaultModel,
  testModel,
} from "@/lib/aeios";
import { requireUser } from "@/lib/auth";
import type { PipelineStep } from "@/lib/types";

export async function runGoalAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

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
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

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
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

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

export async function createPipelineAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

  const name = String(formData.get("name") || "").trim();
  const description = String(formData.get("description") || "").trim();
  const projectId = String(formData.get("project_id") || "").trim() || null;
  const stepsRaw = String(formData.get("steps") || "[]");

  if (!name) {
    return { ok: false as const, error: "Name is required" };
  }

  let steps: PipelineStep[];
  try {
    steps = JSON.parse(stepsRaw) as PipelineStep[];
  } catch {
    return { ok: false as const, error: "Invalid steps payload" };
  }

  if (!Array.isArray(steps) || steps.length === 0) {
    return { ok: false as const, error: "Add at least one step" };
  }

  try {
    const pipeline = await createPipeline({
      name,
      description,
      project_id: projectId,
      steps,
    });
    revalidatePath("/pipelines");
    return { ok: true as const, pipeline };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to create pipeline",
    };
  }
}

export async function deletePipelineAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

  const id = String(formData.get("id") || "").trim();
  if (!id) return { ok: false as const, error: "Missing id" };
  try {
    await deletePipeline(id);
    revalidatePath("/pipelines");
    return { ok: true as const };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to delete pipeline",
    };
  }
}

export async function runPipelineAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

  const id = String(formData.get("id") || "").trim();
  const inputGoal = String(formData.get("input_goal") || "").trim();
  if (!id || !inputGoal) {
    return { ok: false as const, error: "Pipeline id and input goal are required" };
  }
  try {
    const run = await runPipeline(id, inputGoal);
    revalidatePath("/pipelines");
    revalidatePath(`/pipelines/${id}`);
    revalidatePath("/tasks");
    return { ok: true as const, run };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to run pipeline",
    };
  }
}

export async function createModelAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }

  const name = String(formData.get("name") || "").trim();
  const provider = String(formData.get("provider") || "").trim();
  const modelId = String(formData.get("model_id") || "").trim();
  const baseUrl = String(formData.get("base_url") || "").trim() || null;
  const apiKey = String(formData.get("api_key") || "").trim() || null;
  const isDefault = String(formData.get("is_default") || "") === "on";

  if (!name || !provider || !modelId) {
    return { ok: false as const, error: "Name, provider, and model id are required" };
  }

  try {
    const model = await createModel({
      name,
      provider,
      model_id: modelId,
      base_url: baseUrl,
      api_key: apiKey,
      is_default: isDefault,
    });
    revalidatePath("/models");
    revalidatePath("/");
    return { ok: true as const, model };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to create model",
    };
  }
}

export async function setDefaultModelAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }
  const id = String(formData.get("id") || "").trim();
  if (!id) return { ok: false as const, error: "Missing id" };
  try {
    const model = await setDefaultModel(id);
    revalidatePath("/models");
    revalidatePath("/");
    return { ok: true as const, model };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to set default",
    };
  }
}

export async function deleteModelAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }
  const id = String(formData.get("id") || "").trim();
  if (!id) return { ok: false as const, error: "Missing id" };
  try {
    await deleteModel(id);
    revalidatePath("/models");
    revalidatePath("/");
    return { ok: true as const };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Failed to delete model",
    };
  }
}

export async function testModelAction(formData: FormData) {
  try {
    await requireUser();
  } catch {
    return { ok: false as const, error: "Sign in required" };
  }
  const id = String(formData.get("id") || "").trim();
  if (!id) return { ok: false as const, error: "Missing id" };
  try {
    const result = await testModel(id);
    return { ok: true as const, reply: result.reply };
  } catch (err) {
    return {
      ok: false as const,
      error: err instanceof Error ? err.message : "Model test failed",
    };
  }
}
