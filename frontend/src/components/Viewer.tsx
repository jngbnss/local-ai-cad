import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import { STLLoader } from "three/examples/jsm/loaders/STLLoader.js";
import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

interface ViewerProps {
  url: string | null;
  label?: string;
}

export function Viewer({ url, label = "3D 미리보기" }: ViewerProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !url) return;

    setLoadError(null);
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x101316);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100000);
    camera.up.set(0, url.toLowerCase().endsWith(".glb") ? 1 : 0, url.toLowerCase().endsWith(".glb") ? 0 : 1);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.screenSpacePanning = true;

    scene.add(new THREE.HemisphereLight(0xf7efe2, 0x34404b, 2.2));
    const key = new THREE.DirectionalLight(0xffffff, 3.6);
    key.position.set(3, -4, 6);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0x8fb7ff, 1.4);
    fill.position.set(-4, 2, 3);
    scene.add(fill);

    let object: THREE.Object3D | null = null;
    let frame = 0;
    let disposed = false;

    function resize() {
      const width = Math.max(host!.clientWidth, 1);
      const height = Math.max(host!.clientHeight, 1);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    }

    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    function frameObject(root: THREE.Object3D) {
      if (disposed) return;
      const box = new THREE.Box3().setFromObject(root);
      const center = box.getCenter(new THREE.Vector3());
      const size = box.getSize(new THREE.Vector3());
      const longest = Math.max(size.x, size.y, size.z, 1);
      root.position.sub(center);
      object = root;
      scene.add(root);
      const up = camera.up.y === 1;
      camera.position.set(longest * 1.4, up ? longest * 1.25 : -longest * 1.8, up ? longest * 1.8 : longest * 1.25);
      camera.near = longest / 1000;
      camera.far = longest * 100;
      camera.updateProjectionMatrix();
      controls.target.set(0, 0, 0);
      controls.update();
    }

    const onLoadError = (caught: unknown) => {
      setLoadError(caught instanceof Error ? caught.message : "3D 파일을 불러오지 못했습니다.");
    };
    if (url.toLowerCase().endsWith(".glb")) {
      new GLTFLoader().load(url, (gltf) => frameObject(gltf.scene), undefined, onLoadError);
    } else {
      new STLLoader().load(
        url,
        (geometry) => {
          if (disposed) {
            geometry.dispose();
            return;
          }
          geometry.computeVertexNormals();
          const material = new THREE.MeshStandardMaterial({
            color: 0xf2a65a,
            roughness: 0.48,
            metalness: 0.08,
          });
          const mesh = new THREE.Mesh(geometry, material);
          mesh.castShadow = true;
          frameObject(mesh);
        },
        undefined,
        onLoadError,
      );
    }

    function animate() {
      controls.update();
      renderer.render(scene, camera);
      frame = requestAnimationFrame(animate);
    }
    animate();

    return () => {
      disposed = true;
      cancelAnimationFrame(frame);
      observer.disconnect();
      controls.dispose();
      object?.traverse((child) => {
        if (!(child instanceof THREE.Mesh)) return;
        child.geometry.dispose();
        const materials = Array.isArray(child.material) ? child.material : [child.material];
        materials.forEach((material) => material.dispose());
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [url]);

  return (
    <section className="viewer" aria-label={label}>
      <div className="viewer__topline">
        <span>{label}</span>
        {url && <span className="viewer__hint">드래그 회전 · 휠 확대</span>}
      </div>
      <div ref={hostRef} className="viewer__canvas">
        {!url && (
          <div className="viewer__empty">
            <span className="viewer__axis">XYZ</span>
            <strong>설계가 아직 없습니다</strong>
            <p>왼쪽에서 원하는 물체와 치수를 자연어로 적어보세요.</p>
          </div>
        )}
        {loadError && <div className="viewer__error">미리보기 오류: {loadError}</div>}
      </div>
    </section>
  );
}
