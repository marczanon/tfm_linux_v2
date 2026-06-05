import { STAGE_LABELS } from "../../constants/pipeline";
import type { ApiRunResponse, DatasetDescribeResponse } from "../../types";
import { StatusPill } from "../common/StatusPill";
import { CapabilityList } from "../datasets/CapabilityList";

export function PlanView({
  response,
  description,
}: {
  response: ApiRunResponse | null;
  description: DatasetDescribeResponse | null;
}) {
  if (response === null && description === null) {
    return <p className="empty-state">Sin plan activo</p>;
  }

  const plan = response?.plan ?? null;
  const descriptor = plan?.descriptor ?? description?.descriptor ?? null;
  const adapterInfo = plan?.adapter_info ?? description?.adapter_info ?? null;
  const reviewReasons = response?.human_review_reasons ?? [];
  const responseApproval = response?.human_approval ?? null;

  return (
    <div className="plan-content">
      <div className="plan-status-row">
        {plan ? (
          <StatusPill
            ok={plan.can_execute_requested_stages}
            label={plan.can_execute_requested_stages ? "ejecutable" : "bloqueado"}
          />
        ) : (
          <StatusPill ok label="descrito" />
        )}
        <span>{adapterInfo?.display_name ?? "-"}</span>
      </div>

      {descriptor ? (
        <section className="plan-section">
          <h3>Descriptor</h3>
          <dl className="meta-list">
            <div>
              <dt>dataset_id</dt>
              <dd>{descriptor.dataset_id}</dd>
            </div>
            <div>
              <dt>formato</dt>
              <dd>{descriptor.source_format}</dd>
            </div>
            <div>
              <dt>tarea</dt>
              <dd>{descriptor.task_type}</dd>
            </div>
            <div>
              <dt>perfil</dt>
              <dd>{descriptor.supervision_profile}</dd>
            </div>
            <div>
              <dt>labels</dt>
              <dd>{descriptor.label_source}/{descriptor.label_granularity}</dd>
            </div>
            <div>
              <dt>canales</dt>
              <dd>{descriptor.channel_names.length || "-"}</dd>
            </div>
          </dl>
          {descriptor.notes.length > 0 ? (
            <ul className="plain-list note-list">
              {descriptor.notes.slice(0, 3).map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          ) : null}
        </section>
      ) : null}

      {plan ? (
        <>
          <section className="plan-section">
            <h3>Fases efectivas</h3>
            <div className="stage-list">
              {plan.effective_stages.map((stage) => (
                <span className="stage-token" key={stage}>
                  {STAGE_LABELS[stage]}
                </span>
              ))}
            </div>
          </section>

          <section className="plan-section">
            <h3>Politica</h3>
            <CapabilityList capabilities={plan.policy.capabilities} />
          </section>

          {plan.blocking_reasons.length > 0 ? (
            <section className="plan-section">
              <h3>Bloqueos</h3>
              <ul className="plain-list warning-list">
                {plan.blocking_reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {reviewReasons.length > 0 ? (
            <section className="plan-section">
              <h3>Revision humana</h3>
              <ul className="plain-list review-reasons">
                {reviewReasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
              {responseApproval ? (
                <dl className="meta-list snapshot-list">
                  <div>
                    <dt>required</dt>
                    <dd>{String(responseApproval.required)}</dd>
                  </div>
                  <div>
                    <dt>approved</dt>
                    <dd>
                      {responseApproval.approved === null
                        ? "-"
                        : String(responseApproval.approved)}
                    </dd>
                  </div>
                </dl>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
