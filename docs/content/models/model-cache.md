---
title: Cache Model Weights
weight: 30
description: Stage model weights on cluster storage before serving.
---
<!-- vale write-good.Passive = NO -->
**API:** [`modelplane.ai/v1alpha1` · ModelCache]({{< ref "/reference/modelcaches" >}})

A `ModelCache` stages a model's weights on shared workload-cluster storage,
fetched once from the configured source rather than downloaded again on every pod
start. `ModelDeployments` reference a cache via `spec.modelCacheRef.name`, and
Modelplane mounts it at `/mnt/models` in every serving pod, shared across the
pods of a multi-node engine. The engine reads weights locally from the mount.


Without a cache, the engine fetches the model at pod startup, so the
`ModelDeployment` must supply any required credentials, like `HF_TOKEN` via the engine container's `env`.

Each cache has:

- A **source**: a required `source` enum naming the kind, with the matching
  source object set alongside it (setting `source: HuggingFace` selects
  `spec.huggingFace`, which carries `repo` and `sizeGiB`). `HuggingFace` is
  the only value today; future sources add an enum value and a sibling object
  (`Dragonfly` for P2P distribution, `OCI` for NIM-style bundled artifacts).
- An optional **clusterSelector** to scope replication. Omitting
  `spec.clusterSelector` stages the cache on every matched cluster; setting
  `matchLabels` restricts it to clusters carrying those labels. A
  `ModelDeployment` that references the cache places *new* replicas only onto
  clusters within this footprint, so narrowing the selector also narrows where
  replicas can land - a replica never schedules to a cluster the cache didn't
  stage to. Replicas already running are left where they are.

The cache mounts at `/mnt/models` on every consuming pod; engine container args
should reference this path (`--model=/mnt/models` for vLLM).

`ModelCache` is required for multi-node deployments and optional for single-node
cold-start optimization.

## Storage prerequisites

<!-- vale Google.Acronyms = NO -->
The cache PVC needs a `ReadWriteMany` (RWX) StorageClass on the workload cluster.
What the platform admin must set up depends on the cloud:
<!-- vale Google.Acronyms = YES -->

- **GKE:** auto-provisioned on Filestore. Nothing for the admin to do.
- **EKS:** auto-provisioned on EFS. Nothing for the admin to do. EFS is elastic,
  so the cache's `sizeGiB` is informational on EKS: the PVC API still requires a
  size, but EFS ignores it.
- **Existing:** bring-your-own. The admin creates a `ReadWriteMany` StorageClass
  on the cluster and names it in `cluster.existing.cache.storageClassName`. See
  [Custom cache backends](#custom-cache-backends).

## Custom cache backends

<!-- vale Google.Acronyms = NO -->
Modelplane provisions RWX storage on `GKE` (Filestore Enterprise) and `EKS`
(EFS) clusters, and those classes are fixed. On `Existing` clusters the admin
brings the storage: create a `ReadWriteMany` StorageClass on the cluster (any
backend with automatic PVC provisioning, like WekaIO, NetApp Trident, `FSx` for
NetApp, and similar) and name it in `cluster.existing.cache.storageClassName` on
the [InferenceCluster]({{< ref "platform/inference-cluster.md" >}}). Any name
works; `modelplane-rwx` is just a convention. The ML team's `ModelCache` and
`ModelDeployment` specs are unchanged regardless.
<!-- vale Google.Acronyms = YES -->

Backends that don't fit automatic PVC provisioning (Dragonfly's P2P distribution
to per-node local caches) will be added natively as new types under
`ModelCache.spec.source` rather than through this override.

## Example

{{< manifests "concepts/model-cache.yaml" >}}
<!-- vale write-good.Passive = YES -->
