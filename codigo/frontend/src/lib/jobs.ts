import type { ApiRunJobStatus } from "../types";

export function isActiveJob(job: ApiRunJobStatus): boolean {
  return job.status === "queued" || job.status === "running";
}
