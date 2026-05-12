from .lib import resource as libresource
from .model.ai.modelplane.clustermodel import v1alpha1 as cmv1alpha1
from .model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from .model.ai.modelplane.inferencegateway import v1alpha1 as igwv1alpha1
from .model.ai.modelplane.modelreplica import v1alpha1 as mrv1alpha1
from .model.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1
from .model.io.upbound.dev.meta.compositiontest import v1alpha1 as compositiontest

test = compositiontest.CompositionTest(
    metadata=metav1.ObjectMeta(
        name="model-deployment-stable-scheduling",
    ),
    spec=compositiontest.Spec(
        compositionPath="apis/modeldeployments/composition.yaml",
        xrPath="tests/test-model-deployment-stable-scheduling/xr.yaml",
        xrdPath="apis/modeldeployments/definition.yaml",
        timeoutSeconds=120,
        validate=False,
        # extraResources is the up CLI's name for required resources.
        # These are resources the function reads but doesn't own, resolved
        # by Crossplane at runtime via response.require_resources().
        extraResources=[
            # cluster-a: a new cluster that just came online. Sorts first
            # lexicographically, so without the stability sort it would
            # displace cluster-b's existing replica.
            libresource.model_to_fixture(
                icv1alpha1.InferenceCluster(
                    metadata=metav1.ObjectMeta(
                        name="cluster-a",
                        labels={"modelplane.ai/cluster": "true"},
                    ),
                    spec=icv1alpha1.Spec(cluster=icv1alpha1.Cluster(source="Existing")),
                    status=icv1alpha1.Status(
                        providerConfigRef=icv1alpha1.ProviderConfigRef(
                            name="cluster-a-cluster",
                        ),
                        gateway=icv1alpha1.Gateway(address="10.0.0.1"),
                        capacity=icv1alpha1.Capacity(
                            gpuPools=[
                                icv1alpha1.GpuPool(
                                    acceleratorType="nvidia-l4",
                                    countPerNode=1,
                                    nodes=2,
                                    memory="24Gi",
                                )
                            ],
                        ),
                    ),
                )
            ),
            # cluster-b: already has a replica (simulated via observedResources).
            # Both are compatible, but with clusters=1 the scheduler should
            # prefer cluster-b because it already has an observed replica —
            # even though cluster-a sorts first lexicographically.
            libresource.model_to_fixture(
                icv1alpha1.InferenceCluster(
                    metadata=metav1.ObjectMeta(
                        name="cluster-b",
                        labels={"modelplane.ai/cluster": "true"},
                    ),
                    spec=icv1alpha1.Spec(cluster=icv1alpha1.Cluster(source="Existing")),
                    status=icv1alpha1.Status(
                        providerConfigRef=icv1alpha1.ProviderConfigRef(
                            name="cluster-b-cluster",
                        ),
                        gateway=icv1alpha1.Gateway(address="10.0.0.2"),
                        capacity=icv1alpha1.Capacity(
                            gpuPools=[
                                icv1alpha1.GpuPool(
                                    acceleratorType="nvidia-l4",
                                    countPerNode=1,
                                    nodes=2,
                                    memory="24Gi",
                                )
                            ],
                        ),
                    ),
                )
            ),
            # The ClusterModel referenced by spec.modelRef.
            libresource.model_to_fixture(
                cmv1alpha1.ClusterModel(
                    metadata=metav1.ObjectMeta(name="qwen-0.5b"),
                    spec=cmv1alpha1.Spec(
                        model=cmv1alpha1.Model(name="Qwen/Qwen2.5-0.5B-Instruct"),
                        source="HuggingFace",
                        huggingFace=cmv1alpha1.HuggingFace(
                            repo="Qwen/Qwen2.5-0.5B-Instruct",
                        ),
                        resources=cmv1alpha1.Resources(vram="2Gi"),
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
            # The InferenceGateway.
            libresource.model_to_fixture(
                igwv1alpha1.InferenceGateway(
                    metadata=metav1.ObjectMeta(name="default"),
                    spec=igwv1alpha1.Spec(backend="EnvoyGateway"),
                    status=igwv1alpha1.Status(address="10.0.0.100"),
                )
            ),
            # The existing replica on cluster-b, also visible as a required
            # resource so the scheduler knows cluster-b already has a replica.
            libresource.model_to_fixture(
                mrv1alpha1.ModelReplica(
                    metadata=metav1.ObjectMeta(
                        name="qwen-demo-cluster-b",
                        namespace="ml-team",
                        labels={
                            "modelplane.ai/replica": "true",
                            "modelplane.ai/deployment": "qwen-demo",
                        },
                    ),
                    spec=mrv1alpha1.Spec(
                        modelRef=mrv1alpha1.ModelRef(
                            kind="ClusterModel",
                            name="qwen-0.5b",
                        ),
                        inferenceClusterRef=mrv1alpha1.InferenceClusterRef(
                            name="cluster-b",
                        ),
                    ),
                )
            ),
        ],
        # Simulate a second reconcile where replica-cluster-b already exists.
        # The scheduler should keep cluster-b, not reschedule to cluster-a.
        observedResources=[
            libresource.model_to_dict(
                mrv1alpha1.ModelReplica(
                    metadata=metav1.ObjectMeta(
                        name="qwen-demo-cluster-b",
                        namespace="ml-team",
                        annotations={
                            "crossplane.io/composition-resource-name": "replica-cluster-b",
                        },
                        labels={
                            "modelplane.ai/replica": "true",
                            "modelplane.ai/deployment": "qwen-demo",
                        },
                    ),
                    spec=mrv1alpha1.Spec(
                        modelRef=mrv1alpha1.ModelRef(
                            kind="ClusterModel",
                            name="qwen-0.5b",
                        ),
                        inferenceClusterRef=mrv1alpha1.InferenceClusterRef(
                            name="cluster-b",
                        ),
                    ),
                )
            ),
        ],
        assertResources=[
            # Assert the replica stays on cluster-b, not rescheduled to cluster-a.
            libresource.model_to_dict(
                mrv1alpha1.ModelReplica(
                    metadata=metav1.ObjectMeta(
                        annotations={
                            "crossplane.io/composition-resource-name": "replica-cluster-b",
                        },
                        name="qwen-demo-cluster-b",
                        namespace="ml-team",
                        labels={
                            "modelplane.ai/replica": "true",
                            "modelplane.ai/deployment": "qwen-demo",
                        },
                    ),
                    spec=mrv1alpha1.Spec(
                        modelRef=mrv1alpha1.ModelRef(
                            kind="ClusterModel",
                            name="qwen-0.5b",
                        ),
                        inferenceClusterRef=mrv1alpha1.InferenceClusterRef(
                            name="cluster-b",
                        ),
                    ),
                )
            ),
        ],
    ),
)
