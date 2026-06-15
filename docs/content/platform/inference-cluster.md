---
title: Register a Cluster
weight: 30
description: A Kubernetes cluster registered with Modelplane for model serving.
---
<!-- vale write-good.Passive = NO -->
An `InferenceCluster` represents a Kubernetes cluster configured for model
serving. Platform teams create these to provide GPU capacity.

**API:** [`modelplane.ai/v1alpha1` · InferenceCluster]({{< ref "reference.md" >}}#crd-inferencecluster)

Each cluster has:

- A **cluster source**: `GKE` or `EKS` (Modelplane provisions the full cluster)
  or `Existing` (bring a cluster you manage yourself).
- One or more **node pools**, each referencing an `InferenceClass` for its
  hardware capabilities and provisioning recipe.
- **Labels** for organizational metadata: tier, region, provider. These are the
  matching surface for `ModelDeployment.clusterSelector`.

Modelplane installs an inference stack (LeaderWorkerSet, llm-d, Dynamo, Envoy
Gateway, etc.) on every cluster it manages. This includes existing clusters,
which Modelplane assumes are solely for its use.

## Examples

{{< tabs >}}
{{< tab "GKE" >}}
Modelplane provisions the full GKE cluster — VPC, subnet, system pool, GPU
pools, service account, and IAM bindings — and installs the inference stack.
Set `spec.cluster.gke.project` to your GCP project ID.

{{< manifests "platform/inference-cluster-gke.yaml" >}}
{{< /tab >}}
{{< tab "EKS" >}}
Modelplane provisions the full EKS cluster — VPC, subnets, internet gateway,
IAM roles, system and GPU node groups, and core addons — and installs the
inference stack.

{{< hint "warning" >}}
EKS does not auto-provision RWX storage for ModelCache. See
[Cache storage](#cache-storage) below.
{{< /hint >}}

{{< manifests "platform/inference-cluster-eks.yaml" >}}
{{< /tab >}}
{{< tab "Existing" >}}
Bring a cluster you already manage. Modelplane installs its inference stack
on the cluster and assumes it is solely for Modelplane's use. Provide a
kubeconfig secret reference under `spec.cluster.existing`.

{{< manifests "platform/inference-cluster-existing.yaml" >}}
{{< /tab >}}
{{< /tabs >}}

## Cache storage

To override the default ReadWriteMany StorageClass Modelplane uses for
[ModelCache]({{< ref "models/model-cache.md#custom-cache-backends" >}}) PVCs on
this cluster, set `cluster.<source>.cache.storageClassName`. See
[Custom cache backends]({{< ref "models/model-cache.md#custom-cache-backends" >}})
for details.
<!-- vale write-good.Passive = YES -->
