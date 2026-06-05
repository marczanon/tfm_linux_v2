import { STAGE_LABELS } from "../../constants/pipeline";
import type { DatasetCapabilityRule } from "../../types";
import { StatusPill } from "../common/StatusPill";

export function CapabilityList({
  capabilities,
}: {
  capabilities: DatasetCapabilityRule[];
}) {
  return (
    <div className="capability-list">
      {capabilities.map((capability) => (
        <div className="capability-row" key={capability.stage}>
          <span>{STAGE_LABELS[capability.stage]}</span>
          <StatusPill
            ok={capability.status === "allowed"}
            label={capability.status}
            muted={capability.status === "not_supported"}
          />
        </div>
      ))}
    </div>
  );
}
