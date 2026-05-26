"""Tests for the compose-model-endpoint function."""

import dataclasses
import unittest

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from function import fn
from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb
from models.ai.modelplane.modelendpoint import v1alpha1
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1


@dataclasses.dataclass
class Case:
    """A test case for compose-model-endpoint."""

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
        """The function composes an Envoy Backend from a ModelEndpoint."""
        cases = [
            Case(
                name="http URL composes a Backend with the correct IP and default port",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct(
                                v1alpha1.ModelEndpoint(
                                    metadata=metav1.ObjectMeta(name="test-endpoint", namespace="ml-team"),
                                    spec=v1alpha1.Spec(url="http://34.55.100.10/default/qwen-demo/v1"),
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
                            "backend": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                                        "kind": "Backend",
                                        "metadata": {"namespace": "ml-team"},
                                        "spec": {"endpoints": [{"ip": {"address": "34.55.100.10", "port": 80}}]},
                                    }
                                ),
                            ),
                        },
                    ),
                    conditions=[
                        fnv1.Condition(
                            type="RoutingReady", status=fnv1.STATUS_CONDITION_FALSE, reason="WaitingForBackend"
                        ),
                    ],
                    context=structpb.Struct(),
                ),
            ),
            Case(
                name="observed backend sets RoutingReady and status.routing.backendName",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct(
                                v1alpha1.ModelEndpoint(
                                    metadata=metav1.ObjectMeta(name="test-endpoint", namespace="ml-team"),
                                    spec=v1alpha1.Spec(url="http://34.55.100.10/default/qwen-demo/v1"),
                                ).model_dump(exclude_none=True, mode="json")
                            ),
                        ),
                        resources={
                            "backend": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                                        "kind": "Backend",
                                        "metadata": {"name": "my-backend", "namespace": "ml-team"},
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
                            resource=resource.dict_to_struct({"status": {"routing": {"backendName": "my-backend"}}}),
                        ),
                        resources={
                            "backend": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    {
                                        "apiVersion": "gateway.envoyproxy.io/v1alpha1",
                                        "kind": "Backend",
                                        "metadata": {"namespace": "ml-team"},
                                        "spec": {"endpoints": [{"ip": {"address": "34.55.100.10", "port": 80}}]},
                                    }
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                        },
                    ),
                    conditions=[
                        fnv1.Condition(
                            type="RoutingReady", status=fnv1.STATUS_CONDITION_TRUE, reason="BackendConfigured"
                        ),
                    ],
                    context=structpb.Struct(),
                ),
            ),
            Case(
                name="invalid URL produces a warning and no backend",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(
                        composite=fnv1.Resource(
                            resource=resource.dict_to_struct(
                                v1alpha1.ModelEndpoint(
                                    metadata=metav1.ObjectMeta(name="test-endpoint", namespace="ml-team"),
                                    spec=v1alpha1.Spec(url="not-a-url"),
                                ).model_dump(exclude_none=True, mode="json")
                            ),
                        ),
                    ),
                ),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
                    desired=fnv1.State(),
                    conditions=[
                        fnv1.Condition(
                            type="RoutingReady",
                            status=fnv1.STATUS_CONDITION_FALSE,
                            reason="InvalidURL",
                            message="spec.url has no host: not-a-url",
                        ),
                    ],
                    results=[
                        fnv1.Result(severity=fnv1.SEVERITY_WARNING, message="Invalid spec.url: not-a-url"),
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
