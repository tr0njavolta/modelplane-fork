"""Fan out a ModelDeployment to ModelReplicas and configure routing.

This function discovers InferenceClusters, matches model requirements
against available capacity, creates a ModelReplica per matched cluster,
and composes Envoy Gateway Backend + HTTPRoute resources on the control plane
for unified endpoint routing.
"""

from crossplane.function import request, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1

from . import scheduling
from .lib import conditions, defaults, metadata, naming
from .lib import resource as libresource
from .model.ai.modelplane.clustermodel import v1alpha1 as cmv1alpha1
from .model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from .model.ai.modelplane.inferencegateway import v1alpha1 as igwv1alpha1
from .model.ai.modelplane.model import v1alpha1 as mv1alpha1
from .model.ai.modelplane.modeldeployment import v1alpha1
from .model.ai.modelplane.modelreplica import v1alpha1 as mrv1alpha1
from .model.io.k8s.apimachinery.pkg.apis.meta import v1 as metav1

# Condition types and reasons for the ModelDeployment XR.
CONDITION_TYPE_REPLICAS_SCHEDULED = "ReplicasScheduled"
CONDITION_TYPE_REPLICAS_READY = "ReplicasReady"

CONDITION_REASON_NO_CLUSTERS = "NoClusters"
CONDITION_REASON_MODEL_NOT_FOUND = "ModelNotFound"
CONDITION_REASON_INSUFFICIENT_CAPACITY = "InsufficientCapacity"
CONDITION_REASON_REPLICAS_CREATED = "ReplicasCreated"
CONDITION_REASON_SCHEDULING = "Scheduling"
CONDITION_REASON_NO_REPLICAS_SCHEDULED = "NoReplicasScheduled"
CONDITION_REASON_ALL_REPLICAS_READY = "AllReplicasReady"
CONDITION_REASON_MODEL_STARTING = "ModelStarting"
CONDITION_REASON_ROUTE_CONFIGURED = "RouteConfigured"
CONDITION_REASON_CONFIGURING = "Configuring"
CONDITION_REASON_WAITING_FOR_REPLICAS = "WaitingForReplicas"


class Composer:
    def __init__(self, req, rsp):
        self.req = req
        self.rsp = rsp
        self.xr = v1alpha1.ModelDeployment(**resource.struct_to_dict(req.observed.composite.resource))

        # Required resources — set by _resolve_inputs.
        self.model = None
        self.clusters = []
        self.gateway = None
        self.all_replicas = []

    def compose(self):
        if not self.resolve_inputs():
            return
        matched = self.schedule()
        self.compose_replicas(matched)
        self.compose_httproute(matched)
        self.write_status(matched)
        self.derive_conditions(matched)

    def resolve_inputs(self):
        """Declare and fetch required resources. Returns False if critical
        inputs are missing."""
        model_kind = self.xr.spec.modelRef.kind
        model_name = self.xr.spec.modelRef.name

        # InferenceClusters are matched by the modelplane.ai/cluster=true
        # label — a workaround for the empty match_labels protobuf bug.
        cluster_match_labels: dict[str, str] = {
            metadata.LABEL_KEY_CLUSTER: metadata.LABEL_VALUE_CLUSTER,
        }
        if self.xr.spec.clusterSelector and self.xr.spec.clusterSelector.matchLabels:
            cluster_match_labels.update(self.xr.spec.clusterSelector.matchLabels)

        response.require_resources(
            self.rsp,
            name="clusters",
            api_version="modelplane.ai/v1alpha1",
            kind="InferenceCluster",
            match_labels=cluster_match_labels,
        )
        response.require_resources(
            self.rsp,
            name="model",
            api_version="modelplane.ai/v1alpha1",
            kind=model_kind,
            match_name=model_name,
        )
        response.require_resources(
            self.rsp,
            name="inference-gateway",
            api_version="modelplane.ai/v1alpha1",
            kind="InferenceGateway",
            match_name="default",
        )
        response.require_resources(
            self.rsp,
            name="all-replicas",
            api_version="modelplane.ai/v1alpha1",
            kind="ModelReplica",
            match_labels={metadata.LABEL_KEY_REPLICA: metadata.LABEL_VALUE_REPLICA},
        )

        cluster_dicts = request.get_required_resources(self.req, "clusters")
        model_dict = request.get_required_resource(self.req, "model")
        gw_dict = request.get_required_resource(self.req, "inference-gateway")
        replica_dicts = request.get_required_resources(self.req, "all-replicas")

        if not cluster_dicts:
            conditions.set_condition(
                self.rsp,
                CONDITION_TYPE_REPLICAS_SCHEDULED,
                False,
                CONDITION_REASON_NO_CLUSTERS,
            )
            response.warning(self.rsp, "No InferenceClusters found")
            return False

        if model_dict is None:
            conditions.set_condition(
                self.rsp,
                CONDITION_TYPE_REPLICAS_SCHEDULED,
                False,
                CONDITION_REASON_MODEL_NOT_FOUND,
            )
            response.warning(self.rsp, f"Model {model_name} not found")
            return False

        self.clusters = [
            defaults.inference_cluster(icv1alpha1.InferenceCluster.model_validate(c)) for c in cluster_dicts
        ]
        if model_kind == "Model":
            self.model = defaults.cluster_model(mv1alpha1.ModelModel.model_validate(model_dict))
        else:
            self.model = defaults.cluster_model(cmv1alpha1.ClusterModel.model_validate(model_dict))
        self.gateway = (
            defaults.inference_gateway(igwv1alpha1.InferenceGateway.model_validate(gw_dict)) if gw_dict else None
        )
        self.all_replicas = [defaults.model_replica(mrv1alpha1.ModelReplica.model_validate(r)) for r in replica_dicts]

        return True

    def schedule(self):
        """Match model requirements against available clusters. Returns the
        list of matched candidates."""
        matched = scheduling.schedule(self.xr, self.model, self.clusters, self.all_replicas)

        # Transition: emit which clusters were matched (first time only).
        if not matched:
            return matched
        prev_replica_count = sum(1 for c in matched if f"replica-{c.name}" in self.req.observed.resources)
        if prev_replica_count == 0:
            matched_names = [c.name for c in matched]
            response.normal(self.rsp, f"Matched {len(matched)} clusters: {', '.join(matched_names)}")

        return matched

    def compose_replicas(self, matched):
        """Compose a ModelReplica per matched cluster."""
        for cluster_info in matched:
            replica_key = f"replica-{cluster_info.name}"

            resource.update(
                self.rsp.desired.resources[replica_key],
                mrv1alpha1.ModelReplica(
                    metadata=metav1.ObjectMeta(
                        name=naming.replica_name(self.xr.metadata.name, cluster_info.name),
                        namespace=self.xr.metadata.namespace,
                        labels={
                            metadata.LABEL_KEY_REPLICA: metadata.LABEL_VALUE_REPLICA,
                            metadata.LABEL_KEY_DEPLOYMENT: self.xr.metadata.name,
                        },
                    ),
                    spec=mrv1alpha1.Spec(
                        modelRef=mrv1alpha1.ModelRef(
                            kind=self.xr.spec.modelRef.kind,
                            name=self.xr.spec.modelRef.name,
                        ),
                        inferenceClusterRef=mrv1alpha1.InferenceClusterRef(
                            name=cluster_info.name,
                        ),
                        # Convert via model_dump because the MD and MR
                        # Scaling types are different Pydantic classes
                        # (generated from different XRDs).
                        scaling=mrv1alpha1.Scaling.model_validate(self.xr.spec.scaling.model_dump(exclude_none=True)),
                    ),
                ),
            )

    def compose_httproute(self, matched):
        """Compose an HTTPRoute that load-balances across all replicas'
        backends. Backend resources are composed by ModelReplica — we read
        their names from observed ModelReplica status."""
        if not matched:
            return

        backend_refs = self.backend_refs(matched)

        # Rewrite /{ns}/{deployment}/ to /{remote-ns}/{model-name}/.
        # The LLMIS name is the ClusterModel name on all remote clusters,
        # so the rewrite is the same for every backend.
        rewrite_prefix = f"/{metadata.NAMESPACE_REMOTE}/{naming.to_dns_label(self.xr.spec.modelRef.name)}/"

        # Gateway parentRef — defaults for Envoy Gateway, could be read
        # from InferenceGateway status in future.
        httproute_spec: dict = {
            "parentRefs": [{"name": metadata.GATEWAY_NAME, "namespace": metadata.NAMESPACE_SYSTEM}],
            "rules": [
                {
                    "matches": [
                        {
                            "path": {
                                "type": "PathPrefix",
                                "value": f"/{self.xr.metadata.namespace}/{self.xr.metadata.name}/",
                            },
                        }
                    ],
                    "filters": [
                        {
                            "type": "URLRewrite",
                            "urlRewrite": {
                                "path": {
                                    "type": "ReplacePrefixMatch",
                                    "replacePrefixMatch": rewrite_prefix,
                                },
                            },
                        }
                    ],
                }
            ],
        }
        if backend_refs:
            httproute_spec["rules"][0]["backendRefs"] = backend_refs

        resource.update(
            self.rsp.desired.resources["httproute"],
            {
                "apiVersion": "gateway.networking.k8s.io/v1",
                "kind": "HTTPRoute",
                "metadata": {"namespace": self.xr.metadata.namespace},
                "spec": httproute_spec,
            },
        )

    def write_status(self, matched):
        """Write deployment status: model name, replica counts, endpoint."""
        gateway_ip = self.gateway.status.address if self.gateway else None

        replicas_ready = sum(1 for c in matched if conditions.has_condition(self.req, f"replica-{c.name}", "Ready"))

        status = v1alpha1.Status(
            model=v1alpha1.Model(name=self.model.spec.model.name),
            replicas=v1alpha1.Replicas(total=len(matched), ready=replicas_ready),
        )
        if gateway_ip:
            status.endpoint = v1alpha1.Endpoint(
                url=f"http://{gateway_ip}/{self.xr.metadata.namespace}/{self.xr.metadata.name}/v1/chat/completions",
            )
        libresource.update_status(self.rsp.desired.composite, status)

    def derive_conditions(self, matched):
        """Derive ReplicasScheduled, ReplicasReady, and RoutingReady
        conditions. Also marks per-replica and httproute readiness."""
        self.derive_replicas_scheduled(matched)
        self.derive_replicas_ready(matched)
        self.derive_routing_ready(matched)

        # When no replicas are scheduled, explicitly mark not ready. Without
        # this, an XR with no composed resources would be trivially ready.
        if not matched:
            self.rsp.desired.composite.ready = fnv1.READY_FALSE

    def derive_replicas_scheduled(self, matched):
        """ReplicasScheduled: clusters matched and replicas created."""
        any_observed = any(f"replica-{c.name}" in self.req.observed.resources for c in matched)
        scheduled = len(matched) > 0 and any_observed

        if not matched:
            reason = CONDITION_REASON_INSUFFICIENT_CAPACITY
            msg = f"0 of {int(self.xr.spec.clusters)} clusters matched (checked {len(self.clusters)})"
        elif scheduled:
            reason = CONDITION_REASON_REPLICAS_CREATED
            msg = f"Matched {len(matched)} clusters"
        else:
            reason = CONDITION_REASON_SCHEDULING
            msg = ""

        conditions.set_condition(self.rsp, CONDITION_TYPE_REPLICAS_SCHEDULED, scheduled, reason, msg)

    def derive_replicas_ready(self, matched):
        """ReplicasReady: all replicas are serving traffic."""
        replicas_ready = 0
        for c in matched:
            replica_key = f"replica-{c.name}"
            if conditions.has_condition(self.req, replica_key, "Ready"):
                self.rsp.desired.resources[replica_key].ready = fnv1.READY_TRUE
                replicas_ready += 1

        all_ready = len(matched) > 0 and replicas_ready == len(matched)

        if not matched:
            reason = CONDITION_REASON_NO_REPLICAS_SCHEDULED
            msg = ""
        elif all_ready:
            reason = CONDITION_REASON_ALL_REPLICAS_READY
            msg = f"{replicas_ready} of {len(matched)} ready"
        else:
            reason = CONDITION_REASON_MODEL_STARTING
            msg = f"{replicas_ready} of {len(matched)} ready"

        conditions.set_condition(self.rsp, CONDITION_TYPE_REPLICAS_READY, all_ready, reason, msg)

    def derive_routing_ready(self, matched):
        """RoutingReady: the control plane HTTPRoute is configured and has
        backends."""
        if "httproute" not in self.rsp.desired.resources:
            reason = CONDITION_REASON_NO_REPLICAS_SCHEDULED if not matched else CONDITION_REASON_WAITING_FOR_REPLICAS
            conditions.set_condition(self.rsp, conditions.CONDITION_TYPE_ROUTING_READY, False, reason)
            return

        # The HTTPRoute is only truly ready when it has backendRefs (not just
        # Accepted). An empty-backendRefs HTTPRoute returns 404.
        backend_refs = self.backend_refs(matched)
        route_ready = conditions.has_parent_condition(self.req, "httproute", "Accepted") and bool(backend_refs)

        if route_ready:
            self.rsp.desired.resources["httproute"].ready = fnv1.READY_TRUE

        if not matched:
            reason = CONDITION_REASON_NO_REPLICAS_SCHEDULED
        elif route_ready:
            reason = CONDITION_REASON_ROUTE_CONFIGURED
        else:
            reason = CONDITION_REASON_CONFIGURING

        conditions.set_condition(self.rsp, conditions.CONDITION_TYPE_ROUTING_READY, route_ready, reason)

    def backend_refs(self, matched):
        """Read backend names from observed ModelReplica status."""
        refs = []
        for cluster_info in matched:
            observed = self.req.observed.resources.get(f"replica-{cluster_info.name}")
            if not observed:
                continue
            r = mrv1alpha1.ModelReplica.model_validate(resource.struct_to_dict(observed.resource))
            if not r.status or not r.status.routing:
                continue
            if not r.status.routing.backendName:
                continue
            refs.append(
                {
                    "group": "gateway.envoyproxy.io",
                    "kind": "Backend",
                    "name": r.status.routing.backendName,
                    "port": 80,
                    "weight": 1,
                }
            )
        return refs


def compose(req: fnv1.RunFunctionRequest, rsp: fnv1.RunFunctionResponse):
    """Compose ModelReplicas and control plane routing resources."""
    Composer(req, rsp).compose()
