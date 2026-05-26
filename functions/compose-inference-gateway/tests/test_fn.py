"""Tests for the compose-inference-gateway function."""

import dataclasses
import unittest

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from function import fn
from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb
from models.ai.modelplane.inferencegateway import v1alpha1
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1


@dataclasses.dataclass
class Case:
    """A test case for compose-inference-gateway."""

    name: str
    req: fnv1.RunFunctionRequest
    want: fnv1.RunFunctionResponse


def setUpModule() -> None:
    logging.configure(level=logging.Level.DISABLED)


class TestFunctionRunner(unittest.IsolatedAsyncioTestCase):
    """Tests for FunctionRunner.RunFunction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = fn.FunctionRunner()

    async def test_compose(self) -> None:
        """The function composes an InferenceGateway."""
        cases = [
            Case(
                name="first pass composes provider config only; envoy gateway and gateway are gated",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct(
                                v1alpha1.InferenceGateway(
                                    metadata=metav1.ObjectMeta(
                                        name="test-gateway",
                                        namespace="modelplane-system",
                                    ),
                                    spec=v1alpha1.Spec(),
                                ).model_dump(exclude_none=True, mode="json")
                            ),
                        ),
                    ),
                ),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
                    desired=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct({"status": {}}),
                        ),
                        resources={
                            "provider-config-helm": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "helm.m.crossplane.io/v1beta1",
                                        "kind": "ProviderConfig",
                                        "metadata": {
                                            "name": "modelplane-in-cluster",
                                            "namespace": "modelplane-system",
                                        },
                                        "spec": {"credentials": {"source": "InjectedIdentity"}},
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                        },
                    ),
                    conditions=[
                        fnv1.Condition(
                            type="ControllerReady",
                            status=fnv1.STATUS_CONDITION_FALSE,
                            reason="Installing",
                        ),
                    ],
                    context=structpb.Struct(),
                ),
            ),
            Case(
                name="second pass with observed provider config and envoy gateway ready composes gateway resources",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct(
                                v1alpha1.InferenceGateway(
                                    metadata=metav1.ObjectMeta(
                                        name="test-gateway",
                                        namespace="modelplane-system",
                                    ),
                                    spec=v1alpha1.Spec(),
                                ).model_dump(exclude_none=True, mode="json")
                            ),
                        ),
                        resources={
                            "provider-config-helm": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "helm.m.crossplane.io/v1beta1",
                                        "kind": "ProviderConfig",
                                        "metadata": {"name": "modelplane-in-cluster"},
                                    }
                                ),
                            ),
                            "envoy-gateway": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "helm.m.crossplane.io/v1beta1",
                                        "kind": "Release",
                                        "status": {
                                            "conditions": [{"type": "Ready", "status": "True"}],
                                        },
                                    }
                                ),
                            ),
                            "gateway": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.networking.k8s.io/v1",
                                        "kind": "Gateway",
                                        "metadata": {"name": "modelplane"},
                                        "status": {
                                            "addresses": [{"value": "10.0.0.42"}],
                                            "conditions": [{"type": "Accepted", "status": "True"}],
                                        },
                                    }
                                ),
                            ),
                            "gateway-class": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.networking.k8s.io/v1",
                                        "kind": "GatewayClass",
                                        "metadata": {"name": "envoy"},
                                        "status": {
                                            "conditions": [{"type": "Accepted", "status": "True"}],
                                        },
                                    }
                                ),
                            ),
                        },
                    ),
                ),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
                    desired=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct(
                                {"status": {"address": "10.0.0.42"}},
                            ),
                        ),
                        resources={
                            "provider-config-helm": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "helm.m.crossplane.io/v1beta1",
                                        "kind": "ProviderConfig",
                                        "metadata": {
                                            "name": "modelplane-in-cluster",
                                            "namespace": "modelplane-system",
                                        },
                                        "spec": {"credentials": {"source": "InjectedIdentity"}},
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                            "envoy-gateway": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "helm.m.crossplane.io/v1beta1",
                                        "kind": "Release",
                                        "metadata": {
                                            "namespace": "modelplane-system",
                                            "labels": {"modelplane.ai/release": "envoy-gateway"},
                                        },
                                        "spec": {
                                            "providerConfigRef": {
                                                "kind": "ProviderConfig",
                                                "name": "modelplane-in-cluster",
                                            },
                                            "forProvider": {
                                                "chart": {
                                                    "name": "gateway-helm",
                                                    "repository": "oci://docker.io/envoyproxy",
                                                    "version": "v1.3.0",
                                                },
                                                "namespace": "envoy-gateway-system",
                                                "values": {
                                                    "config": {
                                                        "envoyGateway": {
                                                            "extensionApis": {"enableBackend": True},
                                                        },
                                                    },
                                                },
                                            },
                                        },
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                            "usage-pc-by-envoy-gateway": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "protection.crossplane.io/v1beta1",
                                        "kind": "Usage",
                                        "metadata": {"namespace": "modelplane-system"},
                                        "spec": {
                                            "of": {
                                                "apiVersion": "helm.m.crossplane.io/v1beta1",
                                                "kind": "ProviderConfig",
                                                "resourceRef": {"name": "modelplane-in-cluster"},
                                            },
                                            "by": {
                                                "apiVersion": "helm.m.crossplane.io/v1beta1",
                                                "kind": "Release",
                                                "resourceSelector": {
                                                    "matchControllerRef": True,
                                                    "matchLabels": {"modelplane.ai/release": "envoy-gateway"},
                                                },
                                            },
                                            "replayDeletion": True,
                                        },
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                            "gateway-class": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.networking.k8s.io/v1",
                                        "kind": "GatewayClass",
                                        "metadata": {"name": "envoy"},
                                        "spec": {
                                            "controllerName": "gateway.envoyproxy.io/gatewayclass-controller",
                                        },
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                            "gateway": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.networking.k8s.io/v1",
                                        "kind": "Gateway",
                                        "metadata": {
                                            "name": "modelplane",
                                            "namespace": "modelplane-system",
                                        },
                                        "spec": {
                                            "gatewayClassName": "envoy",
                                            "listeners": [
                                                {
                                                    "name": "http",
                                                    "protocol": "HTTP",
                                                    "port": 80,
                                                    "allowedRoutes": {"namespaces": {"from": "All"}},
                                                },
                                            ],
                                        },
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                        },
                    ),
                    conditions=[
                        fnv1.Condition(
                            type="ControllerReady",
                            status=fnv1.STATUS_CONDITION_TRUE,
                            reason="ControllerHealthy",
                        ),
                    ],
                    context=structpb.Struct(),
                ),
            ),
        ]

        for case in cases:
            with self.subTest(case.name):
                got = await self.runner.RunFunction(case.req, None)
                self.assertEqual(
                    json_format.MessageToDict(case.want),
                    json_format.MessageToDict(got),
                    "-want, +got",
                )
