"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CadViewer } from "./CadViewer";
import { Job, ModelState, Project, request } from "./api";

const newKey = () => crypto.randomUUID();

export function CadStudio({ apiBaseUrl }: { apiBaseUrl: string }) {
  const [project, setProject] = useState<Project>();
  const [job, setJob] = useState<Job>();
  const [state, setState] = useState<ModelState>();
  const [selection, setSelection] = useState<{ name: string; metadata: Record<string, unknown> } | null>(null);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ name: "New plant model", model_type: "plant", facility_name: "Plant Alpha", length: "120", width: "80", height: "30", units: "mm", room_or_zone: "Production zone", equipment_requirements: "", material: "Steel", additional_instruction: "" });
  const change = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => setForm(current => ({ ...current, [key]: event.target.value }));
  const loadState = useCallback(async (p: Project, version: number) => setState(await request<ModelState>(apiBaseUrl, `/api/cad/projects/${p.project_id}/versions/${version}/metadata`)), [apiBaseUrl]);

  useEffect(() => {
    if (!job || !project || job.status === "completed" || job.status === "failed") return;
    const poll = window.setInterval(async () => { try { const next = await request<Job>(apiBaseUrl, `/api/cad/jobs/${job.job_id}`); setJob(next); if (next.status === "completed" && next.version) { setProject(current => current ? { ...current, current_version: next.version! } : current); await loadState(project, next.version); } } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to refresh job"); } }, 1500);
    return () => window.clearInterval(poll);
  }, [apiBaseUrl, job, loadState, project]);

  async function createProject() { setError(""); setCreating(true); try { const created = await request<Project>(apiBaseUrl, "/api/cad/projects", { method: "POST", body: JSON.stringify({ name: form.name }) }); setProject(created); setJob(undefined); setState(undefined); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to create project"); } finally { setCreating(false); } }
  async function submit(event: FormEvent) { event.preventDefault(); if (!project) return void setError("Create a project first."); setError(""); try { const payload = { fixed_inputs: { model_type: form.model_type, facility_name: form.facility_name || undefined, length: Number(form.length), width: Number(form.width), height: Number(form.height), units: form.units, room_or_zone: form.room_or_zone || undefined, equipment_requirements: form.equipment_requirements || undefined, material: form.material || undefined }, additional_instruction: form.additional_instruction, base_version: project.current_version, idempotency_key: newKey() }; setJob(await request<Job>(apiBaseUrl, `/api/cad/projects/${project.project_id}/generate`, { method: "POST", body: JSON.stringify(payload) })); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to submit model generation"); } }
  const glbUrl = job?.status === "completed" ? `${apiBaseUrl}${job.artifacts?.glb}` : undefined;

  return <div className="studio">
    <header><div><p className="eyebrow">CADPILOT / TEXT-TO-CAD</p><h1>Interactive plant viewer</h1></div><div className={`badge ${job?.status ?? "idle"}`}>{job?.status ?? "idle"}</div></header>
    <div className="layout">
      <form className="panel form" onSubmit={submit}><div className="panel-head"><h2>Project & model</h2><button type="button" className="secondary" onClick={createProject} disabled={creating}>{creating ? "Creating…" : "New project"}</button></div><label>Project name<input value={form.name} onChange={change("name")} required /></label><p className="hint">{project ? `${project.project_id} · version ${project.current_version}` : "No project created"}</p><h2>Model requirements</h2><div className="grid"><label>Model type<input value={form.model_type} onChange={change("model_type")} required /></label><label>Facility name<input value={form.facility_name} onChange={change("facility_name")} /></label><label>Length<input type="number" min="0.01" step="any" value={form.length} onChange={change("length")} required /></label><label>Width<input type="number" min="0.01" step="any" value={form.width} onChange={change("width")} required /></label><label>Height<input type="number" min="0.01" step="any" value={form.height} onChange={change("height")} required /></label><label>Units<select value={form.units} onChange={change("units")}><option>mm</option><option>cm</option><option>m</option><option>in</option><option>ft</option></select></label></div><label>Room or zone<input value={form.room_or_zone} onChange={change("room_or_zone")} /></label><label>Equipment requirements<textarea value={form.equipment_requirements} onChange={change("equipment_requirements")} rows={2} /></label><label>Material<input value={form.material} onChange={change("material")} /></label><label>Additional instructions<textarea value={form.additional_instruction} onChange={change("additional_instruction")} rows={4} placeholder="Create a cylindrical storage tank on the left…" /></label><button className="primary" disabled={!project || !!job && ["queued", "running"].includes(job.status)}>Generate model</button>{job && <p className="hint">Job {job.job_id}<br />{job.stage}</p>}{error && <p className="error">{error}</p>}</form>
      <div className="right"><CadViewer url={glbUrl} onSelection={setSelection} /><section className="panel state"><div className="panel-head"><h2>Model state</h2>{project && <button type="button" className="secondary" onClick={() => project.current_version && loadState(project, project.current_version)}>Refresh</button>}</div><pre>{state ? JSON.stringify(state, null, 2) : "The authoritative FreeCAD state will appear here."}</pre></section>{selection && <section className="panel selected"><h2>Selected object</h2><p>{selection.name}</p><pre>{JSON.stringify(selection.metadata, null, 2)}</pre><button className="secondary" onClick={() => setSelection(null)}>Clear selection</button></section>}</div>
    </div>
  </div>;
}
