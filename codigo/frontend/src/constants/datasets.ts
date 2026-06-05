import type { DatasetAdapterInfo, PipelineRunExecutionMode } from "../types";

export const FALLBACK_ADAPTER: DatasetAdapterInfo = {
  adapter_id: "cwru_bearing",
  dataset_id: "cwru_bearing",
  display_name: "CWRU Bearing Dataset",
  supported_source_formats: ["mat", "directory"],
  supports_descriptor: true,
  supports_manifest: true,
  is_experimental: false,
  notes: "Fallback local hasta cargar el catalogo del backend.",
};

export const DATASET_REQUEST_DEFAULTS: Record<
  string,
  {
    rawPath: string;
    executionMode: PipelineRunExecutionMode;
    datasetPolicyId: string | null;
    allowSyntheticLabels: boolean;
  }
> = {
  cwru_bearing: {
    rawPath: "codigo/data/raw/cwru_bearing/mat",
    executionMode: "full",
    datasetPolicyId: null,
    allowSyntheticLabels: false,
  },
  nasa_ims_bearing: {
    rawPath: "codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen",
    executionMode: "full",
    datasetPolicyId: "nasa_ims_temporal_v1",
    allowSyntheticLabels: false,
  },
  generic_tabular_signal: {
    rawPath: "codigo/data/raw/uploads",
    executionMode: "diagnostic",
    datasetPolicyId: null,
    allowSyntheticLabels: false,
  },
};
