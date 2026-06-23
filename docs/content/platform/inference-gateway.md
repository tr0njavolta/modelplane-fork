---
title: Set Up the Gateway
weight: 10
description: Unified OpenAI-compatible endpoint on the control plane cluster.
---
**API:** [`modelplane.ai/v1alpha1` · InferenceGateway]({{< ref "/reference/inferencegateways" >}})
<!-- vale write-good.Passive = NO -->
The `InferenceGateway` sets up the control plane's front door: one unified,
OpenAI-compatible address that every `ModelService` is exposed through, routing
each request on to the inference cluster serving it.

The `InferenceGateway` is a singleton: create exactly one, named `default`, on
your Modelplane control plane. It fronts every inference cluster in the fleet, so
you don't create one per cluster. When running the control plane in kind, set
`loadBalancer: MetalLB` to get a LoadBalancer IP inside the Docker network.

The `backend` field selects which gateway runs it. `Traefik` is the only value
today.

Once ready, read the gateway's external address from the resource's status:

```bash
kubectl get ig default
```
## Example

{{< manifests "concepts/inference-gateway.yaml" >}}
<!-- vale write-good.Passive = YES -->
