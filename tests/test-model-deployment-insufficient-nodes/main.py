"""Test that the scheduler rejects clusters with insufficient nodes.

A 405B model (810GiB VRAM) needs ceil(810/80) = 11 H100 GPUs. The
cluster has only 1 node with 8 GPUs (countPerNode=8, count=8).
Multi-node would require 2 nodes but only 1 is available. The
scheduler should produce 0 replicas.
"""

from .lib import resource as libresource
from .model.ai.modelplane.clustermodel import v1alpha1 as cmv1alpha1
from .model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from .model.ai.modelplane.inferencegateway import v1alpha1 as igwv1alpha1
from .model.ai.modelplane.modeldeployment import v1alpha1 as mdv1alpha1
from .model.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1
from .model.io.upbound.dev.meta.compositiontest import v1alpha1 as compositiontest

test = compositiontest.CompositionTest(
    metadata=metav1.ObjectMeta(
        name="model-deployment-insufficient-nodes",
    ),
    spec=compositiontest.Spec(
        compositionPath="apis/modeldeployments/composition.yaml",
        xrPath="tests/test-model-deployment-insufficient-nodes/xr.yaml",
        xrdPath="apis/modeldeployments/definition.yaml",
        timeoutSeconds=120,
        validate=False,
        extraResources=[
            # 1-node H100 cluster: 8 GPUs total, 8 per node. Not enough
            # nodes for a model that needs 11 GPUs (requires 2 nodes).
            libresource.model_to_fixture(
                icv1alpha1.InferenceCluster(
                    metadata=metav1.ObjectMeta(
                        name="small-h100",
                        labels={"modelplane.ai/cluster": "true"},
                    ),
                    spec=icv1alpha1.Spec(cluster=icv1alpha1.Cluster(source="Existing")),
                    status=icv1alpha1.Status(
                        providerConfigRef=icv1alpha1.ProviderConfigRef(
                            name="small-h100-cluster",
                        ),
                        gateway=icv1alpha1.Gateway(address="10.0.0.1"),
                        capacity=icv1alpha1.Capacity(
                            gpuPools=[
                                icv1alpha1.GpuPool(
                                    acceleratorType="nvidia-h100-80gb",
                                    countPerNode=8,
                                    nodes=1,
                                    memory="80Gi",
                                )
                            ],
                        ),
                    ),
                )
            ),
            libresource.model_to_fixture(
                cmv1alpha1.ClusterModel(
                    metadata=metav1.ObjectMeta(name="llama-405b"),
                    spec=cmv1alpha1.Spec(
                        model=cmv1alpha1.Model(name="meta-llama/Llama-3.1-405B"),
                        source="HuggingFace",
                        huggingFace=cmv1alpha1.HuggingFace(
                            repo="meta-llama/Llama-3.1-405B",
                        ),
                        resources=cmv1alpha1.Resources(vram="810Gi"),
                        serving=[
                            cmv1alpha1.ServingItem(
                                name="vllm-kserve",
                                engine=cmv1alpha1.Engine(
                                    name="vLLM",
                                    image="vllm/vllm-openai:v0.7.3",
                                ),
                            ),
                        ],
                    ),
                )
            ),
            libresource.model_to_fixture(
                igwv1alpha1.InferenceGateway(
                    metadata=metav1.ObjectMeta(name="default"),
                    spec=igwv1alpha1.Spec(backend="EnvoyGateway"),
                    status=igwv1alpha1.Status(address="10.0.0.100"),
                )
            ),
        ],
        assertResources=[
            # Assert no replicas — the model needs 2 nodes but only 1
            # is available.
            libresource.model_to_dict(
                mdv1alpha1.ModelDeployment(
                    metadata=metav1.ObjectMeta(
                        name="llama405b-demo",
                        namespace="ml-team",
                    ),
                    spec=mdv1alpha1.Spec(
                        modelRef=mdv1alpha1.ModelRef(name="llama-405b"),
                        clusters=1,
                    ),
                    status=mdv1alpha1.Status(
                        model=mdv1alpha1.Model(name="meta-llama/Llama-3.1-405B"),
                        replicas=mdv1alpha1.Replicas(total=0, ready=0),
                    ),
                )
            ),
        ],
    ),
)
