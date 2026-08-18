import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { LocateFixed, RotateCcw, X } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import { formatMetric, formatSeconds } from "../../lib/formatters";
import {
  buildIndustrialTimeline,
  buildIndustrialSceneState,
  healthStateSceneLabel,
  supportsWebGL,
} from "../../lib/visualization3d";
import type {
  IndustrialSceneSelection,
  IndustrialTimelineMarker,
  IndustrialTimelineModel,
  IndustrialTimelinePoint,
} from "../../lib/visualization3d";
import type { RunVisualizationData, TemporalRunSeries } from "../../types";
import { WebGLFallback } from "./WebGLFallback";

const CAMERA_POSITION = new THREE.Vector3(4.4, 3.1, 5.4);
const CAMERA_TARGET = new THREE.Vector3(0, 0.75, 0);

export function IndustrialScene3D({
  data,
  run,
}: {
  data: RunVisualizationData;
  run: TemporalRunSeries;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const [hoveredSelection, setHoveredSelection] =
    useState<IndustrialSceneSelection | null>(null);
  const [pinnedSelection, setPinnedSelection] =
    useState<IndustrialSceneSelection | null>(null);
  const [webGlAvailable, setWebGlAvailable] = useState<boolean | null>(null);
  const sceneState = useMemo(
    () => buildIndustrialSceneState(data, run),
    [data, run],
  );
  const timeline = useMemo(() => buildIndustrialTimeline(run), [run]);
  const sceneStyle = {
    "--scene-state-color": sceneState.cssColor,
  } as CSSProperties;
  const activeSelection = pinnedSelection ?? hoveredSelection;

  const resetCamera = useCallback(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) {
      return;
    }
    camera.position.copy(CAMERA_POSITION);
    controls.target.copy(CAMERA_TARGET);
    controls.update();
    setPinnedSelection(null);
  }, []);

  const focusMarker = useCallback((marker: IndustrialTimelineMarker) => {
    setPinnedSelection(markerSelection(marker));
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) {
      return;
    }
    const target = new THREE.Vector3(marker.x, 0.95, marker.z);
    controls.target.copy(target);
    camera.position.set(marker.x + 2.3, 2.35, marker.z + 2.75);
    controls.update();
  }, []);

  useEffect(() => {
    setWebGlAvailable(supportsWebGL());
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || webGlAvailable !== true) {
      return undefined;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf5f7fa);

    const camera = new THREE.PerspectiveCamera(44, 1, 0.1, 100);
    camera.position.copy(CAMERA_POSITION);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.maxDistance = 8.5;
    controls.maxPolarAngle = Math.PI * 0.48;
    controls.minDistance = 3.2;
    controls.target.copy(CAMERA_TARGET);
    controlsRef.current = controls;

    const interactiveObjects: THREE.Object3D[] = [];
    const machineGroup = createIndustrialMachine(sceneState.threeColor);
    const temporalTimeline = createTemporalTimeline(timeline);
    temporalTimeline.traverse((child) => {
      if (selectionFromObject(child)) {
        interactiveObjects.push(child);
      }
    });
    scene.add(machineGroup);
    scene.add(temporalTimeline);
    scene.add(createIndustrialRoom());
    scene.add(createLights(sceneState.threeColor));

    const resize = () => {
      const { height, width } = container.getBoundingClientRect();
      const safeWidth = Math.max(1, width);
      const safeHeight = Math.max(1, height);
      renderer.setSize(safeWidth, safeHeight, false);
      camera.aspect = safeWidth / safeHeight;
      camera.updateProjectionMatrix();
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(container);
    resize();

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let hoverId = "";
    let pointerDown: { x: number; y: number } | null = null;

    const pickObject = (event: PointerEvent) => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      return raycaster.intersectObjects(interactiveObjects, false)[0]?.object ?? null;
    };

    const updateHover = (selection: IndustrialSceneSelection | null) => {
      const nextId = selection ? selectionId(selection) : "";
      if (nextId === hoverId) {
        return;
      }
      hoverId = nextId;
      setHoveredSelection(selection);
    };

    const handlePointerMove = (event: PointerEvent) => {
      const object = pickObject(event);
      const selection = object ? selectionFromObject(object) : null;
      renderer.domElement.style.cursor = selection ? "pointer" : "grab";
      updateHover(selection);
    };

    const handlePointerDown = (event: PointerEvent) => {
      pointerDown = { x: event.clientX, y: event.clientY };
    };

    const handlePointerUp = (event: PointerEvent) => {
      if (!pointerDown) {
        return;
      }
      const moved = Math.hypot(event.clientX - pointerDown.x, event.clientY - pointerDown.y);
      pointerDown = null;
      if (moved > 6) {
        return;
      }
      const object = pickObject(event);
      setPinnedSelection(object ? selectionFromObject(object) : null);
    };

    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);

    const clock = new THREE.Clock();
    let animationFrame = 0;
    const animate = () => {
      const elapsed = clock.getElapsedTime();
      machineGroup.rotation.y = Math.sin(elapsed * 0.32) * 0.05;
      const beacon = machineGroup.getObjectByName("status-beacon");
      if (beacon) {
        const pulse = 1 + Math.sin(elapsed * 2.4) * 0.08;
        beacon.scale.setScalar(pulse);
      }
      controls.update();
      renderer.render(scene, camera);
      animationFrame = window.requestAnimationFrame(animate);
    };
    animate();

    return () => {
      window.cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      renderer.domElement.style.cursor = "";
      controls.dispose();
      disposeObject(scene);
      renderer.dispose();
      renderer.domElement.remove();
      cameraRef.current = null;
      controlsRef.current = null;
    };
  }, [sceneState.threeColor, timeline, webGlAvailable]);

  if (webGlAvailable === false) {
    return (
      <WebGLFallback message="El navegador o la sesion actual no expone WebGL." />
    );
  }

  if (timeline.visiblePoints === 0) {
    return (
      <IndustrialSceneEmptyState
        modelName={sceneState.modelName}
        runId={data.run_id}
      />
    );
  }

  return (
    <div className="industrial-scene-shell" style={sceneStyle}>
      <div
        aria-label={`Sala 3D industrial para ${data.run_id}`}
        className="industrial-scene-canvas"
        ref={containerRef}
        role="img"
      />
      <div className="industrial-scene-overlay">
        <div className="industrial-scene-title">
          <span>{sceneState.dataset}</span>
          <strong>{sceneState.modelName}</strong>
        </div>
        <dl className="industrial-scene-stats">
          <div>
            <dt>estado</dt>
            <dd>{healthStateSceneLabel(sceneState.healthState)}</dd>
          </div>
          <div>
            <dt>salud</dt>
            <dd>{formatMetric(sceneState.health)}</dd>
          </div>
          <div>
            <dt>riesgo</dt>
            <dd>{formatMetric(sceneState.risk)}</dd>
          </div>
          <div>
            <dt>ventanas</dt>
            <dd>{timeline.visiblePoints}/{timeline.totalPoints}</dd>
          </div>
          <div>
            <dt>alertas</dt>
            <dd>{run.alert_points}</dd>
          </div>
          <div>
            <dt>marcadores</dt>
            <dd>{timeline.markers.length}</dd>
          </div>
        </dl>
        <button
          aria-label="Recentrar camara"
          className="icon-button industrial-scene-reset"
          onClick={resetCamera}
          title="Recentrar camara"
          type="button"
        >
          <RotateCcw size={16} />
        </button>
        <div className="industrial-scene-legend">
          <span><i className="nominal" /> nominal</span>
          <span><i className="watch" /> vigilancia</span>
          <span><i className="warning" /> alerta</span>
          <span><i className="critical" /> critico</span>
          <span><i className="marker first" /> primer pico</span>
          <span><i className="marker persistent" /> sostenido</span>
          <span><i className="marker failure" /> final registrado</span>
        </div>
        <IndustrialMarkerActions
          markers={timeline.markers}
          onFocus={focusMarker}
        />
        <IndustrialSelectionPanel
          onClear={() => setPinnedSelection(null)}
          pinned={pinnedSelection !== null}
          selection={activeSelection}
        />
      </div>
    </div>
  );
}

function IndustrialSceneEmptyState({
  modelName,
  runId,
}: {
  modelName: string;
  runId: string;
}) {
  return (
    <div className="industrial-scene-empty">
      <LocateFixed size={18} />
      <span>{modelName}</span>
      <strong>Sin puntos temporales 3D</strong>
      <p>
        La run {runId} no trae ventanas temporales suficientes para construir la
        escena industrial.
      </p>
    </div>
  );
}

function IndustrialMarkerActions({
  markers,
  onFocus,
}: {
  markers: IndustrialTimelineMarker[];
  onFocus: (marker: IndustrialTimelineMarker) => void;
}) {
  if (markers.length === 0) {
    return null;
  }

  return (
    <div className="industrial-marker-actions" aria-label="Enfoque de marcadores">
      {markers.map((marker) => (
        <button
          className={`industrial-marker-action ${marker.kind}`}
          key={marker.kind}
          onClick={() => onFocus(marker)}
          title={`Enfocar ${markerKindLabel(marker.kind)}`}
          type="button"
        >
          <LocateFixed size={13} />
          <span>{markerKindLabel(marker.kind)}</span>
        </button>
      ))}
    </div>
  );
}

function IndustrialSelectionPanel({
  onClear,
  pinned,
  selection,
}: {
  onClear: () => void;
  pinned: boolean;
  selection: IndustrialSceneSelection | null;
}) {
  if (!selection) {
    return (
      <div className="industrial-scene-selection muted">
        <span>seleccion</span>
        <strong>sin punto activo</strong>
      </div>
    );
  }

  if (selection.kind === "marker") {
    return (
      <div className="industrial-scene-selection">
        <SelectionHeader
          pinned={pinned}
          title={selection.markerLabel}
          onClear={onClear}
        />
        <dl>
          <div>
            <dt>tipo</dt>
            <dd>{markerKindLabel(selection.markerKind)}</dd>
          </div>
          <div>
            <dt>x</dt>
            <dd>{formatMetric(selection.temporalX)}</dd>
          </div>
          <div>
            <dt>lead</dt>
            <dd>{formatSeconds(selection.timeToFailureSeconds)}</dd>
          </div>
        </dl>
      </div>
    );
  }

  return (
    <div className="industrial-scene-selection">
      <SelectionHeader
        pinned={pinned}
        title={selection.windowId}
        onClear={onClear}
      />
      <dl>
        <div>
          <dt>estado</dt>
          <dd>{healthStateSceneLabel(selection.state)}</dd>
        </div>
        <div>
          <dt>salud</dt>
          <dd>{formatMetric(selection.health)}</dd>
        </div>
        <div>
          <dt>riesgo</dt>
          <dd>{formatMetric(selection.risk)}</dd>
        </div>
        <div>
          <dt>score</dt>
          <dd>{formatMetric(selection.score)}</dd>
        </div>
        <div>
          <dt>x</dt>
          <dd>{formatMetric(selection.temporalX)}</dd>
        </div>
        <div>
          <dt>lead</dt>
          <dd>{formatSeconds(selection.timeToFailureSeconds)}</dd>
        </div>
      </dl>
      <p>{selection.stateReason}</p>
    </div>
  );
}

function SelectionHeader({
  onClear,
  pinned,
  title,
}: {
  onClear: () => void;
  pinned: boolean;
  title: string;
}) {
  return (
    <div className="industrial-selection-head">
      <div>
        <span>{pinned ? "fijado" : "hover"}</span>
        <strong>{title}</strong>
      </div>
      {pinned ? (
        <button
          aria-label="Liberar seleccion"
          className="icon-button"
          onClick={onClear}
          title="Liberar seleccion"
          type="button"
        >
          <X size={14} />
        </button>
      ) : null}
    </div>
  );
}

function createIndustrialRoom() {
  const room = new THREE.Group();
  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(7.2, 5),
    new THREE.MeshStandardMaterial({
      color: 0xe7edf4,
      metalness: 0,
      roughness: 0.82,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  room.add(floor);

  const wall = new THREE.Mesh(
    new THREE.BoxGeometry(7.2, 2.5, 0.08),
    new THREE.MeshStandardMaterial({
      color: 0xf9fbfd,
      metalness: 0,
      roughness: 0.78,
    }),
  );
  wall.position.set(0, 1.25, -2.45);
  wall.receiveShadow = true;
  room.add(wall);

  const grid = new THREE.GridHelper(7.2, 12, 0x9fb3c8, 0xd3dce7);
  grid.position.y = 0.01;
  room.add(grid);

  return room;
}

function createIndustrialMachine(statusColor: number) {
  const group = new THREE.Group();
  group.position.y = 0.05;

  const baseMaterial = new THREE.MeshStandardMaterial({
    color: 0x223044,
    metalness: 0.18,
    roughness: 0.56,
  });
  const metalMaterial = new THREE.MeshStandardMaterial({
    color: 0x8394a8,
    metalness: 0.42,
    roughness: 0.38,
  });
  const statusMaterial = new THREE.MeshStandardMaterial({
    color: statusColor,
    emissive: statusColor,
    emissiveIntensity: 0.55,
    metalness: 0.1,
    roughness: 0.28,
  });

  const skid = new THREE.Mesh(new THREE.BoxGeometry(4.1, 0.22, 1.1), baseMaterial);
  skid.position.y = 0.22;
  skid.castShadow = true;
  skid.receiveShadow = true;
  group.add(skid);

  [-1.45, 1.45].forEach((x) => {
    const bearing = new THREE.Mesh(
      new THREE.BoxGeometry(0.58, 0.9, 0.82),
      baseMaterial,
    );
    bearing.position.set(x, 0.75, 0);
    bearing.castShadow = true;
    bearing.receiveShadow = true;
    group.add(bearing);
  });

  const shaft = new THREE.Mesh(
    new THREE.CylinderGeometry(0.22, 0.22, 3.35, 40),
    metalMaterial,
  );
  shaft.rotation.z = Math.PI / 2;
  shaft.position.y = 0.82;
  shaft.castShadow = true;
  group.add(shaft);

  const rotor = new THREE.Mesh(
    new THREE.TorusGeometry(0.66, 0.07, 16, 72),
    metalMaterial,
  );
  rotor.rotation.y = Math.PI / 2;
  rotor.position.set(0, 0.82, 0);
  rotor.castShadow = true;
  group.add(rotor);

  const beacon = new THREE.Mesh(new THREE.SphereGeometry(0.15, 28, 16), statusMaterial);
  beacon.name = "status-beacon";
  beacon.position.set(0, 1.55, 0.2);
  beacon.castShadow = true;
  group.add(beacon);

  const beaconLight = new THREE.PointLight(statusColor, 1.2, 3.2);
  beaconLight.position.copy(beacon.position);
  group.add(beaconLight);

  return group;
}

function createTemporalTimeline(timeline: IndustrialTimelineModel) {
  const group = new THREE.Group();
  group.name = "temporal-timeline";

  const rail = new THREE.Mesh(
    new THREE.BoxGeometry(6.7, 0.055, 0.12),
    new THREE.MeshStandardMaterial({
      color: 0xcbd5e1,
      metalness: 0.08,
      roughness: 0.7,
    }),
  );
  rail.position.set(0, 0.06, 1.42);
  rail.receiveShadow = true;
  group.add(rail);

  for (const point of timeline.points) {
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.045, point.height, 0.24),
      new THREE.MeshStandardMaterial({
        color: point.threeColor,
        emissive: point.threeColor,
        emissiveIntensity: point.state === "critical" ? 0.26 : point.state === "warning" ? 0.16 : 0.04,
        metalness: 0.05,
        roughness: 0.42,
      }),
    );
    bar.position.set(point.x, 0.075 + point.height / 2, point.z);
    bar.castShadow = true;
    bar.userData = { sceneSelection: pointSelection(point) };
    group.add(bar);
  }

  for (const marker of timeline.markers) {
    const height = marker.kind === "failure" ? 1.8 : 1.45;
    const markerMaterial = new THREE.MeshStandardMaterial({
      color: marker.color,
      emissive: marker.color,
      emissiveIntensity: marker.kind === "failure" ? 0.34 : 0.2,
      metalness: 0.08,
      roughness: 0.34,
    });
    const post = new THREE.Mesh(
      new THREE.CylinderGeometry(0.035, 0.035, height, 18),
      markerMaterial,
    );
    post.position.set(marker.x, 0.08 + height / 2, marker.z);
    post.castShadow = true;
    post.userData = { sceneSelection: markerSelection(marker) };
    group.add(post);

    const cap = new THREE.Mesh(
      new THREE.SphereGeometry(marker.kind === "failure" ? 0.105 : 0.085, 20, 12),
      markerMaterial.clone(),
    );
    cap.position.set(marker.x, 0.12 + height, marker.z);
    cap.castShadow = true;
    cap.userData = { sceneSelection: markerSelection(marker) };
    group.add(cap);
  }

  return group;
}

function pointSelection(point: IndustrialTimelinePoint): IndustrialSceneSelection {
  return {
    health: point.health,
    id: `point:${point.id}`,
    kind: "point",
    label: point.label,
    risk: point.risk,
    score: point.score,
    state: point.state,
    stateReason: point.stateReason,
    temporalX: point.temporalX,
    timeToFailureSeconds: point.timeToFailureSeconds,
    timestampStart: point.timestampStart,
    windowId: point.windowId,
  };
}

function markerSelection(marker: IndustrialTimelineMarker): IndustrialSceneSelection {
  return {
    id: `marker:${marker.kind}`,
    kind: "marker",
    markerKind: marker.kind,
    markerLabel: marker.label,
    temporalX: marker.temporalX,
    timeToFailureSeconds: marker.timeToFailureSeconds,
  };
}

function selectionFromObject(object: THREE.Object3D): IndustrialSceneSelection | null {
  const selection = object.userData.sceneSelection;
  return isIndustrialSelection(selection) ? selection : null;
}

function isIndustrialSelection(value: unknown): value is IndustrialSceneSelection {
  return (
    typeof value === "object" &&
    value !== null &&
    "kind" in value &&
    ((value as { kind?: unknown }).kind === "point" ||
      (value as { kind?: unknown }).kind === "marker")
  );
}

function selectionId(selection: IndustrialSceneSelection): string {
  return selection.id;
}

function markerKindLabel(kind: IndustrialTimelineMarker["kind"]): string {
  const labels: Record<IndustrialTimelineMarker["kind"], string> = {
    failure: "final registrado",
    first_alert: "primer pico",
    persistent_alert: "aviso sostenido",
  };
  return labels[kind];
}

function createLights(statusColor: number) {
  const group = new THREE.Group();
  const ambient = new THREE.HemisphereLight(0xffffff, 0xcbd5e1, 1.9);
  group.add(ambient);

  const key = new THREE.DirectionalLight(0xffffff, 2.1);
  key.position.set(3.5, 5, 4);
  key.castShadow = true;
  key.shadow.mapSize.width = 1024;
  key.shadow.mapSize.height = 1024;
  group.add(key);

  const accent = new THREE.PointLight(statusColor, 0.55, 5);
  accent.position.set(-2.2, 2.1, 1.4);
  group.add(accent);

  return group;
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    if (mesh.geometry) {
      mesh.geometry.dispose();
    }
    const material = mesh.material;
    if (Array.isArray(material)) {
      material.forEach((entry) => entry.dispose());
    } else if (material) {
      material.dispose();
    }
  });
}
