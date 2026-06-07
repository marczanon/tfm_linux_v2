import { AlertTriangle } from "lucide-react";

export function WebGLFallback({ message }: { message: string }) {
  return (
    <div className="industrial-webgl-fallback">
      <AlertTriangle size={18} />
      <strong>3D no disponible</strong>
      <span>{message}</span>
    </div>
  );
}
