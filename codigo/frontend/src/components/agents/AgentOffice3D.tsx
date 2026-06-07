import { type CSSProperties, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { RotateCcw } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import {
  type AgentOfficeNode,
  buildAgentOfficeModel,
} from "../../lib/agentOffice3d";
import { supportsWebGL } from "../../lib/visualization3d";
import type { AgentRuntimeEvent } from "../../types";
import { WebGLFallback } from "../visualization/WebGLFallback";

const CAMERA_POSITION = new THREE.Vector3(3.85, 2.95, 4.55);
const CAMERA_TARGET = new THREE.Vector3(0, 0.62, -0.08);

export function AgentOffice3D({
  events,
  selectedAgentId,
  onSelectAgent,
}: {
  events: AgentRuntimeEvent[];
  selectedAgentId: string;
  onSelectAgent: (agentId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const hoveredAgentIdRef = useRef<string | null>(null);
  const selectedAgentIdRef = useRef(selectedAgentId);
  const modelNodesRef = useRef<AgentOfficeNode[]>([]);
  const shouldFocusSelectionRef = useRef(false);
  const [hoveredAgentId, setHoveredAgentId] = useState<string | null>(null);
  const [webGlAvailable, setWebGlAvailable] = useState<boolean | null>(null);
  const model = useMemo(
    () => buildAgentOfficeModel(events, selectedAgentId),
    [events, selectedAgentId],
  );
  const activeNode =
    model.nodes.find((node) => node.id === hoveredAgentId) ??
    model.selectedNode ??
    model.nodes[0];
  const sceneStyle = {
    "--agent-office-state-color": activeNode.cssColor,
  } as CSSProperties;
  const focusableNodes = useMemo(() => {
    if (!model.hasRuntimeEvents) {
      return model.nodes;
    }
    const activeNodes = model.nodes.filter(
      (node) => node.eventCount > 0 || node.selected,
    );
    return activeNodes.length > 0 ? activeNodes : model.nodes;
  }, [model.hasRuntimeEvents, model.nodes]);

  const resetCamera = useCallback(() => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) {
      return;
    }
    camera.position.copy(CAMERA_POSITION);
    controls.target.copy(CAMERA_TARGET);
    controls.update();
  }, []);

  const focusCameraOnNode = useCallback((node: AgentOfficeNode) => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    if (!camera || !controls) {
      return;
    }
    const horizontalOffset = node.x > 1.6 ? -1.35 : node.x < -1.6 ? 1.35 : 1.55;
    const target = new THREE.Vector3(node.x, 0.72, node.z);
    camera.position.set(node.x + horizontalOffset, 2.2, Math.min(4.35, node.z + 2.35));
    controls.target.copy(target);
    controls.update();
  }, []);

  const focusAgent = useCallback(
    (node: AgentOfficeNode) => {
      hoveredAgentIdRef.current = null;
      selectedAgentIdRef.current = node.id;
      shouldFocusSelectionRef.current = true;
      setHoveredAgentId(null);
      onSelectAgent(node.id);
      focusCameraOnNode(node);
    },
    [focusCameraOnNode, onSelectAgent],
  );

  useEffect(() => {
    hoveredAgentIdRef.current = hoveredAgentId;
  }, [hoveredAgentId]);

  useEffect(() => {
    selectedAgentIdRef.current = selectedAgentId;
  }, [selectedAgentId]);

  useEffect(() => {
    modelNodesRef.current = model.nodes;
  }, [model.nodes]);

  useEffect(() => {
    setWebGlAvailable(supportsWebGL());
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || webGlAvailable !== true) {
      return undefined;
    }

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf6f8fb);

    const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 100);
    camera.position.copy(CAMERA_POSITION);
    cameraRef.current = camera;

    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    container.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.enablePan = false;
    controls.maxDistance = 7.6;
    controls.maxPolarAngle = Math.PI * 0.5;
    controls.minDistance = 2.7;
    controls.target.copy(CAMERA_TARGET);
    controlsRef.current = controls;

    const interactiveObjects: THREE.Object3D[] = [];
    const nodeLookup = new Map(model.nodes.map((node) => [node.id, node]));

    scene.add(createOfficeRoom());
    scene.add(createOfficeDecorations());
    scene.add(createOfficeLights());

    for (const connection of model.connections) {
      const from = nodeLookup.get(connection.fromAgentId);
      const to = nodeLookup.get(connection.toAgentId);
      if (from && to) {
        scene.add(createAgentConnection(from, to, connection.intensity));
      }
    }

    for (const node of model.nodes) {
      const group = createAgentDesk(node);
      group.traverse((child) => {
        if (child instanceof THREE.Mesh) {
          child.userData.agentOfficeNode = node;
          interactiveObjects.push(child);
        }
      });
      scene.add(group);
    }

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

    const pickNode = (event: PointerEvent): AgentOfficeNode | null => {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const object = raycaster.intersectObjects(interactiveObjects, false)[0]?.object;
      return object ? nodeFromObject(object) : null;
    };

    const handlePointerMove = (event: PointerEvent) => {
      const node = pickNode(event);
      const nextId = node?.id ?? "";
      if (nextId !== hoverId) {
        hoverId = nextId;
        hoveredAgentIdRef.current = node?.id ?? null;
        setHoveredAgentId(node?.id ?? null);
      }
      renderer.domElement.style.cursor = node ? "pointer" : "grab";
    };

    const handlePointerLeave = () => {
      hoverId = "";
      hoveredAgentIdRef.current = null;
      setHoveredAgentId(null);
      renderer.domElement.style.cursor = "";
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
      const node = pickNode(event);
      if (node) {
        selectedAgentIdRef.current = node.id;
        shouldFocusSelectionRef.current = true;
        onSelectAgent(node.id);
        focusCameraOnNode(node);
      }
    };

    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerleave", handlePointerLeave);
    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);

    let animationFrame = 0;
    const clock = new THREE.Clock();
    const animate = () => {
      const elapsed = clock.getElapsedTime();
      for (const node of model.nodes) {
        const desk = scene.getObjectByName(`agent-office-node-${node.id}`);
        const avatar = scene.getObjectByName(`agent-office-avatar-${node.id}`);
        const beacon = scene.getObjectByName(`agent-office-beacon-${node.id}`);
        const isHovered = hoveredAgentIdRef.current === node.id;
        const isSelected = selectedAgentIdRef.current === node.id;
        if (beacon) {
          const selectedPulse = isSelected ? 0.18 : 0;
          const hoverPulse = isHovered ? 0.12 : 0;
          const activePulse = node.state === "active" ? Math.sin(elapsed * 3.2) * 0.08 : 0;
          beacon.scale.setScalar(1 + selectedPulse + hoverPulse + activePulse);
        }
        if (desk) {
          desk.scale.setScalar(isHovered ? 1.06 : isSelected ? 1.03 : 1);
          if (node.state === "active") {
            desk.rotation.y = Math.sin(elapsed * 0.7) * 0.035;
          } else {
            desk.rotation.y = isHovered ? Math.sin(elapsed * 1.2) * 0.02 : 0;
          }
        }
        if (avatar) {
          const bob = node.state === "active" || isSelected ? Math.sin(elapsed * 2.2) * 0.018 : 0;
          avatar.position.y = bob;
        }
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
      renderer.domElement.removeEventListener("pointerleave", handlePointerLeave);
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
  }, [focusCameraOnNode, model, onSelectAgent, webGlAvailable]);

  useEffect(() => {
    if (webGlAvailable !== true || !shouldFocusSelectionRef.current) {
      return;
    }
    const node = modelNodesRef.current.find((item) => item.id === selectedAgentId);
    if (node) {
      focusCameraOnNode(node);
    }
    shouldFocusSelectionRef.current = false;
  }, [focusCameraOnNode, selectedAgentId, webGlAvailable]);

  if (webGlAvailable === false) {
    return (
      <WebGLFallback message="El navegador o la sesion actual no expone WebGL." />
    );
  }

  return (
    <div className="agent-office-3d-shell" style={sceneStyle}>
      <div
        aria-label="Oficina 3D de agentes"
        className="agent-office-3d-canvas"
        ref={containerRef}
        role="img"
      />
      <div className="agent-office-3d-overlay">
        <AgentOfficeFocusActions
          activeNodeId={activeNode.id}
          nodes={focusableNodes}
          onFocusAgent={focusAgent}
        />
        <button
          aria-label="Recentrar oficina"
          className="icon-button agent-office-3d-reset"
          onClick={resetCamera}
          title="Recentrar oficina"
          type="button"
        >
          <RotateCcw size={16} />
        </button>
        <AgentOfficeMiniTag node={activeNode} />
      </div>
    </div>
  );
}

function AgentOfficeFocusActions({
  activeNodeId,
  nodes,
  onFocusAgent,
}: {
  activeNodeId: string;
  nodes: AgentOfficeNode[];
  onFocusAgent: (node: AgentOfficeNode) => void;
}) {
  return (
    <div aria-label="Foco de agente 3D" className="agent-office-3d-focus-actions">
      {nodes.map((node) => {
        const isActive = activeNodeId === node.id;
        const buttonStyle = {
          "--agent-office-focus-color": node.cssColor,
        } as CSSProperties;
        return (
          <button
            className={`agent-office-3d-focus-action ${node.selected ? "selected" : ""} ${
              isActive ? "active" : ""
            }`}
            key={node.id}
            onClick={() => onFocusAgent(node)}
            style={buttonStyle}
            title={`Enfocar ${node.label}`}
            type="button"
          >
            <i aria-hidden="true" />
            <span>{agentFocusLabel(node.id)}</span>
            <small>{node.eventCount}</small>
          </button>
        );
      })}
    </div>
  );
}

function AgentOfficeMiniTag({ node }: { node: AgentOfficeNode }) {
  const signalText = [
    `${node.eventCount} ev`,
    node.decisionCount > 0 ? `${node.decisionCount} dec` : null,
    node.memoryCount > 0 ? `${node.memoryCount} mem` : null,
    node.errorCount > 0 ? `${node.errorCount} err` : null,
  ].filter((item): item is string => item !== null);

  return (
    <div className="agent-office-3d-mini-tag">
      <span>{node.selected ? "seleccionado" : "inspeccion"}</span>
      <strong>{node.label}</strong>
      <small>{node.role} · {node.stateLabel} · {signalText.join(" · ")}</small>
    </div>
  );
}

function agentFocusLabel(agentId: string): string {
  const labels: Record<string, string> = {
    supervisor: "SUP",
    cleaner: "LIM",
    structurer: "EST",
    modeler: "MOD",
    evaluator: "EVA",
    report_writer: "RED",
    report_verifier: "VER",
  };
  return labels[agentId] ?? agentId.slice(0, 3).toUpperCase();
}

function createOfficeRoom(): THREE.Group {
  const group = new THREE.Group();

  const floor = new THREE.Mesh(
    new THREE.PlaneGeometry(7.6, 5.7),
    new THREE.MeshStandardMaterial({
      color: 0xf5f7fb,
      metalness: 0.05,
      roughness: 0.72,
    }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  group.add(floor);

  const grid = new THREE.GridHelper(7.6, 12, 0xb8c7d8, 0xdbe5ee);
  grid.position.y = 0.01;
  group.add(grid);

  const wallMaterial = new THREE.MeshStandardMaterial({
    color: 0xe8edf4,
    metalness: 0.02,
    roughness: 0.82,
  });
  const trimMaterial = new THREE.MeshStandardMaterial({
    color: 0x0f766e,
    metalness: 0.08,
    roughness: 0.56,
  });

  const backWall = new THREE.Mesh(
    new THREE.BoxGeometry(7.6, 1.78, 0.08),
    wallMaterial,
  );
  backWall.position.set(0, 0.89, -2.84);
  group.add(backWall);

  const wallTrim = new THREE.Mesh(
    new THREE.BoxGeometry(7.55, 0.08, 0.1),
    trimMaterial,
  );
  wallTrim.position.set(0, 1.8, -2.78);
  group.add(wallTrim);

  const leftWall = new THREE.Mesh(
    new THREE.BoxGeometry(0.08, 1.5, 3.35),
    wallMaterial,
  );
  leftWall.position.set(-3.78, 0.75, -1.08);
  group.add(leftWall);

  const rightWall = new THREE.Mesh(
    new THREE.BoxGeometry(0.08, 1.5, 3.35),
    wallMaterial,
  );
  rightWall.position.set(3.78, 0.75, -1.08);
  group.add(rightWall);

  const frontThreshold = new THREE.Mesh(
    new THREE.BoxGeometry(7.3, 0.04, 0.08),
    trimMaterial,
  );
  frontThreshold.position.set(0, 0.035, 2.72);
  group.add(frontThreshold);

  return group;
}

function createOfficeDecorations(): THREE.Group {
  const group = new THREE.Group();
  group.add(createOfficeRug());
  group.add(createWhiteboard());
  group.add(createBookshelf());
  group.add(createWindowPanel(-3.74, -0.88, Math.PI / 2));
  group.add(createWindowPanel(3.74, -0.88, -Math.PI / 2));
  group.add(createPlant(-3.08, 1.94));
  group.add(createPlant(3.08, 1.94));
  group.add(createPlant(3.15, -2.22));
  return group;
}

function createOfficeRug(): THREE.Group {
  const group = new THREE.Group();
  const rug = new THREE.Mesh(
    new THREE.PlaneGeometry(3.6, 2.35),
    new THREE.MeshStandardMaterial({
      color: 0xdbeafe,
      metalness: 0.02,
      roughness: 0.86,
      side: THREE.DoubleSide,
    }),
  );
  rug.rotation.x = -Math.PI / 2;
  rug.position.set(0, 0.018, 0.35);
  group.add(rug);

  const stripeColors = [0x0f766e, 0x2563eb, 0xd97706];
  stripeColors.forEach((color, index) => {
    const stripe = new THREE.Mesh(
      new THREE.PlaneGeometry(0.14, 2.35),
      new THREE.MeshStandardMaterial({
        color,
        metalness: 0.04,
        roughness: 0.72,
        side: THREE.DoubleSide,
      }),
    );
    stripe.rotation.x = -Math.PI / 2;
    stripe.position.set(-1.2 + index * 1.2, 0.022, 0.35);
    group.add(stripe);
  });

  return group;
}

function createWhiteboard(): THREE.Group {
  const group = new THREE.Group();
  const board = new THREE.Mesh(
    new THREE.BoxGeometry(1.8, 0.9, 0.04),
    new THREE.MeshStandardMaterial({
      color: 0xffffff,
      metalness: 0.02,
      roughness: 0.52,
    }),
  );
  board.position.set(0, 1.14, -2.76);
  group.add(board);

  const markerColors = [0x0f766e, 0x2563eb, 0xd97706, 0xdc2626];
  markerColors.forEach((color, index) => {
    const bar = new THREE.Mesh(
      new THREE.BoxGeometry(0.34 + index * 0.08, 0.035, 0.018),
      new THREE.MeshStandardMaterial({
        color,
        metalness: 0.04,
        roughness: 0.48,
      }),
    );
    bar.position.set(-0.55 + index * 0.08, 1.35 - index * 0.13, -2.72);
    group.add(bar);
  });

  return group;
}

function createBookshelf(): THREE.Group {
  const group = new THREE.Group();
  const frameMaterial = new THREE.MeshStandardMaterial({
    color: 0x334155,
    metalness: 0.12,
    roughness: 0.55,
  });
  const shelf = new THREE.Mesh(new THREE.BoxGeometry(1.12, 0.92, 0.18), frameMaterial);
  shelf.position.set(-2.78, 0.52, -2.69);
  group.add(shelf);

  const bookColors = [0x38bdf8, 0xf59e0b, 0x34d399, 0xa78bfa, 0xfb7185];
  bookColors.forEach((color, index) => {
    const book = new THREE.Mesh(
      new THREE.BoxGeometry(0.09, 0.26 + (index % 2) * 0.07, 0.08),
      new THREE.MeshStandardMaterial({
        color,
        metalness: 0.05,
        roughness: 0.64,
      }),
    );
    book.position.set(-3.18 + index * 0.15, 0.72, -2.56);
    group.add(book);
  });

  const shelfLine = new THREE.Mesh(new THREE.BoxGeometry(1.02, 0.04, 0.2), frameMaterial);
  shelfLine.position.set(-2.78, 0.45, -2.55);
  group.add(shelfLine);

  return group;
}

function createWindowPanel(x: number, z: number, rotationY: number): THREE.Group {
  const group = new THREE.Group();
  group.rotation.y = rotationY;
  group.position.set(x, 1.12, z);

  const panel = new THREE.Mesh(
    new THREE.BoxGeometry(1.05, 0.62, 0.035),
    new THREE.MeshStandardMaterial({
      color: 0xbae6fd,
      emissive: 0x7dd3fc,
      emissiveIntensity: 0.12,
      metalness: 0.04,
      roughness: 0.36,
    }),
  );
  group.add(panel);

  const frameMaterial = new THREE.MeshStandardMaterial({
    color: 0x1f2937,
    metalness: 0.12,
    roughness: 0.5,
  });
  const vertical = new THREE.Mesh(new THREE.BoxGeometry(0.035, 0.64, 0.045), frameMaterial);
  group.add(vertical);
  const horizontal = new THREE.Mesh(new THREE.BoxGeometry(1.07, 0.035, 0.045), frameMaterial);
  group.add(horizontal);

  return group;
}

function createPlant(x: number, z: number): THREE.Group {
  const group = new THREE.Group();
  group.position.set(x, 0, z);

  const pot = new THREE.Mesh(
    new THREE.CylinderGeometry(0.16, 0.2, 0.25, 18),
    new THREE.MeshStandardMaterial({
      color: 0xf97316,
      metalness: 0.05,
      roughness: 0.72,
    }),
  );
  pot.position.y = 0.14;
  group.add(pot);

  const stem = new THREE.Mesh(
    new THREE.CylinderGeometry(0.025, 0.035, 0.42, 12),
    new THREE.MeshStandardMaterial({
      color: 0x166534,
      roughness: 0.7,
    }),
  );
  stem.position.y = 0.46;
  group.add(stem);

  const leafMaterial = new THREE.MeshStandardMaterial({
    color: 0x22c55e,
    metalness: 0.02,
    roughness: 0.62,
  });
  const leafOffsets = [
    [-0.1, 0.62, 0.02],
    [0.1, 0.68, -0.02],
    [0, 0.78, 0.08],
  ];
  leafOffsets.forEach(([leafX, leafY, leafZ]) => {
    const leaf = new THREE.Mesh(new THREE.SphereGeometry(0.14, 18, 12), leafMaterial);
    leaf.scale.set(1.15, 0.72, 0.82);
    leaf.position.set(leafX, leafY, leafZ);
    group.add(leaf);
  });

  return group;
}

function createOfficeLights(): THREE.Group {
  const group = new THREE.Group();
  const ambient = new THREE.HemisphereLight(0xffffff, 0xcbd5e1, 1.65);
  group.add(ambient);

  const key = new THREE.DirectionalLight(0xffffff, 1.7);
  key.position.set(2.6, 5.2, 3.1);
  group.add(key);

  const fill = new THREE.PointLight(0x7dd3fc, 0.78, 8);
  fill.position.set(-2.7, 2.3, 1.2);
  group.add(fill);

  const warm = new THREE.PointLight(0xfbbf24, 0.45, 6.5);
  warm.position.set(2.9, 1.9, -2.2);
  group.add(warm);

  return group;
}

function createAgentConnection(
  from: AgentOfficeNode,
  to: AgentOfficeNode,
  intensity: number,
): THREE.Line {
  const geometry = new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(from.x, 0.08, from.z),
    new THREE.Vector3(to.x, 0.08, to.z),
  ]);
  const material = new THREE.LineBasicMaterial({
    color: to.threeColor,
    transparent: true,
    opacity: 0.2 + intensity * 0.46,
  });
  return new THREE.Line(geometry, material);
}

function createAgentDesk(node: AgentOfficeNode): THREE.Group {
  const group = new THREE.Group();
  group.name = `agent-office-node-${node.id}`;
  group.position.set(node.x, 0, node.z);

  const deskMaterial = new THREE.MeshStandardMaterial({
    color: node.selected ? 0xffffff : 0xf8fafc,
    metalness: 0.08,
    roughness: 0.58,
  });
  const edgeMaterial = new THREE.MeshStandardMaterial({
    color: 0x1f2937,
    metalness: 0.18,
    roughness: 0.45,
  });
  const accentMaterial = new THREE.MeshStandardMaterial({
    color: node.threeColor,
    emissive: node.threeColor,
    emissiveIntensity: node.state === "active" ? 0.35 : 0.12,
    metalness: 0.14,
    roughness: 0.42,
  });

  const top = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.08, 0.56), deskMaterial);
  top.position.y = 0.34;
  group.add(top);

  const frontAccent = new THREE.Mesh(
    new THREE.BoxGeometry(0.78, 0.16, 0.045),
    accentMaterial,
  );
  frontAccent.position.set(0, 0.24, 0.3);
  group.add(frontAccent);

  const monitor = new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.3, 0.08), edgeMaterial);
  monitor.position.set(0, 0.58, -0.18);
  group.add(monitor);

  const monitorScreen = new THREE.Mesh(
    new THREE.BoxGeometry(0.32, 0.2, 0.018),
    new THREE.MeshStandardMaterial({
      color: node.threeColor,
      emissive: node.threeColor,
      emissiveIntensity: node.eventCount > 0 ? 0.24 : 0.08,
      metalness: 0.04,
      roughness: 0.36,
    }),
  );
  monitorScreen.position.set(0, 0.58, -0.23);
  group.add(monitorScreen);

  const beacon = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.095, 0.045, 20), accentMaterial);
  beacon.name = `agent-office-beacon-${node.id}`;
  beacon.position.set(-0.3, 0.405, 0.16);
  group.add(beacon);

  const base = new THREE.Mesh(new THREE.BoxGeometry(0.55, 0.05, 0.55), accentMaterial);
  base.position.set(0, 0.055, 0);
  group.add(base);

  addAgentSignalMarkers(group, node);
  group.add(createStandingAgent(node));

  if (node.selected) {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(0.6, 0.018, 10, 56),
      new THREE.MeshBasicMaterial({ color: node.threeColor }),
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.075;
    group.add(ring);
  }

  return group;
}

function createStandingAgent(node: AgentOfficeNode): THREE.Group {
  const group = new THREE.Group();
  group.name = `agent-office-avatar-${node.id}`;
  const isSupervisor = node.id === "supervisor";
  group.position.set(isSupervisor ? 0.5 : 0.48, 0, isSupervisor ? -0.02 : 0.02);
  const shirtColor = agentShirtColor(node.id);
  const trimColor = isSupervisor ? 0xfbbf24 : node.threeColor;

  const torsoMaterial = new THREE.MeshStandardMaterial({
    color: shirtColor,
    emissive: shirtColor,
    emissiveIntensity: node.state === "active" || isSupervisor ? 0.16 : 0.04,
    metalness: 0.08,
    roughness: 0.5,
  });
  const skinMaterial = new THREE.MeshStandardMaterial({
    color: 0xf2c7a7,
    metalness: 0.03,
    roughness: 0.64,
  });
  const darkMaterial = new THREE.MeshStandardMaterial({
    color: 0x1f2937,
    metalness: 0.1,
    roughness: 0.54,
  });
  const trimMaterial = new THREE.MeshStandardMaterial({
    color: trimColor,
    emissive: trimColor,
    emissiveIntensity: isSupervisor ? 0.2 : 0.08,
    metalness: 0.16,
    roughness: 0.42,
  });

  const torso = new THREE.Mesh(
    new THREE.CylinderGeometry(
      isSupervisor ? 0.16 : 0.14,
      isSupervisor ? 0.2 : 0.18,
      isSupervisor ? 0.5 : 0.44,
      20,
    ),
    torsoMaterial,
  );
  torso.position.y = isSupervisor ? 0.61 : 0.58;
  group.add(torso);

  const head = new THREE.Mesh(new THREE.SphereGeometry(0.13, 22, 16), skinMaterial);
  head.position.y = isSupervisor ? 0.96 : 0.9;
  group.add(head);

  const hair = new THREE.Mesh(new THREE.SphereGeometry(0.135, 18, 10), darkMaterial);
  hair.scale.set(1, 0.48, 1);
  hair.position.y = isSupervisor ? 1.04 : 0.98;
  group.add(hair);

  [-0.07, 0.07].forEach((x) => {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.045, 0.32, 12), darkMaterial);
    leg.position.set(x, 0.28, 0);
    group.add(leg);
  });

  [-0.18, 0.18].forEach((x) => {
    const arm = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.032, 0.34, 12), skinMaterial);
    arm.position.set(x, 0.58, 0.01);
    arm.rotation.z = x > 0 ? -0.18 : 0.18;
    group.add(arm);
  });

  const statusBadge = new THREE.Mesh(
    new THREE.SphereGeometry(0.045, 14, 10),
    trimMaterial,
  );
  statusBadge.position.set(0.13, 0.72, 0.12);
  group.add(statusBadge);

  const collar = new THREE.Mesh(
    new THREE.TorusGeometry(isSupervisor ? 0.145 : 0.12, 0.012, 8, 28),
    trimMaterial,
  );
  collar.rotation.x = Math.PI / 2;
  collar.position.y = isSupervisor ? 0.83 : 0.77;
  group.add(collar);

  if (isSupervisor) {
    group.add(createSupervisorLeaderMarker());
  }

  return group;
}

function createSupervisorLeaderMarker(): THREE.Group {
  const group = new THREE.Group();
  const goldMaterial = new THREE.MeshStandardMaterial({
    color: 0xfbbf24,
    emissive: 0xf59e0b,
    emissiveIntensity: 0.18,
    metalness: 0.18,
    roughness: 0.36,
  });

  const podiumRing = new THREE.Mesh(
    new THREE.TorusGeometry(0.36, 0.026, 10, 56),
    goldMaterial,
  );
  podiumRing.rotation.x = -Math.PI / 2;
  podiumRing.position.y = 0.055;
  group.add(podiumRing);

  const podiumDisc = new THREE.Mesh(
    new THREE.CylinderGeometry(0.32, 0.36, 0.035, 36),
    goldMaterial,
  );
  podiumDisc.position.y = 0.035;
  group.add(podiumDisc);

  const badgePole = new THREE.Mesh(
    new THREE.CylinderGeometry(0.014, 0.014, 0.32, 10),
    goldMaterial,
  );
  badgePole.position.set(0, 1.26, 0);
  group.add(badgePole);

  const badge = new THREE.Mesh(
    new THREE.CylinderGeometry(0.135, 0.135, 0.032, 5),
    goldMaterial,
  );
  badge.rotation.x = Math.PI / 2;
  badge.position.set(0, 1.46, 0);
  group.add(badge);

  const crownPoints = [-0.08, 0, 0.08];
  crownPoints.forEach((x, index) => {
    const point = new THREE.Mesh(
      new THREE.ConeGeometry(index === 1 ? 0.042 : 0.035, index === 1 ? 0.12 : 0.09, 5),
      goldMaterial,
    );
    point.position.set(x, 1.16 + (index === 1 ? 0.025 : 0), 0);
    group.add(point);
  });

  return group;
}

function agentShirtColor(agentId: string): number {
  const colors: Record<string, number> = {
    supervisor: 0x115e59,
    cleaner: 0x0284c7,
    structurer: 0x2563eb,
    modeler: 0x7c3aed,
    evaluator: 0xd97706,
    report_writer: 0xbe123c,
    report_verifier: 0x059669,
  };
  return colors[agentId] ?? 0x64748b;
}

function addAgentSignalMarkers(group: THREE.Group, node: AgentOfficeNode): void {
  const signals = [
    { color: 0x2563eb, count: node.memoryCount, x: -0.27, z: 0.13 },
    { color: 0x475569, count: node.toolCount, x: -0.09, z: 0.17 },
    { color: 0xd97706, count: node.debateCount, x: 0.09, z: 0.17 },
    { color: 0xdc2626, count: node.errorCount, x: 0.27, z: 0.13 },
  ].filter((signal) => signal.count > 0);

  for (const signal of signals) {
    const height = 0.08 + Math.min(5, signal.count) * 0.035;
    const marker = new THREE.Mesh(
      new THREE.BoxGeometry(0.1, height, 0.1),
      new THREE.MeshStandardMaterial({
        color: signal.color,
        emissive: signal.color,
        emissiveIntensity: 0.08,
        metalness: 0.12,
        roughness: 0.44,
      }),
    );
    marker.position.set(signal.x, 0.42 + height / 2, signal.z);
    group.add(marker);
  }
}

function nodeFromObject(object: THREE.Object3D): AgentOfficeNode | null {
  const node = object.userData.agentOfficeNode;
  return isAgentOfficeNode(node) ? node : null;
}

function isAgentOfficeNode(value: unknown): value is AgentOfficeNode {
  return Boolean(
    value &&
      typeof value === "object" &&
      "id" in value &&
      typeof (value as { id?: unknown }).id === "string",
  );
}

function disposeObject(root: THREE.Object3D): void {
  root.traverse((object) => {
    const disposable = object as THREE.Object3D & {
      geometry?: { dispose: () => void };
      material?: THREE.Material | THREE.Material[];
    };
    disposable.geometry?.dispose();
    if (Array.isArray(disposable.material)) {
      disposable.material.forEach((material) => material.dispose());
    } else {
      disposable.material?.dispose();
    }
  });
}
