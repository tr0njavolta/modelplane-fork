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
  `spec.huggingFace`, which carries `repo` and `sizeGiB`). `HuggingFace` is the
  only source today.
- An optional **clusterSelector** to scope replication. Omitting
  `spec.clusterSelector` stages the cache on every matched cluster; setting
  `matchLabels` restricts it to clusters carrying those labels. A
  `ModelDeployment` that references the cache places *new* replicas only onto
  clusters within this footprint, so narrowing the selector also narrows where
  replicas can land - a replica never schedules to a cluster the cache didn't
  stage to. Replicas already running are left where they are.

The cache mounts at `/mnt/models` on every consuming pod; engine container args
should reference this path (`--model=/mnt/models` for vLLM).

`ModelCache` is recommended for multi-node deployments and optional for
single-node cold-start optimization.

## Loading from the cache efficiently

A cache only pays off if the engine reads from it quickly. With its default
loader an engine can read a large model from shared storage slowly enough that
the cache makes cold starts *worse* than fetching the model directly, since you
pay to hydrate the cache and then wait on a slow read. Choose a fast loader with
your engine flags.

For vLLM on EKS, `--load-format=runai_streamer` reads from the EFS-backed cache
dramatically faster than the default loader (minutes rather than tens of
minutes for a large model), tuned further with `--model-loader-extra-config`:

```yaml {nocopy=true}
args:
- --model=/mnt/models
- --load-format=runai_streamer
- --model-loader-extra-config={"concurrency":16,"distributed":true}
```

The right loader and settings depend on the engine and the storage backend, so
treat these as a starting point and measure your own cold-start time. The
[Kimi-K2 example]({{< ref "/examples/kimi-k2" >}}) uses this configuration end to
end.

## Storage prerequisites

<!-- vale Google.Acronyms = NO -->
The cache PVC needs a `ReadWriteMany` (RWX) StorageClass on the workload cluster.
What the platform admin must set up depends on the cloud:
<!-- vale Google.Acronyms = YES -->

- **GKE:** auto-provisioned on Filestore. Nothing for the admin to do.
- **EKS:** auto-provisioned on EFS. Nothing for the admin to do.
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
the [InferenceCluster]({{< ref "platform/inference-cluster.md" >}}). The ML
team's `ModelCache` and `ModelDeployment` specs are unchanged regardless.
<!-- vale Google.Acronyms = YES -->

## Example

{{< manifests "concepts/model-cache.yaml" >}}
<!-- vale write-good.Passive = YES -->
