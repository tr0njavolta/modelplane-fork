from .lib import resource as libresource
from .model.ai.modelplane.clustermodel import v1alpha1 as cmv1alpha1
from .model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from .model.ai.modelplane.inferencegateway import v1alpha1 as igwv1alpha1
from .model.ai.modelplane.modeldeployment import v1alpha1 as mdv1alpha1
from .model.ai.modelplane.modelreplica import v1alpha1 as mrv1alpha1
from .model.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1
from .model.io.upbound.dev.meta.compositiontest import v1alpha1 as compositiontest

test = compositiontest.CompositionTest(
    metadata=metav1.ObjectMeta(
        name="model-deployment-incompatible-cluster",
    ),
    spec=compositiontest.Spec(
        compositionPath="apis/modeldeployments/composition.yaml",
        xrPath="tests/test-model-deployment-incompatible-cluster/xr.yaml",
        xrdPath="apis/modeldeployments/definition.yaml",
        timeoutSeconds=120,
        validate=False,
        # extraResources is the up CLI's name for required resources.
        # These are resources the function reads but doesn't own, resolved
        # by Crossplane at runtime via response.require_resources().
        extraResources=[
            # Compatible: labels match the model's environmentSelector.
            libresource.model_to_fixture(
                icv1alpha1.InferenceCluster(
                    metadata=metav1.ObjectMeta(
                        name="compatible-cluster",
                        labels={
                            "modelplane.ai/cluster": "true",
                            "modelplane.ai/region": "us-central",
                        },
                    ),
                    spec=icv1alpha1.Spec(cluster=icv1alpha1.Cluster(source="Existing")),
                    status=icv1alpha1.Status(
                        providerConfigRef=icv1alpha1.ProviderConfigRef(
                            name="compatible-cluster-kubeconfig",
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
            # Incompatible: missing the modelplane.ai/region label that
            # the model's environmentSelector requires.
            libresource.model_to_fixture(
                icv1alpha1.InferenceCluster(
                    metadata=metav1.ObjectMeta(
                        name="incompatible-cluster",
                        labels={"modelplane.ai/cluster": "true"},
                    ),
                    spec=icv1alpha1.Spec(cluster=icv1alpha1.Cluster(source="Existing")),
                    status=icv1alpha1.Status(
                        providerConfigRef=icv1alpha1.ProviderConfigRef(
                            name="incompatible-cluster-kubeconfig",
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
            # The ClusterModel with an environmentSelector requiring
            # us-central — won't match incompatible-cluster.
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
                                name="vllm",
                                environmentSelector=cmv1alpha1.EnvironmentSelector(
                                    matchLabels={"modelplane.ai/region": "us-central"},
                                ),
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
        ],
        assertResources=[
            # Assert only the compatible cluster gets a replica.
            libresource.model_to_dict(
                mrv1alpha1.ModelReplica(
                    metadata=metav1.ObjectMeta(
                        annotations={
                            "crossplane.io/composition-resource-name": "replica-compatible-cluster",
                        },
                        name="qwen-demo-compatible-cluster",
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
                            name="compatible-cluster",
                        ),
                    ),
                )
            ),
            # Assert the XR status shows 1 replica, not 2.
            libresource.model_to_dict(
                mdv1alpha1.ModelDeployment(
                    metadata=metav1.ObjectMeta(
                        name="qwen-demo",
                        namespace="ml-team",
                    ),
                    spec=mdv1alpha1.Spec(
                        modelRef=mdv1alpha1.ModelRef(name="qwen-0.5b"),
                        clusters=1,
                    ),
                    status=mdv1alpha1.Status(
                        model=mdv1alpha1.Model(name="Qwen/Qwen2.5-0.5B-Instruct"),
                        replicas=mdv1alpha1.Replicas(total=1, ready=0),
                        endpoint=mdv1alpha1.Endpoint(
                            url="http://10.0.0.100/ml-team/qwen-demo/v1/chat/completions",
                        ),
                    ),
                )
            ),
        ],
    ),
)
