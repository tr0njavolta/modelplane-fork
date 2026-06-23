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
you don't create one per cluster.

The `backend` field selects which gateway runs it. `Traefik` is the only value
today.

On a cloud cluster with a native LoadBalancer controller, the gateway's `Service`
gets an external address on its own. On kind or bare-metal, where there's no such
controller, set `spec.traefik.loadBalancer: MetalLB` and give it an address pool
in `spec.traefik.metallb.addressPool` so the gateway gets an IP. See the example
below.

Once the gateway is ready, read its external address from `status.address`:

```bash
kubectl get ig default -o jsonpath='{.status.address}'
```

That address is the host of every `ModelService` URL
(`http://<address>/<namespace>/<service>`), so it's what you hand to ML teams.
## Example

{{< manifests "concepts/inference-gateway.yaml" >}}
<!-- vale write-good.Passive = YES -->
