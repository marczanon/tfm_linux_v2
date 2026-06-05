import { AlertTriangle } from "lucide-react";

export function ErrorState({ message }: { message: string }) {
  return (
    <section className="alert" role="alert">
      <AlertTriangle size={18} />
      <span>{message}</span>
    </section>
  );
}
