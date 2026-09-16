export type JobStatus = "queued" | "running" | "completed" | "failed";
export type Project = { project_id: string; name: string; current_version: number };
export type Job = { job_id: string; project_id: string; status: JobStatus; stage?: string; error?: string; version?: number; artifacts?: { glb: string; state: string } };
export type ModelState = { model_id: string; version: number; objects: Array<{ object_id: string; name: string; type: string; parameters: Record<string, unknown>; placement: { x: number; y: number; z: number } }>; feature_history: unknown[]; validation?: { status: string } };

export async function request<T>(base: string, path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${base}${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) }, ...init });
  if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
  return response.json() as Promise<T>;
}
