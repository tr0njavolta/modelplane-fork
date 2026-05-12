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
        name="model-deployment-basic",
    ),
    spec=compositiontest.Spec(
        compositionPath="apis/modeldeployments/composition.yaml",
        xrPath="tests/test-model-deployment/xr.yaml",
        xrdPath="apis/modeldeployments/definition.yaml",
        timeoutSeconds=120,
        validate=False,
        # extraResources is the up CLI's name for required resources.
        # These are resources the function reads but doesn't own, resolved
        # by Crossplane at runtime via response.require_resources().
        extraResources=[
            # A ready InferenceCluster with KServe backend and one L4 pool.
            libresource.model_to_fixture(
                icv1alpha1.InferenceCluster(
                    metadata=metav1.ObjectMeta(
                        name="demo-us-central",
                        labels={"modelplane.ai/cluster": "true"},
                    ),
                    spec=icv1alpha1.Spec(cluster=icv1alpha1.Cluster(source="Existing")),
                    status=icv1alpha1.Status(
                        providerConfigRef=icv1alpha1.ProviderConfigRef(
                            name="demo-us-central-cluster",
                        ),
                        gateway=icv1alpha1.Gateway(address="34.55.100.10"),
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
                        serving=[
                            cmv1alpha1.ServingItem(
                                name="vllm-kserve",
                                engine=cmv1alpha1.Engine(
                                    name="vLLM",
                                    image="vllm/vllm-openai:v0.7.3",
                                ),
                            ),
                        ],
                        resources=cmv1alpha1.Resources(
                            vram="2Gi",
                            cpu="3",
                            memory="10Gi",
                        ),
                    ),
                )
            ),
            # The InferenceGateway for the control plane routing endpoint.
            libresource.model_to_fixture(
                igwv1alpha1.InferenceGateway(
                    metadata=metav1.ObjectMeta(name="default"),
                    spec=igwv1alpha1.Spec(backend="EnvoyGateway"),
                    status=igwv1alpha1.Status(address="10.0.0.1"),
                )
            ),
        ],
        assertResources=[
            # Assert the XR has status populated with model name and replica
            # count, plus the unified endpoint URL from the inference gateway.
            libresource.model_to_dict(
                mdv1alpha1.ModelDeployment(
                    metadata=metav1.ObjectMeta(
                        name="qwen-demo",
                        namespace="ml-team",
                    ),
                    spec=mdv1alpha1.Spec(
                        modelRef=mdv1alpha1.ModelRef(
                            name="qwen-0.5b",
                        ),
                        clusters=1,
                    ),
                    status=mdv1alpha1.Status(
                        model=mdv1alpha1.Model(
                            name="Qwen/Qwen2.5-0.5B-Instruct",
                        ),
                        replicas=mdv1alpha1.Replicas(
                            total=1,
                            ready=0,
                        ),
                        endpoint=mdv1alpha1.Endpoint(
                            url="http://10.0.0.1/ml-team/qwen-demo/v1/chat/completions",
                        ),
                    ),
                )
            ),
            # Assert a ModelReplica is composed for the matched cluster.
            libresource.model_to_dict(
                mrv1alpha1.ModelReplica(
                    metadata=metav1.ObjectMeta(
                        annotations={
                            "crossplane.io/composition-resource-name": "replica-demo-us-central",
                        },
                        name="qwen-demo-demo-us-central",
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
                            name="demo-us-central",
                        ),
                    ),
                )
            ),
            # Assert an HTTPRoute is composed with the correct path rewrite.
            {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "HTTPRoute",
                "metadata": {
                    "namespace": "ml-team",
                    "annotations": {
                        "crossplane.io/composition-resource-name": "httproute",
                    },
                },
                "spec": {
                    "parentRefs": [
                        {
                            "name": "modelplane",
                            "namespace": "modelplane-system",
                        }
                    ],
                    "rules": [
                        {
                            "matches": [
                                {
                                    "path": {
                                        "type": "PathPrefix",
                                        "value": "/ml-team/qwen-demo/",
                                    },
                                }
                            ],
                            "filters": [
                                {
                                    "type": "URLRewrite",
                                    "urlRewrite": {
                                        "path": {
                                            "type": "ReplacePrefixMatch",
                                            "replacePrefixMatch": "/default/model-qwen-0-5b/",
                                        },
                                    },
                                }
                            ],
                        }
                    ],
                },
            },
        ],
    ),
)
