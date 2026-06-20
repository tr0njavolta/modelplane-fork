---
title: Examples
weight: 45
description: Validated, end-to-end recipes for serving specific models.
---
<!-- vale write-good.Passive = NO -->
Each recipe here was run end to end: the `ModelCache` hydrated, the replica
became ready, and a chat completion (and a tool call) returned through the
`ModelService`. The `InferenceClass` and `ModelDeployment` are the exact
manifests from those runs. Surrounding resources an example needs but the run
didn't pin (an `InferenceCluster`, a `ModelService`) are filled in to make each
recipe self-contained.

Apply a recipe's files in order: the `InferenceClass` and `InferenceCluster`
first (platform side), then the `ModelCache` if it has one, then the
`ModelDeployment` and `ModelService` (ML side). Files carrying a placeholder
(a GCP project, an EC2 capacity reservation) or a referenced Secret (a Hugging
Face token) need editing or a prerequisite before they apply.

## Qwen3-8B

An 8.2B dense chat model on a single NVIDIA L4. The smallest recipe: one
`Standalone` engine, no cache, weights pulled straight from Hugging Face.

### Platform

{{< manifests "examples/qwen3-8b/inference-class.yaml" >}}

{{< manifests "examples/qwen3-8b/inference-cluster.yaml" >}}

### Deployment

{{< manifests "examples/qwen3-8b/model-deployment.yaml" >}}

{{< manifests "examples/qwen3-8b/model-service.yaml" >}}

## Qwen3-Coder-480B

A 480B code MoE (35B active). Two validated shapes: the BF16 weights span two
H200 nodes as a gang over EFA, served from a `ModelCache`; the FP8 checkpoint
fits one node, so it runs as a single `Standalone` engine on SGLang with no
cache.

### Platform

{{< tabs >}}
{{< tab "Multi-node (BF16)" >}}
{{< manifests "examples/qwen3-coder/inference-class.yaml" >}}

{{< manifests path="examples/qwen3-coder/inference-cluster.yaml" apply="false" >}}

{{< editCode >}}
```bash
curl -fsSL {{< manifest-url "examples/qwen3-coder/inference-cluster.yaml" >}} \
  | sed 's/cr-0123456789abcdef0/$@<your-reservation-id>$@/' \
  | kubectl apply -f -
```
{{< /editCode >}}
{{< /tab >}}
{{< tab "Single-node (FP8)" >}}
{{< manifests "examples/qwen3-coder/inference-class-fp8.yaml" >}}
{{< /tab >}}
{{< /tabs >}}

### Deployment

{{< tabs >}}
{{< tab "Multi-node (BF16)" >}}
{{< manifests "examples/qwen3-coder/model-cache.yaml" >}}

{{< manifests "examples/qwen3-coder/model-deployment.yaml" >}}

{{< manifests "examples/qwen3-coder/model-service.yaml" >}}
{{< /tab >}}
{{< tab "Single-node (FP8)" >}}
{{< manifests "examples/qwen3-coder/model-deployment-fp8.yaml" >}}

{{< manifests "examples/qwen3-coder/model-service-fp8.yaml" >}}
{{< /tab >}}
{{< /tabs >}}

## Kimi-K2

A 1T MoE (1 trillion parameters) served prefill/decode disaggregated across two H200 nodes:
two engines, one per phase, with Modelplane composing the llm-d routing layer
between them. This recipe serves an INT4 quantization of the model; the native
FP8 weights need four such nodes.

### Platform

{{< manifests "examples/kimi-k2/inference-class.yaml" >}}

{{< manifests path="examples/kimi-k2/inference-cluster.yaml" apply="false" >}}

{{< editCode >}}
```bash
curl -fsSL {{< manifest-url "examples/kimi-k2/inference-cluster.yaml" >}} \
  | sed 's/cr-0123456789abcdef0/$@<your-reservation-id>$@/' \
  | kubectl apply -f -
```
{{< /editCode >}}

### Deployment

{{< manifests "examples/kimi-k2/model-cache.yaml" >}}

{{< manifests "examples/kimi-k2/model-deployment.yaml" >}}

{{< manifests "examples/kimi-k2/model-service.yaml" >}}
<!-- vale write-good.Passive = YES -->
