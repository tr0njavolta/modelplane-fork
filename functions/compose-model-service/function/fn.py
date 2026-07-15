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

"""Compose a Gateway-API HTTPRoute from a ModelService.

ModelService selects ModelEndpoints by label and load-balances across
them. This function fetches the InferenceGateway (for the public
address and parentRef) and the matching ModelEndpoints (for their
backend service names and rewrite paths), then composes a single
HTTPRoute on the control plane.

The match prefix is `/<service-ns>/<service-name>/`. Each endpoint's
rewritePath is attached as a per-backendRef URLRewrite filter so that
endpoints with different path conventions (e.g. composed replicas at
/v1/ alongside external providers at /openai/v1/) each get the correct
path rewrite. This is a Gateway API Extended feature (per-backendRef
filters) supported by Traefik Proxy.
"""

import math
import urllib.parse

import grpc
from crossplane.function import logging, request, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1
from models.ai.modelplane.inferencegateway import v1alpha1 as igwv1alpha1
from models.ai.modelplane.modelendpoint import v1alpha1 as mev1alpha1
from models.ai.modelplane.modelservice import v1alpha1
from models.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1

CONDITION_TYPE_ENDPOINTS_RESOLVED = "EndpointsResolved"
CONDITION_REASON_RESOLVED = "Resolved"
CONDITION_REASON_NO_ENDPOINTS = "NoEndpoints"
CONDITION_REASON_WAITING_FOR_GATEWAY = "WaitingForGateway"
CONDITION_REASON_ROUTE_CONFIGURED = "RouteConfigured"
CONDITION_REASON_CONFIGURING = "Configuring"
CONDITION_TYPE_ROUTING_READY = "RoutingReady"

# The control plane gateway name and namespace. ModelService composes
# HTTPRoutes that reference this gateway as a parentRef.
_GATEWAY_NAME = "modelplane"
_NAMESPACE_SYSTEM = "modelplane-system"

# Scheme for user-facing service URLs.
_GATEWAY_SCHEME = "http"

# Gateway API caps a backendRef's weight at 1,000,000 (an int32 limit in the
# HTTPRoute CRD). We keep composed weights at or below it so the API server
# accepts the HTTPRoute.
_MAX_WEIGHT = 1000000


def _name(meta: metav1.ObjectMeta | None) -> str:
    """The object's name, always set on resources read from the API server."""
    if meta is None or meta.name is None:
        raise ValueError("metadata.name is unexpectedly absent")
    return meta.name


def _namespace(meta: metav1.ObjectMeta | None) -> str:
    """The object's namespace, always set on namespaced resources read from the API server."""
    if meta is None or meta.namespace is None:
        raise ValueError("metadata.namespace is unexpectedly absent")
    return meta.namespace


def _port_from_url(url: str) -> int:
    """Parse the backend port from a ModelEndpoint URL.

    Defaults to 443 for https and 80 for http when not explicit, matching
    what compose-model-endpoint uses when creating the backend Service.
    """
    parsed = urllib.parse.urlparse(url)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _distribute_weights(
    groups: list[tuple[int, list[mev1alpha1.ModelEndpoint]]],
) -> list[tuple[mev1alpha1.ModelEndpoint, int]]:
    """Turn group weights into per-endpoint backendRef weights.

    Gateway API only supports per-backendRef weights, so each group's weight
    is spread across its endpoints. The result preserves the ratio between
    groups: a group weighted 80 next to one weighted 20 gets 80% of the total
    weight.

    Every group's weight is first scaled up by a common factor so it is at
    least its endpoint count, so no endpoint rounds down to weight 0 (which
    Gateway API treats as "no traffic") - e.g. weight 1 across 5 endpoints
    scales to 5, spread as [1, 1, 1, 1, 1]. The scaled weights are then reduced
    by their greatest common divisor to the smallest equivalent integers, and
    clamped to Gateway API's per-backendRef maximum so even extreme ratios
    yield an HTTPRoute the API server accepts.

    Groups with no ready endpoints are dropped; they can't receive traffic and
    so don't count towards the split.
    """
    # A group with no ready endpoints can't receive traffic, so drop it. Its
    # share is effectively redistributed across the groups that can serve.
    live = [(weight, eps) for weight, eps in groups if eps]
    if not live:
        return []

    # We give each endpoint (group weight * scale) // (endpoint count), then
    # hand out the remainder. Without scaling, a group whose weight is smaller
    # than its endpoint count would floor some endpoints to 0 (which Gateway
    # API reads as "no traffic"). To keep every endpoint at 1 or more, the
    # scaled group weight must be at least its endpoint count, so each group
    # needs scale >= ceil(endpoint count / group weight). Take the largest
    # requirement across all groups: multiplying every group by one common
    # factor leaves the ratios between groups unchanged.
    scale = 1
    for weight, eps in live:
        scale = max(scale, math.ceil(len(eps) / weight))

    # Spread each group's scaled weight across its endpoints as evenly as the
    # integers allow, handing the leftover one unit at a time to the first few.
    # For example weight 80 over 3 endpoints with scale 1 gives 27, 27, 26.
    weighted: list[tuple[mev1alpha1.ModelEndpoint, int]] = []
    for weight, eps in live:
        base, remainder = divmod(weight * scale, len(eps))
        for idx, ep in enumerate(eps):
            weighted.append((ep, base + (1 if idx < remainder else 0)))

    # Scaling can inflate the weights well past what's needed to express the
    # ratio (e.g. all groups landing on even numbers), so divide them back down
    # by their greatest common divisor to the smallest equivalent integers.
    weights = [w for _, w in weighted]
    divisor = math.gcd(*weights)
    highest = max(weights) // divisor
    if highest <= _MAX_WEIGHT:
        return [(ep, w // divisor) for ep, w in weighted]

    # Even reduced, an extreme ratio (say 1,000,000 to 1) can push a weight past
    # Gateway API's per-backendRef limit, which would make the API server
    # reject the HTTPRoute. Rescale everything so the largest weight lands on
    # the limit, keeping every endpoint at 1 or more. This trades a little ratio
    # precision for a valid route in a case no realistic config reaches.
    return [(ep, max(1, round(w / divisor / highest * _MAX_WEIGHT))) for ep, w in weighted]


def _has_parent_condition(req: fnv1.RunFunctionRequest, name: str, cond: str) -> bool:
    """Check a Gateway API condition nested under status.parents[].conditions.

    Gateway API resources (HTTPRoute, etc.) nest route status under
    status.parents[].conditions instead of top-level status.conditions.
    """
    observed = req.observed.resources.get(name)
    if observed is None:
        return False
    d = resource.struct_to_dict(observed.resource)
    for p in d.get("status", {}).get("parents", []):
        for c in p.get("conditions", []):
            if c.get("type") == cond and c.get("status") == "True":
                return True
    return False


class FunctionRunner(grpcv1.FunctionRunnerServiceServicer):
    """A FunctionRunner handles gRPC RunFunctionRequests."""

    def __init__(self) -> None:
        """Create a new FunctionRunner."""
        self.log = logging.get_logger()

    async def RunFunction(
        self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext | None
    ) -> fnv1.RunFunctionResponse:  # ty: ignore[invalid-method-override]  # the generated grpc servicer base is untyped
        """Run the function."""
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running function")

        rsp = response.to(req)
        c = Composer(req, rsp)
        c.compose()
        return rsp


class Composer:
    def __init__(self, req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse) -> None:
        self.req = req
        self.rsp = rsp
        self.xr = v1alpha1.ModelService(**resource.struct_to_dict(req.observed.composite.resource))
        self.gateway = None
        self.endpoints: list[mev1alpha1.ModelEndpoint] = []
        # Matched endpoints grouped by spec.endpoints[] entry, paired with
        # that entry's weight. Traffic is split across groups in proportion
        # to their weights; compose_httproute spreads each group's weight
        # across its endpoints.
        self.groups: list[tuple[int, list[mev1alpha1.ModelEndpoint]]] = []

    def compose(self) -> None:
        if not self.resolve_inputs():
            return
        self.compose_httproute()
        self.write_status()
        self.derive_conditions()

    def resolve_inputs(self) -> bool:
        """Fetch the InferenceGateway and matching ModelEndpoints."""
        response.require_resources(
            self.rsp,
            name="inference-gateway",
            api_version="modelplane.ai/v1alpha1",
            kind="InferenceGateway",
            match_name="default",
        )

        # One required-resources request per spec.endpoints[i] entry.
        for i, entry in enumerate(self.xr.spec.endpoints):
            response.require_resources(
                self.rsp,
                name=f"endpoints-{i}",
                api_version="modelplane.ai/v1alpha1",
                kind="ModelEndpoint",
                match_labels=entry.selector.matchLabels,
            )

        gw_dict = request.get_required_resource(self.req, "inference-gateway")
        self.gateway = igwv1alpha1.InferenceGateway.model_validate(gw_dict) if gw_dict else None

        # Gather matched endpoints per selector entry, preserving the group
        # structure so each group's weight can be applied. An endpoint matched
        # by more than one entry is assigned to the first entry that matches
        # it, so its weight is unambiguous.
        seen_names: set[str] = set()
        for i, entry in enumerate(self.xr.spec.endpoints):
            weight = entry.weight if entry.weight is not None else 1
            group: list[mev1alpha1.ModelEndpoint] = []
            for d in request.get_required_resources(self.req, f"endpoints-{i}") or []:
                ep = mev1alpha1.ModelEndpoint.model_validate(d)
                key = f"{_namespace(ep.metadata)}/{_name(ep.metadata)}"
                if key in seen_names:
                    continue
                seen_names.add(key)
                group.append(ep)
                self.endpoints.append(ep)
            self.groups.append((weight, group))

        if not self.endpoints:
            response.set_conditions(
                self.rsp,
                resource.Condition(
                    typ=CONDITION_TYPE_ENDPOINTS_RESOLVED,
                    status="False",
                    reason=CONDITION_REASON_NO_ENDPOINTS,
                    message="No ModelEndpoints matched the configured selectors",
                ),
            )
            response.warning(self.rsp, "No ModelEndpoints matched the configured selectors")
            return False

        ready = sum(1 for ep in self.endpoints if ep.status and ep.status.routing and ep.status.routing.backendName)
        waiting = len(self.endpoints) - ready
        msg = f"Matched {len(self.endpoints)} endpoint(s)"
        if waiting > 0:
            msg += f"; {waiting} waiting for Backend"

        response.set_conditions(
            self.rsp,
            resource.Condition(
                typ=CONDITION_TYPE_ENDPOINTS_RESOLVED,
                status="True",
                reason=CONDITION_REASON_RESOLVED,
                message=msg,
            ),
        )
        return True

    def _backend_ref(self, ep: mev1alpha1.ModelEndpoint, weight: int) -> dict:
        """Build an HTTPRoute backendRef for a ready endpoint."""
        # Callers pass only ready endpoints; this guard also narrows the type.
        if not ep.status or not ep.status.routing or not ep.status.routing.backendName:
            raise ValueError("endpoint has no backend name")
        # Derive the backend Service port from the endpoint's URL.
        # compose-model-endpoint creates a Service with this port.
        ref: dict = {
            "name": ep.status.routing.backendName,
            "port": _port_from_url(ep.spec.url),
            "weight": weight,
        }
        if ep.spec.rewritePath:
            ref["filters"] = [
                {
                    "type": "URLRewrite",
                    "urlRewrite": {
                        "path": {
                            "type": "ReplacePrefixMatch",
                            "replacePrefixMatch": ep.spec.rewritePath,
                        },
                    },
                }
            ]
        return ref

    def compose_httproute(self) -> None:
        """Compose an HTTPRoute that splits traffic across matched endpoints.

        A single rule matches the service prefix and fans out to all ready
        endpoints via weighted backendRefs. Traffic is split across selector
        entries in proportion to their weights; each entry's weight is spread
        evenly across the endpoints it matched. Each backendRef carries its
        own URLRewrite filter derived from the endpoint's rewritePath, so
        endpoints with different path conventions are rewritten correctly
        per-backend. This is a Gateway API Extended feature supported by
        Traefik Proxy.
        """
        match_prefix = f"/{_namespace(self.xr.metadata)}/{_name(self.xr.metadata)}/"
        match = {"path": {"type": "PathPrefix", "value": match_prefix}}

        # Only ready endpoints (those with a Backend) can receive traffic.
        ready_groups = [
            (weight, [ep for ep in eps if ep.status and ep.status.routing and ep.status.routing.backendName])
            for weight, eps in self.groups
        ]

        backend_refs = [self._backend_ref(ep, w) for ep, w in _distribute_weights(ready_groups)]

        rule: dict = {"matches": [match]}
        if backend_refs:
            rule["backendRefs"] = backend_refs

        resource.update(
            self.rsp.desired.resources["httproute"],
            {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "HTTPRoute",
                "metadata": {"namespace": _namespace(self.xr.metadata)},
                "spec": {
                    "parentRefs": [{"name": _GATEWAY_NAME, "namespace": _NAMESPACE_SYSTEM}],
                    "rules": [rule],
                },
            },
        )

    def write_status(self) -> None:
        status = v1alpha1.Status()
        gateway_ip = self.gateway.status.address if self.gateway and self.gateway.status else None
        if gateway_ip:
            status.address = (
                f"{_GATEWAY_SCHEME}://{gateway_ip}/{_namespace(self.xr.metadata)}/{_name(self.xr.metadata)}"
            )
        resource.update_status(self.rsp.desired.composite, status)

    def derive_conditions(self) -> None:
        """RoutingReady: HTTPRoute is composed and Accepted with backends."""
        if "httproute" not in self.rsp.desired.resources:
            response.set_conditions(
                self.rsp,
                resource.Condition(
                    typ=CONDITION_TYPE_ROUTING_READY,
                    status="False",
                    reason=CONDITION_REASON_WAITING_FOR_GATEWAY,
                ),
            )
            return

        backend_refs_observed = any(
            ep.status and ep.status.routing and ep.status.routing.backendName for ep in self.endpoints
        )
        route_ready = _has_parent_condition(self.req, "httproute", "Accepted") and backend_refs_observed

        if route_ready:
            self.rsp.desired.resources["httproute"].ready = fnv1.READY_TRUE

        response.set_conditions(
            self.rsp,
            resource.Condition(
                typ=CONDITION_TYPE_ROUTING_READY,
                status="True" if route_ready else "False",
                reason=CONDITION_REASON_ROUTE_CONFIGURED if route_ready else CONDITION_REASON_CONFIGURING,
            ),
        )
