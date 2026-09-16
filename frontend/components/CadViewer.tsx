"use client";

import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

type Selected = { name: string; metadata: Record<string, unknown> } | null;

export function CadViewer({ url, onSelection }: { url?: string; onSelection: (selection: Selected) => void }) {
  const host = useRef<HTMLDivElement>(null);
  const reset = useRef<() => void>(() => undefined);
  const [status, setStatus] = useState("Waiting for a generated model");

  useEffect(() => {
    if (!host.current) return;
    const element = host.current;
    const scene = new THREE.Scene(); scene.background = new THREE.Color("#08111f");
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100000); camera.position.set(180, 180, 140);
    const renderer = new THREE.WebGLRenderer({ antialias: true }); renderer.setPixelRatio(window.devicePixelRatio); element.appendChild(renderer.domElement);
    const controls = new OrbitControls(camera, renderer.domElement); controls.enableDamping = true; controls.screenSpacePanning = true;
    scene.add(new THREE.HemisphereLight(0xe5f1ff, 0x182335, 2)); const light = new THREE.DirectionalLight(0xffffff, 2.5); light.position.set(100, 160, 100); scene.add(light);
    const grid = new THREE.GridHelper(400, 20, 0x31506e, 0x183048); scene.add(grid);
    const raycaster = new THREE.Raycaster(); const pointer = new THREE.Vector2(); let root: THREE.Object3D | undefined; let selected: THREE.Mesh | undefined; let original: THREE.Color | undefined;
    const fit = () => { if (!root) return; const box = new THREE.Box3().setFromObject(root); const size = box.getSize(new THREE.Vector3()).length() || 100; const center = box.getCenter(new THREE.Vector3()); camera.position.copy(center).add(new THREE.Vector3(size, size, size)); controls.target.copy(center); camera.near = size / 100; camera.far = size * 100; camera.updateProjectionMatrix(); controls.update(); };
    reset.current = fit;
    const resize = () => { const { width, height } = element.getBoundingClientRect(); renderer.setSize(width, height); camera.aspect = width / Math.max(height, 1); camera.updateProjectionMatrix(); };
    const select = (event: PointerEvent) => { const rect = renderer.domElement.getBoundingClientRect(); pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1); raycaster.setFromCamera(pointer, camera); const mesh = raycaster.intersectObjects(scene.children, true).find(hit => (hit.object as THREE.Mesh).isMesh)?.object as THREE.Mesh | undefined; if (selected && original) (selected.material as THREE.MeshStandardMaterial).color.copy(original); selected = mesh; original = mesh ? (mesh.material as THREE.MeshStandardMaterial).color.clone() : undefined; if (mesh) { (mesh.material as THREE.MeshStandardMaterial).color.set("#fbbf24"); onSelection({ name: mesh.name || "CAD object", metadata: (mesh.userData ?? {}) as Record<string, unknown> }); } else onSelection(null); };
    resize(); window.addEventListener("resize", resize); renderer.domElement.addEventListener("pointerdown", select);
    let frame = 0; const animate = () => { frame = requestAnimationFrame(animate); controls.update(); renderer.render(scene, camera); }; animate();
    if (url) { setStatus("Loading GLB…"); new GLTFLoader().load(url, gltf => { root = gltf.scene; scene.add(root); setStatus(""); fit(); }, undefined, error => setStatus(`Could not load GLB: ${error instanceof Error ? error.message : "Unknown loader error"}`)); }
    return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); renderer.domElement.removeEventListener("pointerdown", select); controls.dispose(); renderer.dispose(); element.removeChild(renderer.domElement); };
  }, [url, onSelection]);

  return <section className="viewer"><div ref={host} className="canvas" /><div className="viewer-status">{status}</div><button className="secondary viewer-reset" onClick={() => reset.current()}>Fit / reset camera</button></section>;
}
