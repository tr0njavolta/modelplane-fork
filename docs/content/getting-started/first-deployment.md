---
title: Create your first inference platform and model deployment
weight: 10
description: Provision a single GPU cluster and deploy a model.
---
<!-- vale write-good.Passive = NO -->
Modelplane is an open source control plane for AI inference. It separates two
concerns: building a GPU cluster fleet with published hardware capabilities, and
deploying models against those capabilities.

In this guide, you'll provision one GPU cluster and serve a small model. You'll
send a request to your model endpoint and get a response.

This guide uses AWS EKS, but Modelplane supports GKE as well.

Provisioning one GPU cluster takes about 15 minutes.

## Prerequisites

You need:

- [kind](https://kind.sigs.k8s.io/), [kubectl](https://kubernetes.io/docs/tasks/tools/),
  [Helm](https://helm.sh/docs/intro/install/) installed on your machine
- An AWS account with permissions to create EKS clusters, VPCs, and IAM roles
- AWS access key ID and secret access key

## Build your inference platform

This section sets up the inference platform. This includes creating a control
plane to manage your clusters, creating cluster networking, and publishing
hardware capabilities.

### Install the control plane

You'll run Modelplane's control plane in a local kind cluster. Crossplane
provides the reconciliation engine, package management, and
infrastructure as code layer.

{{< hint "note" >}}
You can run your Modelplane control plane anywhere. This guide uses kind for
illustration. 
{{< /hint >}}

```bash
kind create cluster --name modelplane
```

Install Crossplane with Helm:

```bash
helm repo add crossplane-stable https://charts.crossplane.io/stable
helm repo update crossplane-stable
helm install crossplane crossplane-stable/crossplane \
  --namespace crossplane-system --create-namespace \
  --set "args={--enable-dependency-version-upgrades}" \
  --wait
```

Apply the bootstrap resources. This grants Crossplane the permissions necessary
to manage your cluster:

```shell
kubectl apply -f {{< manifest-url "qwen-demo/00-prerequisites.yaml" >}}
```

{{< expand "Review the prerequisites manifest" >}}
{{< manifests "qwen-demo/00-prerequisites.yaml" >}}
{{< /expand >}}

### Install Modelplane

<!--- TODO(tr0njavolta): explain the Modelplane configuration via Crossplane --->

```bash
kubectl apply -f - <<'EOF'
apiVersion: pkg.crossplane.io/v1
kind: Configuration
metadata:
  name: modelplane
spec:
  package: xpkg.upbound.io/modelplane/modelplane:{{<version>}}
EOF
```

Wait until the configuration is healthy:

```bash
kubectl wait configuration/modelplane --for=condition=Healthy --timeout=5m
```

### Configure cloud credentials

Create an AWS credentials file:

{{< editCode >}}
```ini {copy-lines="all"}
[default]
aws_access_key_id = $@<aws_access_key>$@
aws_secret_access_key = $@<aws_secret_key>$@
```
{{< /editCode >}}

{{< editCode >}}

Create a Kubernetes secret:

```ini
kubectl create secret generic aws-creds \
  --from-file=credentials=$@</path/to/aws-credentials>$@ \
  -n crossplane-system
```

Apply the `ClusterProviderConfig` referencing your secret:

{{< /editCode >}}

```bash
kubectl apply -f - <<'EOF'
apiVersion: aws.m.upbound.io/v1beta1
kind: ClusterProviderConfig
metadata:
  name: default
spec:
  credentials:
    source: Secret
    secretRef:
      namespace: crossplane-system
      name: aws-creds
      key: credentials
EOF
```

### Set up the InferenceGateway

The `InferenceGateway` installs Traefik Proxy and MetalLB on the control plane.
Traefik routes inference traffic to model replicas. MetalLB assigns Traefik's
`LoadBalancer` service an external IP on kind, which doesn't have a cloud load
balancer. You need one per control plane, always named `default`.

If you run the control plane on a cloud cluster with native `LoadBalancer`
support, omit the `loadBalancer` field entirely.

{{< manifests "platform/inference-gateway.yaml" >}}

Wait until the gateway is ready:

```bash
kubectl wait --for=condition=Ready ig/default --timeout=5m
```

### Publish hardware and register the cluster

<!--- TODO(tr0njavolta): explain the DRA claim use hovercode --->


```bash
kubectl apply -f - <<'EOF'
apiVersion: modelplane.ai/v1alpha1
kind: InferenceClass
metadata:
  name: l4-1x-g6
spec:
  description: "EKS g6.xlarge, 1x NVIDIA L4"
  provisioning:
    provider: EKS
    eks:
      instanceType: g6.xlarge
      diskSizeGb: 50
      accelerator:
        type: nvidia-l4
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
      memory: { value: "23034Mi" }
---
apiVersion: modelplane.ai/v1alpha1
kind: InferenceCluster
metadata:
  name: eks-us-east
  labels:
    modelplane.ai/region: us-east
spec:
  cluster:
    source: EKS
    eks:
      region: us-east-1
  nodePools:
  - name: gpu-l4
    className: l4-1x-g6
    nodeCount: 1
    minNodeCount: 1
    maxNodeCount: 1
    zones:
    - us-east-1b
EOF
```

Modelplane provisions the cluster. This takes about 15 minutes:

```bash
kubectl wait --for=condition=Ready ic/eks-us-east --timeout=20m
```

Modelplane registers the cluster and installs the serving stack. Now you're ready to deploy a model.


## Deploy the model

In this section, you'll use the platform you just created to request and serve a
model based on your hardware needs.

### Create a deployment

Create a new namespace and apply the deployment:
```bash
kubectl create namespace ml-team
```

The `ModelDeployment` allows you to declare what the model needs; Modelplane
finds the cluster that satisfies it. The device selector matches against the
capacity declared in the `InferenceClass`. Any L4 node satisfies `>= 20Gi`.
Modelplane places the replica on the cluster.

Apply the deployment:

```bash
kubectl apply -f - <<'EOF'
apiVersion: modelplane.ai/v1alpha1
kind: ModelDeployment
metadata:
  name: qwen-demo
  namespace: ml-team
spec:
  replicas: 1
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
              device.capacity["gpu.nvidia.com"].memory.compareTo(quantity("20Gi")) >= 0
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

Wait until `REPLICAS` shows `1`:

```bash
kubectl get md -n ml-team --watch
```

To see which cluster the scheduler chose:

```bash
kubectl get modelreplica -n ml-team
```

```shell
NAME              CLUSTER       SYNCED   READY   COMPOSITION                   AGE
qwen-demo-7323a   eks-us-east   True     True    modelreplicas.modelplane.ai   12m
```

### Expose the model

A `ModelService` selects `ModelEndpoints` by label and creates a Gateway API
`HTTPRoute` that routes to them. Modelplane creates one `ModelEndpoint` per
replica, labeled with the deployment name:

{{< manifests "deployment/model-service.yaml" >}}

The path is `/<namespace>/<modelservice-name>/...`(`/ml-team/qwen/`) in this
example, from
the `ModelService` named `qwen`. The `model` field in
the request body is the Hugging Face id `Qwen/Qwen2.5-0.5B-Instruct`, since this
deployment doesn't set `--served-model-name`.

### Send a request

Send a request to the endpoint:

```bash
kubectl run -i --rm curl-test \
  --image=curlimages/curl \
  --restart=Never \
  -- curl -s http://172.18.255.200/ml-team/qwen/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-0.5B-Instruct",
    "messages": [{"role": "user", "content": "What is Crossplane in one sentence?"}],
    "max_tokens": 100
  }'
```

You should get a response in a few seconds:

```json
{
  "id": "chatcmpl-217f0efa-4b57-40bb-a7dc-f31047a9ba45",
  "object": "chat.completion",
  "created": 1781713612,
  "model": "Qwen/Qwen2.5-0.5B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Crossplane is a cross-cloud service orchestration platform
        designed to facilitate seamless deployment and management of
        applications and infrastructure across various distributed cloud
        environments." },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 37,
    "completion_tokens": 28,
    "total_tokens": 65
  }
}
```



<!-- vale write-good.Passive = YES -->

## Next steps

<!-- vale write-good.TooWordy = NO -->
One cluster and one replica is enough to see the system work. When you're ready
to scale, the [next guide]({{< ref "getting-started/scale-to-fleet.md" >}})
adds two bigger clusters and shows how raising the CEL threshold in the same
`ModelDeployment` moves the replicas to the hardware that qualifies.
<!-- vale write-good.TooWordy  = YES -->

For more on the resources you created:

* [InferenceClass]({{< ref "platform/inference-class.md" >}})
* [InferenceCluster]({{< ref "platform/inference-cluster.md" >}})
* [ModelDeployment]({{< ref "models/model-deployment.md" >}})

{{<expand "Ready to take a break? Clean up your deployment and come back when you're ready for the next guide" >}}
Delete the `ModelDeployment` before the `InferenceCluster`. Deleting the cluster
first leaves the deployment trying to reconcile against infrastructure that no
longer exists.

```bash
kubectl delete md --all -n ml-team
kubectl delete ms --all -n ml-team
```

Wait for model replicas to finish:

```bash
kubectl get modelreplica -n ml-team --watch
```

Delete the cluster with foreground cascading deletion. The serving stack runs on
the workload cluster and must uninstall while that cluster's API server is still
reachable. Foreground deletion holds the cluster object until the stack
finishes; background deletion can orphan cloud resources.

```bash
kubectl delete ic eks-us-east --cascade=foreground
```

Wait until the cluster is deleted:

```bash
kubectl get ic --watch
```

Delete the kind cluster:

```bash
kind delete cluster --name modelplane
```

{{</expand>}}
