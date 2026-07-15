# Copyright 2026 The Modelplane Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

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


def _gateway() -> fnv1.Resource:
    """The InferenceGateway every case resolves for its address and parentRef."""
    return fnv1.Resource(
        resource=resource.dict_to_struct(
            {
                "apiVersion": "modelplane.ai/v1alpha1",
                "kind": "InferenceGateway",
                "metadata": {"name": "default"},
                "spec": {"backend": "Traefik"},
                "status": {"address": "34.55.100.10"},
            }
        )
    )


def _endpoint(
    name: str, *, url: str = "http://10.0.0.1/v1", rewrite_path: str | None = None, backend: str | None = None
) -> fnv1.Resource:
    """A matched ModelEndpoint. Omit backend for one that isn't ready yet."""
    ep: dict = {
        "apiVersion": "modelplane.ai/v1alpha1",
        "kind": "ModelEndpoint",
        "metadata": {"name": name, "namespace": "ml-team"},
        "spec": {"url": url},
    }
    if rewrite_path is not None:
        ep["spec"]["rewritePath"] = rewrite_path
    if backend is not None:
        ep["status"] = {"routing": {"backendName": backend}}
    return fnv1.Resource(resource=resource.dict_to_struct(ep))


def _gateway_selector() -> fnv1.ResourceSelector:
    return fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="InferenceGateway", match_name="default")


def _endpoint_selector(labels: dict[str, str]) -> fnv1.ResourceSelector:
    sel = fnv1.ResourceSelector(api_version="modelplane.ai/v1alpha1", kind="ModelEndpoint")
    sel.match_labels.labels.update(labels)
    return sel


class TestFunctionRunner(unittest.IsolatedAsyncioTestCase):
    """Tests for FunctionRunner.RunFunction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = fn.FunctionRunner()

    async def test_compose(self) -> None:  # noqa: PLR0915
        """The function composes an HTTPRoute from a ModelService."""

        xr = v1alpha1.ModelService(
            metadata=metav1.ObjectMeta(name="test-service", namespace="ml-team"),
            spec=v1alpha1.Spec(
                endpoints=[v1alpha1.Endpoint(selector=v1alpha1.Selector(matchLabels={"app": "model"}))],
            ),
        ).model_dump(exclude_none=True, mode="json")

        # Case 1: endpoints with ready backends compose HTTPRoute with backendRefs.
        req1 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr))),
        )
        req1.required_resources["inference-gateway"].items.append(_gateway())
        req1.required_resources["endpoints-0"].items.append(_endpoint("ep-1", rewrite_path="/v1/", backend="svc-1"))

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
                                                    "name": "svc-1",
                                                    "port": 80,
                                                    "weight": 1,
                                                    "filters": [
                                                        {
                                                            "type": "URLRewrite",
                                                            "urlRewrite": {
                                                                "path": {
                                                                    "type": "ReplacePrefixMatch",
                                                                    "replacePrefixMatch": "/v1/",
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
        want1.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want1.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "model"}))

        # Case 2: no endpoints produces warning.
        req2 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr))),
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
        want2.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want2.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "model"}))

        # Case 3: endpoint without backend name — route has no backendRefs.
        req3 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr))),
        )
        req3.required_resources["inference-gateway"].items.append(_gateway())
        req3.required_resources["endpoints-0"].items.append(_endpoint("ep-1"))

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
        want3.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want3.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "model"}))

        # Case 4: two endpoints with the same rewritePath produce one rule with two backendRefs.
        req4 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr))),
        )
        req4.required_resources["inference-gateway"].items.append(_gateway())
        req4.required_resources["endpoints-0"].items.append(_endpoint("ep-1", rewrite_path="/v1/", backend="svc-ep-1"))
        req4.required_resources["endpoints-0"].items.append(_endpoint("ep-2", rewrite_path="/v1/", backend="svc-ep-2"))

        want4 = fnv1.RunFunctionResponse(
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
                                                    "name": "svc-ep-1",
                                                    "port": 80,
                                                    "weight": 1,
                                                    "filters": [
                                                        {
                                                            "type": "URLRewrite",
                                                            "urlRewrite": {
                                                                "path": {
                                                                    "type": "ReplacePrefixMatch",
                                                                    "replacePrefixMatch": "/v1/",
                                                                },
                                                            },
                                                        }
                                                    ],
                                                },
                                                {
                                                    "name": "svc-ep-2",
                                                    "port": 80,
                                                    "weight": 1,
                                                    "filters": [
                                                        {
                                                            "type": "URLRewrite",
                                                            "urlRewrite": {
                                                                "path": {
                                                                    "type": "ReplacePrefixMatch",
                                                                    "replacePrefixMatch": "/v1/",
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
                    message="Matched 2 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want4.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want4.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "model"}))

        # Case 5: two endpoints with different rewritePaths get per-backendRef filters.
        req5 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr))),
        )
        req5.required_resources["inference-gateway"].items.append(_gateway())
        req5.required_resources["endpoints-0"].items.append(_endpoint("ep-a", rewrite_path="/v1/", backend="svc-a"))
        req5.required_resources["endpoints-0"].items.append(
            _endpoint("ep-b", url="https://api.groq.com/openai/v1", rewrite_path="/openai/v1/", backend="svc-groq")
        )

        want5 = fnv1.RunFunctionResponse(
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
                                                    "name": "svc-a",
                                                    "port": 80,
                                                    "weight": 1,
                                                    "filters": [
                                                        {
                                                            "type": "URLRewrite",
                                                            "urlRewrite": {
                                                                "path": {
                                                                    "type": "ReplacePrefixMatch",
                                                                    "replacePrefixMatch": "/v1/",
                                                                },
                                                            },
                                                        }
                                                    ],
                                                },
                                                {
                                                    "name": "svc-groq",
                                                    "port": 443,
                                                    "weight": 1,
                                                    "filters": [
                                                        {
                                                            "type": "URLRewrite",
                                                            "urlRewrite": {
                                                                "path": {
                                                                    "type": "ReplacePrefixMatch",
                                                                    "replacePrefixMatch": "/openai/v1/",
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
                    message="Matched 2 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want5.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want5.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "model"}))

        # Case 6: two weighted selector groups (80/20) split traffic proportionally.
        # The weight-80 group is spread across its three endpoints as 27/27/26;
        # the weight-20 group goes to its single endpoint.
        xr6 = v1alpha1.ModelService(
            metadata=metav1.ObjectMeta(name="test-service", namespace="ml-team"),
            spec=v1alpha1.Spec(
                endpoints=[
                    v1alpha1.Endpoint(weight=80, selector=v1alpha1.Selector(matchLabels={"app": "prod"})),
                    v1alpha1.Endpoint(weight=20, selector=v1alpha1.Selector(matchLabels={"app": "canary"})),
                ],
            ),
        ).model_dump(exclude_none=True, mode="json")

        req6 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr6))),
        )
        req6.required_resources["inference-gateway"].items.append(_gateway())
        req6.required_resources["endpoints-0"].items.append(_endpoint("ep-1", backend="svc-ep-1"))
        req6.required_resources["endpoints-0"].items.append(_endpoint("ep-2", backend="svc-ep-2"))
        req6.required_resources["endpoints-0"].items.append(_endpoint("ep-3", backend="svc-ep-3"))
        req6.required_resources["endpoints-1"].items.append(_endpoint("ep-4", backend="svc-ep-4"))

        want6 = fnv1.RunFunctionResponse(
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
                                                {"name": "svc-ep-1", "port": 80, "weight": 27},
                                                {"name": "svc-ep-2", "port": 80, "weight": 27},
                                                {"name": "svc-ep-3", "port": 80, "weight": 26},
                                                {"name": "svc-ep-4", "port": 80, "weight": 20},
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
                    message="Matched 4 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want6.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want6.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "prod"}))
        want6.requirements.resources["endpoints-1"].CopyFrom(_endpoint_selector({"app": "canary"}))

        # Case 7: a default-weight (1) group of two endpoints beside a weight-3
        # group. Scaling up keeps both first-group endpoints at weight 1 rather
        # than rounding one to 0, preserving the 1:3 split.
        xr7 = v1alpha1.ModelService(
            metadata=metav1.ObjectMeta(name="test-service", namespace="ml-team"),
            spec=v1alpha1.Spec(
                endpoints=[
                    v1alpha1.Endpoint(selector=v1alpha1.Selector(matchLabels={"app": "prod"})),
                    v1alpha1.Endpoint(weight=3, selector=v1alpha1.Selector(matchLabels={"app": "canary"})),
                ],
            ),
        ).model_dump(exclude_none=True, mode="json")

        req7 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr7))),
        )
        req7.required_resources["inference-gateway"].items.append(_gateway())
        req7.required_resources["endpoints-0"].items.append(_endpoint("ep-1", backend="svc-ep-1"))
        req7.required_resources["endpoints-0"].items.append(_endpoint("ep-2", backend="svc-ep-2"))
        req7.required_resources["endpoints-1"].items.append(_endpoint("ep-3", backend="svc-ep-3"))

        want7 = fnv1.RunFunctionResponse(
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
                                                {"name": "svc-ep-1", "port": 80, "weight": 1},
                                                {"name": "svc-ep-2", "port": 80, "weight": 1},
                                                {"name": "svc-ep-3", "port": 80, "weight": 6},
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
                    message="Matched 3 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want7.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want7.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "prod"}))
        want7.requirements.resources["endpoints-1"].CopyFrom(_endpoint_selector({"app": "canary"}))

        # Case 8: equal weights on single-endpoint groups reduce from [2, 2] to [1, 1].
        xr8 = v1alpha1.ModelService(
            metadata=metav1.ObjectMeta(name="test-service", namespace="ml-team"),
            spec=v1alpha1.Spec(
                endpoints=[
                    v1alpha1.Endpoint(weight=2, selector=v1alpha1.Selector(matchLabels={"app": "prod"})),
                    v1alpha1.Endpoint(weight=2, selector=v1alpha1.Selector(matchLabels={"app": "canary"})),
                ],
            ),
        ).model_dump(exclude_none=True, mode="json")

        req8 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr8))),
        )
        req8.required_resources["inference-gateway"].items.append(_gateway())
        req8.required_resources["endpoints-0"].items.append(_endpoint("ep-1", backend="svc-ep-1"))
        req8.required_resources["endpoints-1"].items.append(_endpoint("ep-2", backend="svc-ep-2"))

        want8 = fnv1.RunFunctionResponse(
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
                                                {"name": "svc-ep-1", "port": 80, "weight": 1},
                                                {"name": "svc-ep-2", "port": 80, "weight": 1},
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
                    message="Matched 2 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want8.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want8.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "prod"}))
        want8.requirements.resources["endpoints-1"].CopyFrom(_endpoint_selector({"app": "canary"}))

        # Case 9: a weight so large it would exceed Gateway API's per-backendRef
        # maximum after scaling is clamped, keeping every endpoint >= 1.
        xr9 = v1alpha1.ModelService(
            metadata=metav1.ObjectMeta(name="test-service", namespace="ml-team"),
            spec=v1alpha1.Spec(
                endpoints=[
                    v1alpha1.Endpoint(weight=1000000, selector=v1alpha1.Selector(matchLabels={"app": "prod"})),
                    v1alpha1.Endpoint(weight=1, selector=v1alpha1.Selector(matchLabels={"app": "canary"})),
                ],
            ),
        ).model_dump(exclude_none=True, mode="json")

        req9 = fnv1.RunFunctionRequest(
            observed=fnv1.State(composite=fnv1.Resource(resource=resource.dict_to_struct(xr9))),
        )
        req9.required_resources["inference-gateway"].items.append(_gateway())
        req9.required_resources["endpoints-0"].items.append(_endpoint("ep-1", backend="svc-ep-1"))
        req9.required_resources["endpoints-1"].items.append(_endpoint("ep-2", backend="svc-ep-2"))
        req9.required_resources["endpoints-1"].items.append(_endpoint("ep-3", backend="svc-ep-3"))

        want9 = fnv1.RunFunctionResponse(
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
                                                {"name": "svc-ep-1", "port": 80, "weight": 1000000},
                                                {"name": "svc-ep-2", "port": 80, "weight": 1},
                                                {"name": "svc-ep-3", "port": 80, "weight": 1},
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
                    message="Matched 3 endpoint(s)",
                ),
                fnv1.Condition(
                    type="RoutingReady",
                    status=fnv1.STATUS_CONDITION_FALSE,
                    reason="Configuring",
                ),
            ],
            context=structpb.Struct(),
        )
        want9.requirements.resources["inference-gateway"].CopyFrom(_gateway_selector())
        want9.requirements.resources["endpoints-0"].CopyFrom(_endpoint_selector({"app": "prod"}))
        want9.requirements.resources["endpoints-1"].CopyFrom(_endpoint_selector({"app": "canary"}))

        cases = [
            Case(name="endpoints with ready backends compose HTTPRoute with backendRefs", req=req1, want=want1),
            Case(name="no endpoints produces warning and EndpointsResolved=False", req=req2, want=want2),
            Case(name="endpoint without backend composes HTTPRoute without backendRefs", req=req3, want=want3),
            Case(name="same rewritePath produces one rule with two backendRefs", req=req4, want=want4),
            Case(name="different rewritePaths produce per-backendRef URLRewrite filters", req=req5, want=want5),
            Case(name="weighted selector groups split traffic proportionally", req=req6, want=want6),
            Case(name="group weights scale up so no endpoint rounds to zero", req=req7, want=want7),
            Case(name="equal group weights reduce to smallest equivalent weights", req=req8, want=want8),
            Case(name="weights clamp to the Gateway API maximum", req=req9, want=want9),
        ]

        for case in cases:
            with self.subTest(case.name):
                got = await self.runner.RunFunction(case.req, None)
                self.assertEqual(
                    json_format.MessageToDict(case.want),
                    json_format.MessageToDict(got),
                    "-want, +got",
                )
