---
title: FAQ
weight: 35
description: Short answers to the questions practitioners ask about Modelplane first.
---
<!-- vale write-good.Passive = NO -->
Short answers to the questions that come up first, with links to the full
treatment. If you're new here, read the [Introduction]({{< ref "/overview" >}})
and [How Modelplane works]({{< ref "/overview/how-it-works" >}}) first.

## What Modelplane is

### Is Modelplane a serving engine like vLLM?

No. Modelplane is the control plane *above* the engine. It composes serving
engines like vLLM and SGLang and operates them across a fleet of clusters; it
doesn't serve tokens itself. You bring the engine; Modelplane schedules it, routes
to it, scales it, and caches its weights.

### Does Modelplane replace vLLM or SGLang?

No. They run the model; Modelplane runs the fleet. A `ModelDeployment` carries
your engine container and its flags, and Modelplane composes it onto the right
cluster. Switching or upgrading engines is a change to your deployment, not to
Modelplane.

### How is Modelplane different from KServe or NVIDIA Dynamo?

Scope. KServe and Dynamo are cluster orchestrators: they schedule, scale, route,
and cache within a single cluster. Modelplane runs the same control loop across a
fleet of clusters, clouds, and regions. The difference is definitional, not
"better than." A team using a cluster orchestrator today is a natural Modelplane
adopter, and Modelplane composes those layers beneath it.

### How is Modelplane different from a managed provider like Baseten or Together?

Managed providers run fleet-scale serving inside their own closed platform.
Modelplane is the open equivalent that runs in infrastructure you own. The
difference is open, in your own infrastructure, and neutral across the stack, not
scope. You can still route to a managed provider from Modelplane when you want a
fallback.

## What it requires

### Do I need Crossplane?

Yes. Modelplane is built on [Crossplane](https://crossplane.io) and requires it on
the control cluster. If your platform team already runs Crossplane to manage cloud
infrastructure, Modelplane is the same pattern applied to inference.

### Which clouds does Modelplane support?

Today Modelplane provisions clusters on GKE and EKS, and brings in any existing
Kubernetes cluster you point it at. More provisioners are on the roadmap; the
bring-your-own path means you can run on any Kubernetes now.

### Can I bring my own cluster, or run on a neocloud or on-premise?

Yes. An `InferenceCluster` with `source: Existing` registers a cluster you already
run, through its kubeconfig. Modelplane installs the serving stack it needs but
doesn't provision the infrastructure. This is how you run on neoclouds and
on-premise today.

### Which engines and accelerators are supported?

The API is engine-agnostic: any engine that runs as a container works, and its
flags are yours to write. vLLM is the engine proven in v0.1, with SGLang on the
disaggregation path. Accelerators are NVIDIA GPUs bound through DRA today, and the
device model (DRA plus CEL selectors) is built to extend to other accelerators and
fabrics.

## What it can do

### How does Modelplane decide where a model runs?

Two-level matching. First it filters clusters by their labels (tier, region,
provider) against your `clusterSelector`. Then it filters node pools by matching
your device requests, real DRA requests with CEL selectors over GPU memory,
architecture, and so on, against each pool's `InferenceClass`. It places each
replica on a cluster and pool that fits and has free capacity.

### Can I serve across regions and clusters behind one endpoint?

Yes, that's the point. A `ModelService` exposes one OpenAI-compatible endpoint and
load-balances across every replica of a deployment, wherever they run, with
weights for canary and A/B rollouts.

### Can I fall back to a managed provider?

Yes. A `ModelService` can send a slice of traffic to a manually created
`ModelEndpoint` that points at an external SaaS endpoint (for example Together or
Baseten), alongside your self-hosted replicas. Use it for overflow or break-glass
routing.

### How do large or multi-node models work?

An engine can be a gang: a leader and one or more workers that Modelplane composes
into a LeaderWorkerSet across nodes. You write the coordination (for example Ray,
or vLLM's data-parallel coordinator) in the engine flags, and Modelplane injects
the leader's address so the workers can join it. Multi-node deployments stage
weights through a `ModelCache`.

### What about disaggregated prefill/decode?

Set `serving.mode: PrefillDecode` and define separate prefill and decode engines.
They land on the same cluster, hand off the KV cache over a fast fabric, and
Modelplane configures the cluster-edge routing that pairs each request. The
KV-transfer flags live in your engine config.

### How does scaling work?

Replicas are the only scaling axis. Each replica is a complete serving instance;
scaling `spec.replicas` adds or removes whole instances across the fleet. Because
a `ModelDeployment` exposes the Kubernetes scale subresource, `kubectl scale` and
KEDA work without anything extra. There's no per-pod autoscaling inside a cluster.

### How are model weights handled?

A `ModelCache` stages weights once per cluster on shared (ReadWriteMany) storage,
and every pod reads them locally. Pods don't re-download on each start, and
concurrent starts don't race. It hydrates from Hugging Face today, is optional for
single-node deployments, and is required for multi-node ones.

## The project

### Is Modelplane production-ready?

Modelplane is at v0.1: early and moving fast. It's built to show that a
fleet-level inference control plane is viable and to be credible for the models
enterprises actually deploy. Treat it as early software. The
[platform docs]({{< ref "/platform" >}}) are specific about what ships today
versus what's planned.

### What's the license and governance?

Modelplane is [Apache 2.0](https://github.com/modelplaneai/modelplane/blob/main/LICENSE),
with no usage caps or token meters, and is developed in the open. It's neutral
across models, engines, accelerators, and clouds, and is intended for donation to
a neutral open source foundation. It's a project from Upbound, the creators of
Crossplane.

### How do I get involved?

Issues, discussions, and contributions are welcome on
[GitHub](https://github.com/modelplaneai/modelplane). See `CONTRIBUTING.md` for
development setup and the project's conventions.

{{< cardgroup cols="2" >}}
{{< card title="Get started" href="/getting-started/" >}}
Deploy Modelplane and serve your first model.
{{< /card >}}
{{< card title="How Modelplane works" href="/overview/how-it-works/" >}}
The architecture and the control loop, in one page.
{{< /card >}}
{{< /cardgroup >}}
<!-- vale write-good.Passive = YES -->
