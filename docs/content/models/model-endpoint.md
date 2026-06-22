---
title: Route to External Providers
weight: 40
description: A reachable inference endpoint, composed per replica or created manually for external providers.
---
**API:** [`modelplane.ai/v1alpha1` · ModelEndpoint]({{< ref "/reference/modelendpoints" >}})
<!-- vale write-good.Passive = NO -->
A `ModelEndpoint` is a reachable inference endpoint. Both shapes use the same
schema, and `ModelService` treats them the same:

- **Composed.** Modelplane creates one `ModelEndpoint` per `ModelReplica`,
  labeled `modelplane.ai/deployment`, `modelplane.ai/cluster`, and
  `modelplane.ai/replica-index`. Its `url` points at the replica's path on the
  workload cluster's gateway.
- **Manual.** Create one by hand to route to an external provider (Together,
  Baseten), setting `url` to the provider's OpenAI-compatible endpoint. Label it
  to match a `ModelService` selector. Reusing a deployment's
  `modelplane.ai/deployment` label puts the external endpoint behind the same
  service as that deployment's replicas, for overflow or break-glass routing.

Modelplane routes to a manual endpoint's `url` as-is. v0.1 doesn't attach
credentials, so an external endpoint that needs an API key isn't supported yet.
<!-- vale write-good.Passive = YES -->

## Example

{{< manifests "concepts/model-endpoint.yaml" >}}
