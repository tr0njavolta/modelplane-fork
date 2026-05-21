"""Tests for the compose-model-service function."""

import dataclasses
import unittest

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from function import fn
from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb
from models.ai.modelplane.modelservice import v1alpha1
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1


@dataclasses.dataclass
class Case:
    """A test case for compose-model-service."""

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
        """The function composes an HTTPRoute from a ModelService."""

        xr = v1alpha1.ModelService(
            metadata=metav1.ObjectMeta(name="test-service", namespace="ml-team"),
            spec=v1alpha1.Spec(
                endpoints=[v1alpha1.Endpoint(selector=v1alpha1.Selector(matchLabels={"app": "model"}))],
            ),
        ).model_dump(exclude_none=True, mode="json")

        # Case 1: endpoints with ready backends compose HTTPRoute with backendRefs.
        req1 = fnv1.RunFunctionRequest(
            observed=fnv1.State(
                composite=fnv1.Resource(resource=resource.dict_to_struct(xr)),
            ),
        )
        req1.required_resources["inference-gateway"].items.append(
            fnv1.Resource(
                resource=resource.dict_to_struct(
                    {
                        "apiVersion": "modelplane.ai/v1alpha1",
                        "kind": "InferenceGateway",
                        "metadata": {"name": "default"},
                        "spec": {"backend": "EnvoyGateway"},
                        "status": {"address": "34.55.100.10"},
                    }
                )
            )
        )
        req1.required_resources["endpoints-0"].items.append(
            fnv1.Resource(
                resource=resource.dict_to_struct(
                    {
                        "apiVersion": "modelplane.ai/v1alpha1",
                        "kind": "ModelEndpoint",
                        "metadata": {"name": "ep-1", "namespace": "ml-team"},
                        "spec": {"url": "http://10.0.0.1/default/model/v1", "rewritePath": "/default/model/"},
                        "status": {"routing": {"backendName": "backend-1"}},
                    }
                )
            )
        )

        want1 = fnv1.RunFunctionResponse(
            meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
            desired=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"status": {"address": "http://34.55.100.10/ml-team/test-service"}}
                    ),
                ),
                resources={
                    "httproute": fnv1.Resource(
                        resource=resource.dict_to_struct(
                            {
                                "apiVersion": "gateway.networking.k8s.io/v1",
                                "kind": "HTTPRoute",
                                "metadata": {"namespace": "ml-team"},
                                "spec": {
                                    "parentRefs": [{"name": "modelplane", "namespace": "modelplane-system"}],
                                    "rules": [
                                        {
                                            "matches": [
                                                {"path": {"type": "PathPrefix", "value": "/ml-team/test-service/"}}
                                            ],
                                            "backendRefs": [
                                                {
                                                    "group": "gateway.envoyproxy.io",
                                                    "kind": "Backend",
                                                    "name": "backend-1",
                                                    "port": 80,
                                                    "weight": 1,
                                                    "filters": [
                                                        {
                                                            "type": "URLRewrite",
                                                            "urlRewrite": {
                                                                "path": {
                                                                    "type": "ReplacePrefixMatch",
                                                                    "replacePrefixMatch": "/default/model/",
                                                                },
                                                            },
                                                        }
                                                    ],
                                                },
                                            ],
                                        }
                                    ],
                                },
                            }
                        ),
                    ),
                },
            ),
            conditions=[
                fnv1.Condition(
                    type="EndpointsResolved",
                    status=fnv1.STATUS_CONDITION_TRUE,
                    reason="Resolved",
                    message="Matched 1 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want1.requirements.resources["inference-gateway"].CopyFrom(
            fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="InferenceGateway", match_name="default")
        )
        sel0 = fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="ModelEndpoint")
        sel0.match_labels.labels.update({"app": "model"})
        want1.requirements.resources["endpoints-0"].CopyFrom(sel0)

        # Case 2: no endpoints produces warning.
        req2 = fnv1.RunFunctionRequest(
            observed=fnv1.State(
                composite=fnv1.Resource(resource=resource.dict_to_struct(xr)),
            ),
        )
        req2.required_resources["endpoints-0"].SetInParent()

        want2 = fnv1.RunFunctionResponse(
            meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
            desired=fnv1.State(),
            conditions=[
                fnv1.Condition(
                    type="EndpointsResolved",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="NoEndpoints",
                    message="No ModelEndpoints matched the configured selectors",
                ),
            ],
            results=[
                fnv1.Result(
                    severity=fnv1.SEVERITY_WARNING,
                    message="No ModelEndpoints matched the configured selectors",
                ),
            ],
            context=structpb.Struct(),
        )
        want2.requirements.resources["inference-gateway"].CopyFrom(
            fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="InferenceGateway", match_name="default")
        )
        sel0_2 = fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="ModelEndpoint")
        sel0_2.match_labels.labels.update({"app": "model"})
        want2.requirements.resources["endpoints-0"].CopyFrom(sel0_2)

        # Case 3: endpoint without backend name — route has no backendRefs.
        req3 = fnv1.RunFunctionRequest(
            observed=fnv1.State(
                composite=fnv1.Resource(resource=resource.dict_to_struct(xr)),
            ),
        )
        req3.required_resources["inference-gateway"].items.append(
            fnv1.Resource(
                resource=resource.dict_to_struct(
                    {
                        "apiVersion": "modelplane.ai/v1alpha1",
                        "kind": "InferenceGateway",
                        "metadata": {"name": "default"},
                        "spec": {"backend": "EnvoyGateway"},
                        "status": {"address": "34.55.100.10"},
                    }
                )
            )
        )
        req3.required_resources["endpoints-0"].items.append(
            fnv1.Resource(
                resource=resource.dict_to_struct(
                    {
                        "apiVersion": "modelplane.ai/v1alpha1",
                        "kind": "ModelEndpoint",
                        "metadata": {"name": "ep-1", "namespace": "ml-team"},
                        "spec": {"url": "http://10.0.0.1/default/model/v1"},
                    }
                )
            )
        )

        want3 = fnv1.RunFunctionResponse(
            meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
            desired=fnv1.State(
                composite=fnv1.Resource(
                    resource=resource.dict_to_struct(
                        {"status": {"address": "http://34.55.100.10/ml-team/test-service"}}
                    ),
                ),
                resources={
                    "httproute": fnv1.Resource(
                        resource=resource.dict_to_struct(
                            {
                                "apiVersion": "gateway.networking.k8s.io/v1",
                                "kind": "HTTPRoute",
                                "metadata": {"namespace": "ml-team"},
                                "spec": {
                                    "parentRefs": [{"name": "modelplane", "namespace": "modelplane-system"}],
                                    "rules": [
                                        {
                                            "matches": [
                                                {"path": {"type": "PathPrefix", "value": "/ml-team/test-service/"}}
                                            ],
                                        }
                                    ],
                                },
                            }
                        ),
                    ),
                },
            ),
            conditions=[
                fnv1.Condition(
                    type="EndpointsResolved",
                    status=fnv1.STATUS_CONDITION_TRUE,
                    reason="Resolved",
                    message="Matched 1 endpoint(s); 1 waiting for Backend",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want3.requirements.resources["inference-gateway"].CopyFrom(
            fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="InferenceGateway", match_name="default")
        )
        sel0_3 = fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="ModelEndpoint")
        sel0_3.match_labels.labels.update({"app": "model"})
        want3.requirements.resources["endpoints-0"].CopyFrom(sel0_3)

        cases = [
            Case(name="endpoints with ready backends compose HTTPRoute with backendRefs", req=req1, want=want1),
            Case(name="no endpoints produces warning and EndpointsResolved=False", req=req2, want=want2),
            Case(name="endpoint without backend composes HTTPRoute without backendRefs", req=req3, want=want3),
        ]

        for case in cases:
            with self.subTest(case.name):
                got = await self.runner.RunFunction(case.req, None)
                self.assertEqual(
                    json_format.MessageToDict(case.want),
                    json_format.MessageToDict(got),
                    "-want, +got",
                )
