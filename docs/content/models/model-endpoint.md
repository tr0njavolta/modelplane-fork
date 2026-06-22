---
title: Route to External Providers
weight: 40
description: A reachable inference endpoint, composed per replica or created manually for external providers.
---
**API:** [`modelplane.ai/v1alpha1` · ModelEndpoint]({{< ref "/reference/modelendpoints" >}})
<!-- vale write-good.Passive = NO -->
A `ModelEndpoint` is a single reachable inference endpoint that a
[`ModelService`]({{< ref "model-service.md" >}}) can route to. Modelplane creates
one for each of your replicas automatically, but you can also create one by hand
to point at an inference endpoint Modelplane doesn't run, most often a SaaS
provider like Together or Baseten. A service treats both the same, so you can
front your own replicas and an external provider behind one URL: send overflow to
the provider when your fleet is busy, or fail over to it as a break-glass option.

## Routing to an external provider

Create a `ModelEndpoint` with three things:

```yaml {nocopy=true}
apiVersion: modelplane.ai/v1alpha1
kind: ModelEndpoint
metadata:
  name: kimi-k2-together
  namespace: ml-team
  labels:
    # 1. A label a ModelService selects on. Reusing a deployment's
    #    modelplane.ai/deployment label puts this endpoint behind the same
    #    service as that deployment's own replicas.
    modelplane.ai/deployment: kimi-k2
spec:
  # 2. The provider's base URL.
  url: https://api.together.xyz/
  # 3. The path to rewrite requests to. A ModelService receives requests at
  #    /<namespace>/<service>/v1/... and rewrites them to this prefix, so an
  #    OpenAI-compatible provider that serves /v1/... takes /v1/.
  rewritePath: /v1/
```

Then point a `ModelService` at it. With the label above, a service selecting
`modelplane.ai/deployment: kimi-k2` reaches both the deployment's replicas and
this provider, splitting traffic across them. Give the endpoint a label of its
own instead if you want a service that routes only to the provider. See
[Expose a Model]({{< ref "model-service.md" >}}) for selecting and combining
endpoints.

The provider must speak the OpenAI API, since that's the contract a
`ModelService` exposes. Anything OpenAI-compatible works; `url` and `rewritePath`
are all that change between providers.
<!-- vale write-good.Passive = YES -->

## Example

{{< manifests "concepts/model-endpoint.yaml" >}}
