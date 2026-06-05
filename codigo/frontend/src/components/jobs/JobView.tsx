import type { ApiRunJobStatus, RunSnapshot } from "../../types";
import { StatusPill } from "../common/StatusPill";

export function JobView({
  job,
  snapshot,
}: {
  job: ApiRunJobStatus | null;
  snapshot: RunSnapshot | null;
}) {
  if (job === null) {
    return <p className="empty-state compact-empty">Sin job en curso</p>;
  }

  return (
    <section className="plan-section job-section">
      <div className="job-heading">
        <h3>Job</h3>
        <StatusPill
          ok={job.status === "completed"}
          label={job.status}
          muted={job.status === "queued" || job.status === "running"}
        />
      </div>
      <dl className="meta-list">
        <div>
          <dt>job_id</dt>
          <dd>{job.job_id}</dd>
        </div>
        <div>
          <dt>run_id</dt>
          <dd>{job.run_id}</dd>
        </div>
        <div>
          <dt>detalle</dt>
          <dd>{job.detail ?? "-"}</dd>
        </div>
      </dl>
      {job.status === "failed" && job.detail ? (
        <p className="job-error">{job.detail}</p>
      ) : null}
      {snapshot ? (
        <dl className="meta-list snapshot-list">
          <div>
            <dt>artefactos</dt>
            <dd>{snapshot.n_artifacts}</dd>
          </div>
          <div>
            <dt>aprobada</dt>
            <dd>{snapshot.approved === null ? "-" : String(snapshot.approved)}</dd>
          </div>
        </dl>
      ) : null}
    </section>
  );
}
