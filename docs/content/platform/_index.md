---
title: Build the Inference Stack Platform
weight: 20
description: Resources for platform engineers provisioning GPU clusters and hardware classes for ML teams.
---
<!-- vale write-good.Passive = NO -->
Platform engineers set up the GPU fleet that ML teams deploy models onto. You
create the `InferenceGateway` for control-plane routing, `InferenceClass`
resources defining hardware recipes, and `InferenceClusters` representing
individual GPU clusters.

Modelplane installs the inference stack on every cluster you register — including
existing clusters you bring yourself.

## Resources

- [InferenceGateway]({{< ref "inference-gateway.md" >}}) — unified OpenAI-compatible endpoint on the control plane
- [InferenceClass]({{< ref "inference-class.md" >}}) — hardware recipe defining GPU type, count, and provisioning
- [InferenceCluster]({{< ref "inference-cluster.md" >}}) — a Kubernetes cluster registered for model serving
- [ServingStack]({{< ref "serving-stack.md" >}}) — the serving substrate Modelplane installs on every managed cluster
<!-- vale write-good.Passive = YES -->
