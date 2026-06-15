---
title: Manage the Serving Stack
weight: 40
description: The serving substrate Modelplane installs on every managed cluster.
---
<!-- vale write-good.Passive = NO -->
A `ServingStack` installs the serving substrate on a Kubernetes cluster:
LeaderWorkerSet, Envoy Gateway, Gateway API, cert-manager, Prometheus, Node
Feature Discovery, and the NVIDIA DRA driver. Modelplane composes one
automatically on every `InferenceCluster` it manages — don't create these
directly.

NFD labels GPU nodes so the NVIDIA DRA driver targets its kubelet plugin to
them. The NVIDIA DRA driver publishes GPUs as DRA ResourceSlices and the
`gpu.nvidia.com` DeviceClass that `ModelReplica` ResourceClaims bind through.

**API:** [`infrastructure.modelplane.ai/v1alpha1` · ServingStack]({{< ref "reference.md" >}}#crd-servingstack)

Platform teams interact with the serving stack indirectly: Modelplane installs
and upgrades it as part of cluster lifecycle. If a cluster's stack is
unhealthy, check the `ServingStack` status on the workload cluster:

```bash
kubectl get servingstack -n modelplane-system
```
<!-- vale write-good.Passive = YES -->
