---
title: Scale to a multi-cluster fleet
weight: 20
description: Extend a single cluster to a fleet and schedule models by hardware capability.
---

<!-- vale write-good.Passive = NO -->
This guide extends the setup from [the previous guide]({{< ref
"getting-started/first-deployment.md" >}}). 

You'll add two larger GPU clusters in different regions and raise the memory
threshold in the `qwen-demo` deployment. Modelplane moves the replicas to the
qualifying hardware.

By the end, one `ModelDeployment` will run replicas across two `L40S` clusters,
routed through the same endpoint you curled in Part 1. The `L4` cluster will
still be present but skipped because it no longer meets the selector.

Provisioning two more clusters takes about 10–15 minutes.


## Scale your inference fleet

<!-- vale write-good.TooWordy = NO -->

Register two more clusters with a bigger hardware class: `L40S` (`48 Gi`):

<!-- vale write-good.TooWordy  = YES -->

```bash
kubectl apply -f - <<'EOF'
apiVersion: modelplane.ai/v1alpha1
kind: InferenceClass
metadata:
  name: l40s-1x-g6e
spec:
  description: "EKS g6e.xlarge, 1x NVIDIA L40S"
  provisioning:
    provider: EKS
    eks:
      instanceType: g6e.xlarge
      diskSizeGb: 100
      accelerator:
        type: nvidia-l40s
        count: 1
  devices:
  - name: gpu
    claim: DRA
    driver: gpu.nvidia.com
    deviceClassName: gpu.nvidia.com
    count: 1
    attributes:
      architecture: { string: Ada Lovelace }
    capacity:
      memory: { value: "46068Mi" }
---
apiVersion: modelplane.ai/v1alpha1
kind: InferenceCluster
metadata:
  name: eks-us-west
  labels:
    modelplane.ai/region: us-west
spec:
  cluster:
    source: EKS
    eks:
      region: us-west-2
  nodePools:
  - name: gpu-l40s
    className: l40s-1x-g6e
    nodeCount: 1
    minNodeCount: 1
    maxNodeCount: 1
    zones:
    - us-west-2a
---
apiVersion: modelplane.ai/v1alpha1
kind: InferenceCluster
metadata:
  name: eks-eu-west
  labels:
    modelplane.ai/region: eu-west
spec:
  cluster:
    source: EKS
    eks:
      region: eu-west-1
  nodePools:
  - name: gpu-l40s
    className: l40s-1x-g6e
    nodeCount: 1
    minNodeCount: 1
    maxNodeCount: 1
    zones:
    - eu-west-1b
EOF
```

Modelplane provisions both clusters in parallel:

```bash
kubectl wait --for=condition=Ready ic --all --timeout=20m
```

{{< hint "note" >}}
`g6e.xlarge` runs ~$2/hr on demand. Two of them plus the `L4` from Part 1 is a
few dollars for this guide. Delete the clusters when you're done (see [Clean
up](#clean-up)). 
{{< /hint >}}

## Request new hardware for your model

```mermaid
graph LR
    subgraph pt ["Platform team"]
        IC1["eks-us-east\nL4 · 24Gi"]
        IC2["eks-us-west\nL40S · 48Gi"]
        IC3["eks-eu-west\nL40S · 48Gi"]
    end

    sel["memory >= 40Gi"]

    IC2 -- "48Gi ✓" --> sel
    IC3 -- "48Gi ✓" --> sel
    IC1 -. "24Gi · skipped" .-> sel

    subgraph ml ["ML team"]
        MD["ModelDeployment\nmemory >= 40Gi\nreplicas: 2"]
        EP["unified endpoint\n/ml-team/qwen/v1/..."]
    end

    sel --> MD
    MD --> EP
```
Update the `qwen-demo` deployment with a higher memory threshold and two replicas:

```bash
kubectl apply -f - <<'EOF'
apiVersion: modelplane.ai/v1alpha1
kind: ModelDeployment
metadata:
  name: qwen-demo
  namespace: ml-team
spec:
  replicas: 2
  engines:
  - name: qwen
    members:
    - role: Standalone
      nodeSelector:
        devices:
        - name: gpu
          count: 1
          selectors:
          - cel: |
              device.capacity["gpu.nvidia.com"].memory.compareTo(quantity("40Gi")) >= 0
      template:
        spec:
          containers:
          - name: engine
            image: vllm/vllm-openai:v0.11.0
            args:
            - "--model=Qwen/Qwen2.5-0.5B-Instruct"
            - "--dtype=half"
EOF
```

Wait until `REPLICAS` shows `2`:

```bash
kubectl get md -n ml-team --watch
```

Check replica placement:

```bash
kubectl get modelreplica -n ml-team
```

```shell
NAME              CLUSTER        SYNCED   READY   COMPOSITION                   AGE
qwen-demo-7323a   eks-us-west    True     True    modelreplicas.modelplane.ai   8m
qwen-demo-92535   eks-eu-west    True     True    modelreplicas.modelplane.ai   29m
```

The endpoint URL doesn't change. The gateway picks up the new replicas
automatically.

Any new `L40S` cluster that becomes `Ready` is eligible automatically. The same
`ModelService` fronts both regions, so losing one cluster keeps the other
serving. Two regions, one endpoint.


## Clean up

Delete model resources before clusters:

```bash
kubectl delete md --all -n ml-team
kubectl delete ms --all -n ml-team
```

Wait for all model replicas to finish:

```bash
kubectl get modelreplica -n ml-team --watch
```

Delete all clusters with foreground cascading deletion. The serving stack on
each workload cluster must uninstall while that cluster's API server is still
reachable. Foreground deletion holds each cluster object until its stack
finishes; background deletion can orphan cloud resources.

```bash
kubectl delete ic --all --cascade=foreground
```

Wait until all clusters are deleted:

```bash
kubectl get ic --watch
```

Delete the kind cluster:

```bash
kind delete cluster --name modelplane
```
<!-- vale write-good.Passive = YES -->

## Next steps

In this guide, you scaled an inference stack deployment hardware to support 
your model deployment. You created new clusters and were able to deploy models
to the appropriate cluster based on hardware needs.

* [Build the inference stack platform]({{< ref "platform/" >}})
* [Deploy and manage models]({{< ref "models/" >}})

Star the [Modelplane project on GitHub](https://github.com/modelplaneai/modelplane) and build with us.
