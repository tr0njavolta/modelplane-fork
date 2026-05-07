# Modelplane API Update — One-Pager

**Status:** Draft
**Date:** May 2026
**Author:** Nic Cope

## Summary

A simplified resource model for Modelplane that drops the ClusterModel/Model
catalog split, makes ModelDeployment self-contained, and aligns the resource
hierarchy with Kubernetes core: ModelDeployment → ModelPlacement → ModelService
→ ModelEndpoint mirrors Deployment → Pod → Service → Endpoint.

Cluster and pool matching uses open-ended capabilities with CEL expressions.
InferenceClass captures hardware topology as a reusable named bundle, following
the StorageClass pattern. Composition fields (parallelism, engine config) stay
structured so the placement function can compose KServe LLMInferenceService
correctly.

## Resource model

| Resource | Scope | Created by | Purpose |
|---|---|---|---|
| `InferenceGateway` | Cluster | Platform team | Control plane routing infrastructure |
| `InferenceClass` | Cluster | Platform team (or Modelplane defaults) | Named hardware topology bundle |
| `InferenceCluster` | Cluster | Platform team | A cluster in the inference fleet |
| `ModelDeployment` | Namespace | ML team | Self-contained model deployment spec |
| `ModelPlacement` | Namespace | Modelplane (composed) | Per-cluster realization of a deployment replica |
| `ModelService` | Namespace | ML team | Routing surface across deployments and external endpoints |
| `ModelEndpoint` | Namespace | Modelplane (composed) | Per-placement routing target |

`ClusterModel` and `Model` are removed. Model identity, engine configuration,
and resource requirements all live on `ModelDeployment`.

## InferenceClass

Reusable hardware topology bundles. An InferenceClass captures the complete
hardware context for a node pool — GPU topology and inter-node networking.
Modelplane ships defaults (`h200-nvl-8x-ib`, `h100-nvl-8x-ib`, `h100-nvl-8x`,
`l4-1x`, `b200-nvl-8x`, `mi300x-8x`, etc.). Platform teams can author custom
classes for bespoke hardware.

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: InferenceClass
metadata:
  name: h200-nvl-8x-ib
spec:
  description: "8x NVIDIA H200 SXM, NVLink Switch, InfiniBand 400Gbps"
  capabilities:
    gpu.vendor: nvidia
    gpu.product: H200
    gpu.architecture: Hopper
    gpu.vramGiB: 141
    gpu.count: 8
    gpu.features: [fp8, bf16, transformer-engine, mig]
    interconnect.intraNode: nvswitch
    interconnect.intraNodeBandwidthGBs: 900
    network.interNode: infiniband
    network.interNodeBandwidthGbps: 400
    driver.version: {type: version, value: "535.129.03"}
```

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: InferenceClass
metadata:
  name: l4-1x
spec:
  description: "1x NVIDIA L4, 24 GiB GDDR6, PCIe"
  capabilities:
    gpu.vendor: nvidia
    gpu.product: L4
    gpu.architecture: Ada
    gpu.vramGiB: 24
    gpu.count: 1
    gpu.features: [fp8, bf16, int8]
    interconnect.intraNode: pcie
```

Capability values are plain YAML by default (string, integer, boolean, list).
Decorate with `{type: ..., value: ...}` when YAML can't express the type
natively (versions, quantities).

## InferenceCluster

A cluster in the fleet. Cluster-level metadata is captured in standard
Kubernetes labels. Hardware capabilities — including inter-node networking —
come from each pool's referenced `InferenceClass`.

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: InferenceCluster
metadata:
  name: prod-coreweave-us-east
  labels:
    modelplane.ai/tier: production
    cloud.provider: coreweave
    cloud.region: us-east-1
spec:
  cluster:
    source: Existing
    existing:
      secretRef:
        name: coreweave-kubeconfig
        key: kubeconfig

  nodePools:
  - name: frontier
    class: h200-nvl-8x-ib
    maxNodes: 4
    nodeSelector:
      modelplane.ai/pool: frontier

  - name: general
    class: h100-nvl-8x
    maxNodes: 8
    nodeSelector:
      modelplane.ai/pool: general
```

## ModelDeployment — Mixtral 8x7B

Single-node, two GPUs, concurrency autoscaling.

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelDeployment
metadata:
  name: mixtral-8x7b
  namespace: ml-team
spec:
  source: HuggingFace
  huggingFace:
    repo: mistralai/Mixtral-8x7B-Instruct-v0.1

  placements: 1

  clusterSelector:
    matchLabels:
      modelplane.ai/tier: production

  scaling:
    minReplicas: 2
    maxReplicas: 10
    target: 32

  serving:
  - name: default
    poolSelector:
      count: 2
      perNode: 2
      cel: |
        capabilities["gpu.vramGiB"] >= 80

    engine:
      name: vLLM
      image: vllm/vllm-openai:v0.8.5
      args:
      - "--tensor-parallel-size=2"
      - "--max-model-len=32768"
      - "--gpu-memory-utilization=0.9"
```

## ModelDeployment — Kimi K2

Multi-node frontier MoE. 16 GPUs across 2 nodes, TP=8 PP=2, FP8, tool calling.
No `scaling` block means fixed replicas (one pod per placement).

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelDeployment
metadata:
  name: kimi-k2
  namespace: ml-team
spec:
  source: HuggingFace
  huggingFace:
    repo: moonshotai/Kimi-K2-Instruct
    secretRef:
      name: hf-token

  placements: 1

  clusterSelector:
    matchLabels:
      modelplane.ai/tier: production

  serving:
  - name: default
    poolSelector:
      count: 16
      perNode: 8
      cel: |
        capabilities["gpu.vramGiB"] >= 141 &&
        "fp8" in capabilities["gpu.features"] &&
        capabilities["network.interNode"] == "infiniband" &&
        capabilities["network.interNodeBandwidthGbps"] >= 400

    parallelism:
      tensor: 8
      pipeline: 2

    engine:
      name: vLLM
      image: vllm/vllm-openai:v0.8.5
      args:
      - "--trust-remote-code"
      - "--max-model-len=65536"
      - "--gpu-memory-utilization=0.85"
      - "--enable-auto-tool-choice"
      - "--tool-call-parser=kimi_k2"
      - "--distributed-executor-backend=ray"
```

## ModelDeployment — Qwen3-Coder-480B

Multi-node MoE coding model. Demonstrates a profile fallback: prefer H200s
with PP=2, fall back to H100s with PP=4 if no H200 pool matches.

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelDeployment
metadata:
  name: qwen3-coder
  namespace: ml-team
spec:
  source: HuggingFace
  huggingFace:
    repo: Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8

  placements: 1

  clusterSelector:
    matchLabels:
      modelplane.ai/tier: production

  serving:
  - name: h200-preferred
    poolSelector:
      count: 16
      perNode: 8
      cel: |
        capabilities["gpu.product"] == "H200" &&
        "fp8" in capabilities["gpu.features"] &&
        capabilities["network.interNode"] == "infiniband"

    parallelism:
      tensor: 8
      pipeline: 2

    engine:
      name: vLLM
      image: vllm/vllm-openai:v0.9.0
      args:
      - "--max-model-len=65536"
      - "--gpu-memory-utilization=0.9"
      - "--enable-auto-tool-choice"
      - "--tool-call-parser=hermes"

  - name: h100-fallback
    poolSelector:
      count: 32
      perNode: 8
      cel: |
        capabilities["gpu.product"] == "H100" &&
        "fp8" in capabilities["gpu.features"] &&
        capabilities["network.interNode"] == "infiniband"

    parallelism:
      tensor: 8
      pipeline: 4

    engine:
      name: vLLM
      image: vllm/vllm-openai:v0.9.0
      args:
      - "--max-model-len=32768"
      - "--gpu-memory-utilization=0.9"
      - "--enable-auto-tool-choice"
      - "--tool-call-parser=hermes"
```

## ModelEndpoint

A reachable inference endpoint. Composed by `ModelDeployment` (one per
`ModelPlacement`) or created manually for break-glass routing to external
services like Together AI or BaseTen. Both shapes use the same schema —
`ModelService` doesn't care where they came from.

Composed (one per placement, created by Modelplane):

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelEndpoint
metadata:
  name: kimi-k2-coreweave-us-east
  namespace: ml-team
  labels:
    modelplane.ai/deployment: kimi-k2
spec:
  url: http://10.0.1.50/ml-team/kimi-k2/
  api: OpenAI
```

Manual (created by the ML team for external routing):

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelEndpoint
metadata:
  name: together-kimi-k2
  namespace: ml-team
  labels:
    modelplane.ai/deployment: kimi-k2
spec:
  url: https://api.together.xyz/v1
  api: OpenAI
  auth:
    secretRef:
      name: together-api-key
```

The `api` field declares what protocol the endpoint speaks. `OpenAI` means
the standard OpenAI-compatible surface (`/v1/chat/completions`,
`/v1/embeddings`, etc.). Future values reserve room for non-OpenAI APIs.

## ModelService

A weighted routing surface across `ModelEndpoint`s. Always uses
`spec.endpoints` — a single-entry list for the simple case, multiple entries
with weights for canary, A/B, or hybrid SaaS routing.

Simple — one entry, all of a deployment's endpoints:

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelService
metadata:
  name: kimi-k2
  namespace: ml-team
spec:
  endpoints:
  - selector:
      matchLabels:
        modelplane.ai/deployment: kimi-k2
```

Weighted — multiple deployments plus an external endpoint:

```yaml
apiVersion: modelplane.ai/v1alpha1
kind: ModelService
metadata:
  name: assistant
  namespace: ml-team
spec:
  endpoints:
  - weight: 70
    selector:
      matchLabels:
        modelplane.ai/deployment: kimi-k2

  - weight: 25
    selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-coder

  - weight: 5
    selector:
      matchLabels:
        modelplane.ai/endpoint: together-kimi-k2
```

Each `endpoints[]` entry selects `ModelEndpoint` resources by label. Composed
endpoints carry the `modelplane.ai/deployment` label set by the deployment
composition; manual endpoints carry whatever labels the user puts on them.
A route with no `weight` defaults to weight 1 (equal weighting across routes).

## Composed resources

The Kubernetes parallel:

| Modelplane | Kubernetes |
|---|---|
| `ModelDeployment` | `Deployment` |
| `ModelPlacement` | `Pod` |
| `ModelService` | `Service` |
| `ModelEndpoint` | `Endpoint` |

`ModelPlacement` is composed by `ModelDeployment` — one per
`spec.placements`. Each placement targets a specific `InferenceCluster` and
pool, and composes a KServe `LLMInferenceService` on that cluster.

`ModelEndpoint` is composed by `ModelDeployment` — one per `ModelPlacement`,
labeled with `modelplane.ai/deployment: <md-name>`. Manual `ModelEndpoint`s
can also be created to route to external services, using the same schema.

## Key design decisions

- **`ClusterModel` and `Model` removed.** `ModelDeployment` is self-contained.
  Organizations that want a curated catalog build a Crossplane Composition over
  `ModelDeployment`.
- **Model identity is `<namespace>/<name>`.** The ModelDeployment's namespace
  and name form the served model identifier passed to the engine and used by
  clients in OpenAI API requests. The HuggingFace repo (or other source) is
  purely where weights are fetched from, not the model's identity.
- **Two-level matching, two mechanisms, two homes.** Cluster-level matching
  is deployment-level — `spec.clusterSelector.matchLabels` against standard
  Kubernetes labels on `InferenceCluster` (organizational metadata: tier,
  region, provider). Pool-level matching is per-profile —
  `serving[].poolSelector.cel` against the typed `capabilities` bundled by
  `InferenceClass` (hardware and networking facts). Cluster selection is the
  deployment intent; pool selection is the hardware adaptation strategy.
- **`InferenceClass` is the complete hardware context.** GPU topology and
  inter-node networking both live on the class. Different networking implies
  a different class (`h200-nvl-8x-ib` vs `h200-nvl-8x`). No cluster-level
  capabilities — networking belongs to the pool that uses it.
- **Open-ended capabilities with CEL matching.** Pool capabilities are
  key-value maps; pool selectors are CEL expressions. New capabilities don't
  require schema changes.
- **Optional type decoration.** Plain YAML values for the common case
  (string, integer, boolean, list); `{type: ..., value: ...}` wrapper for
  versions, quantities, and any type YAML can't express natively.
- **Structured parallelism.** `parallelism: {tensor, pipeline, expert}` on the
  serving profile maps directly to KServe's `LLMInferenceService.spec.parallelism`.
  Engine args remain opaque and pass through to the engine container.
- **Serving as an array of fallbacks.** Profiles are tried in order; the first
  one with a matching cluster and pool wins. Different profiles can adapt to
  different hardware (H200 with PP=2, H100 with PP=4). The common case is a
  single entry.
- **Placement count, cluster selection, and scaling are deployment-level.**
  `spec.placements` controls how many `ModelPlacement`s are created (one per
  cluster). `spec.clusterSelector` filters the candidate clusters. Optional
  `spec.scaling` configures per-placement pod autoscaling (KEDA targeting the
  per-cluster `LLMInferenceService`). Omitting `spec.scaling` means fixed
  replicas — one pod per placement. Profiles never carry these concerns — only
  one profile is active per placement, and the deployment's intent doesn't
  change between profiles.
- **Fleet scheduling, in-cluster delegation.** Modelplane picks
  `(InferenceCluster, pool)` per placement based on declared capabilities and
  capacity (declared max nodes minus existing placement claims). Device binding
  is delegated to the in-cluster scheduler and DRA driver.
- **Kubernetes-native resource hierarchy.** `ModelDeployment` →
  `ModelPlacement` → `ModelService` → `ModelEndpoint` mirrors `Deployment` →
  `Pod` → `Service` → `Endpoint`.
- **One `ModelEndpoint` schema, two creation paths.** `ModelDeployment`
  composes one `ModelEndpoint` per `ModelPlacement`. The ML team can also
  create `ModelEndpoint`s manually to point at external services (Together,
  BaseTen, Bedrock). Both look the same to `ModelService` — `spec.url` and
  `spec.api` describe the endpoint, `auth` is optional for endpoints that
  need credentials.
- **`ModelService` always uses `spec.endpoints`.** No separate path for the
  simple case versus weighted routing. Single-entry list for one deployment,
  multi-entry with weights for canary, A/B, or SaaS overflow. Each entry
  selects `ModelEndpoint`s by label — Kubernetes-native, no special
  endpointRef syntax.
