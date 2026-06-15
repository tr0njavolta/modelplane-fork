---
title: Deploy Models
weight: 30
description: Resources for ML teams deploying models and getting unified endpoints.
---
<!-- vale write-good.Passive = NO -->
ML teams deploy models to the GPU fleet provisioned by platform engineers. You
create `ModelDeployments` carrying everything needed to serve a model, optional
`ModelCaches` to stage weights, and `ModelServices` to expose a unified
OpenAI-compatible endpoint.

**API group:** `modelplane.ai/v1alpha1` · Namespaced

## Resources

- [ModelDeployment]({{< ref "model-deployment.md" >}}) — deploy a model to the fleet with replica count and engine config
- [ModelCache]({{< ref "model-cache.md" >}}) — stage model weights on cluster storage before serving
- [ModelService]({{< ref "model-service.md" >}}) — expose endpoints via a unified OpenAI-compatible URL
- [ModelEndpoint]({{< ref "model-endpoint.md" >}}) — a reachable inference endpoint, composed or manually created
<!-- vale write-good.Passive = YES -->
