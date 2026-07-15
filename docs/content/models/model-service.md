---
title: Expose a Model
weight: 20
description: Expose model endpoints via a unified OpenAI-compatible URL.
---
**API:** [`modelplane.ai/v1alpha1` · ModelService]({{< ref "/reference/modelservices" >}})
<!-- vale write-good.Passive = NO -->
A [`ModelDeployment`]({{< ref "model-deployment.md" >}}) serves a model, but its
replicas are scattered across the fleet with no single address. A `ModelService`
gives them one: a stable, unified, OpenAI-compatible URL that load-balances
across every replica, wherever it runs.

A service selects what to route to by label. Behind the scenes, Modelplane
creates one `ModelEndpoint`, a single reachable backend, for each replica of a
deployment and labels it. Two of those labels carry routing intent:

- `modelplane.ai/deployment`: the deployment the replica belongs to.
- `modelplane.ai/cluster`: the cluster the replica runs on.

Modelplane creates an endpoint only once its replica is Ready, serving and
reachable, and withdraws it if the replica later goes unhealthy. A service only
ever routes to replicas that can actually answer, so a deployment that's still
starting or scaling up has fewer endpoints behind its URL until those replicas
come up. You don't create endpoints yourself. You point a service at them.

`spec.endpoints` is a list, and the entries combine: the service routes to every
endpoint that any entry matches. The patterns below build on that.

## Route to a whole deployment

The common case: one selector matching a deployment's name reaches every replica,
wherever in the fleet they run.

```yaml {nocopy=true}
spec:
  endpoints:
  - selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-8b   # every replica of this deployment
```

## Route to part of a deployment

Add a second label to narrow within a deployment. A selector matches an endpoint
only when all its labels match, so pairing the deployment with a cluster routes to
just that cluster's replicas. This is how you take a cluster out of service
without redeploying: point the service at the clusters you want and leave one out,
and traffic drains to the rest.

```yaml {nocopy=true}
spec:
  endpoints:
  # Only the replicas on prod-us-east, e.g. while draining another cluster.
  - selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-8b
        modelplane.ai/cluster: prod-us-east
```

## Route across several deployments

Give more than one entry to front several deployments behind the same URL. Each
entry contributes its matched endpoints. By default every entry carries equal
weight, so traffic splits evenly between entries and then spreads as evenly as
possible across the endpoints each one matches.

```yaml {nocopy=true}
spec:
  endpoints:
  - selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-8b
  - selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-8b-v2
```

## Split traffic by weight

Set a `weight` on an entry to give it a fixed share of traffic instead of an
equal one. Weights are relative: an entry weighted 80 next to one weighted 20
takes 80% of requests. The weight applies to the entry as a whole and spreads
as evenly as possible across the endpoints it matches, so scaling a deployment
up or down doesn't change its share. An entry without a `weight` defaults to 1.

This is the shape of a canary rollout: send most traffic to the stable deployment
and a sliver to the new one, then shift the ratio as confidence grows.

```yaml {nocopy=true}
spec:
  endpoints:
  - weight: 95
    selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-8b
  - weight: 5
    selector:
      matchLabels:
        modelplane.ai/deployment: qwen3-8b-v2
```

The entries don't have to be deployments. One can select a manually created
[ModelEndpoint]({{< ref "model-endpoint.md" >}}) that points at an external
provider, so a service can send overflow or break-glass traffic to a SaaS
endpoint alongside your own replicas:

```yaml {nocopy=true}
spec:
  endpoints:
  - selector:
      matchLabels:
        modelplane.ai/deployment: kimi-k2
  - selector:
      matchLabels:
        modelplane.ai/external-provider: together
```

Endpoints with different path layouts coexist behind the one URL.

## Sending a request

The service's public address is on `status.address`, in the form
`http://<gateway>/<namespace>/<service-name>`:

```bash
ADDRESS=$(kubectl get ms qwen -n ml-team -o jsonpath='{.status.address}')
```

Append the OpenAI path and send a request. The `model` field is the name the
engine serves (its `--served-model-name`, or the model's Hugging Face id if you
didn't set one):

```bash
curl "$ADDRESS/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Alternate APIs

We call the endpoint OpenAI-compatible because the engines are, not because
Modelplane imposes it. The route matches the `/<namespace>/<service>/` prefix and
preserves the path below it on the way to the engine, so any API the engine serves
is reachable on the same URL.

Take a vLLM replica that also serves the Anthropic Messages API. It answers on
`.../v1/messages`, so a client that speaks it (including Claude Code, via
`ANTHROPIC_BASE_URL`) talks to it directly. The engine's operational paths come
through the same way: `.../health` and the Prometheus `.../metrics` are reachable
on the service URL.

There's one exception, and it's set by the deployment rather than the service.
[Disaggregated serving]({{< ref "model-deployment.md#disaggregated-serving" >}})
reads OpenAI-format request bodies to pick a prefill and decode worker, so a
request in another API shape still reaches the engine but skips that
cache-aware routing. Unified serving forwards every API shape the same way.

## Example

{{< manifests "concepts/model-service.yaml" >}}
<!-- vale write-good.Passive = YES -->
