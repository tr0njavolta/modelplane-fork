"""Compose a ModelCache.

Stages a HuggingFace model onto a ReadWriteMany PVC on every matched
InferenceCluster via a one-shot hydration Job. Pods that reference the
cache (ModelDeployment.spec.modelCacheRef -> ModelReplica) mount the PVC
at /mnt/models, so weights are downloaded once per cluster and read N
times by every pod in an LWS gang.

v0.1 surface (locked to the merged XRD): source `huggingFace` only,
Modelplane-managed RWX PVC, replication to all matching clusters.
"""

import grpc
from crossplane.function import logging, resource, response
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from crossplane.function.proto.v1 import run_function_pb2_grpc as grpcv1
from models.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from models.ai.modelplane.modelcache import v1alpha1

# Condition types/reasons for the ModelCache XR.
CONDITION_TYPE_SOURCE_VALID = "SourceValid"
CONDITION_TYPE_CLUSTERS_MATCHED = "ClustersMatched"
CONDITION_TYPE_ARTIFACT_READY = "ArtifactReady"

CONDITION_REASON_MATCHED = "Matched"
CONDITION_REASON_NO_CLUSTERS = "NoClusters"
CONDITION_REASON_HYDRATING = "Hydrating"
CONDITION_REASON_STAGED = "Staged"
CONDITION_REASON_PARTIAL = "Partial"
CONDITION_REASON_NO_SOURCE = "NoSource"
CONDITION_REASON_SUPPORTED = "Supported"

# Per-cluster phases reported in status.clusters[].phase.
PHASE_PENDING = "Pending"
PHASE_HYDRATING = "Hydrating"
PHASE_READY = "Ready"
PHASE_FAILED = "Failed"

# Namespace on the workload cluster where the PVC + Job land. This MUST match
# the namespace the serving pods land in (native.py/llmd.py `_REMOTE_NAMESPACE`,
# also "default") — a pod can only mount a PVC in its own namespace. The two
# functions hardcode this independently (no shared lib); they are a contract and
# must change together. If serving moves to per-deployment namespaces (negz's
# musing on #99), the cache PVC namespace moves with it.
REMOTE_NS = "default"

# The cluster-presence label every InferenceCluster carries; the matcher
# always includes it (match_labels={} is dropped by protobuf). This mirrors
# compose-model-deployment's cluster matching exactly. negz's PR #51 removes
# this workaround (bare ResourceSelector once `up` ships Crossplane >=2.2.1 and
# function-sdk-python grows a require_all helper) — when it lands, migrate this
# matcher alongside compose-model-deployment's, not separately.
LABEL_KEY_CLUSTER = "modelplane.ai/cluster"
LABEL_VALUE_CLUSTER = "true"

# Hydration container. python:3.11-slim has pip; we install huggingface_hub
# at runtime. A Modelplane-owned image with the tool preinstalled is a
# follow-up.
HYDRATION_IMAGE = "python:3.11-slim"
HYDRATION_MOUNT = "/mnt/artifact"

# Per-source default RWX storage class, mirroring the InferenceCluster XRD
# defaults (GKE/Existing -> Filestore-backed modelplane-rwx; EKS -> EFS-backed
# modelplane-rwx-efs). Used only when a cluster omits its cache block entirely:
# Pydantic doesn't apply the nested storageClassName default in that case, so a
# flat "modelplane-rwx" fallback would point an EKS PVC at a non-existent class.
_DEFAULT_STORAGE_CLASS = {"GKE": "modelplane-rwx", "EKS": "modelplane-rwx-efs", "Existing": "modelplane-rwx"}


class FunctionRunner(grpcv1.FunctionRunnerService):
    """A FunctionRunner handles gRPC RunFunctionRequests."""

    def __init__(self):
        self.log = logging.get_logger()

    async def RunFunction(self, req: fnv1.RunFunctionRequest, _: grpc.aio.ServicerContext) -> fnv1.RunFunctionResponse:
        log = self.log.bind(tag=req.meta.tag)
        log.info("Running function")
        rsp = response.to(req)
        Composer(req, rsp).compose()
        return rsp


class Composer:
    def __init__(self, req, rsp):
        self.req = req
        self.rsp = rsp
        self.xr = v1alpha1.ModelCache(**resource.struct_to_dict(req.observed.composite.resource))
        self.clusters: list[icv1alpha1.InferenceCluster] = []

    def compose(self):
        # The XRD can't yet enforce "exactly one source" (no CEL union rule —
        # issue #28), so a ModelCache with an empty/unknown source reaches us.
        # Fail fast with a clear condition rather than NPE in _hf_hydration.
        # This is also the seam where future sources (s3/http/inline) plug in:
        # extend _source_supported() and dispatch in _job_manifest().
        if not self._source_supported():
            response.set_conditions(
                self.rsp,
                resource.Condition(
                    typ=CONDITION_TYPE_SOURCE_VALID,
                    status="False",
                    reason=CONDITION_REASON_NO_SOURCE,
                    message="spec.source.huggingFace is required (the only v0.1 source)",
                ),
            )
            response.warning(self.rsp, "ModelCache has no supported source set")
            return
        response.set_conditions(
            self.rsp,
            resource.Condition(typ=CONDITION_TYPE_SOURCE_VALID, status="True", reason=CONDITION_REASON_SUPPORTED),
        )
        if not self.resolve_inputs():
            return
        matched = self.match_clusters()
        for cluster in matched:
            self.compose_cluster_resources(cluster)
        per_cluster_phase = [(c.metadata.name, self.derive_cluster_phase(c.metadata.name)) for c in matched]
        self.mark_ready_resources(per_cluster_phase)
        self.write_status(matched, per_cluster_phase)
        self.derive_conditions(matched, per_cluster_phase)
        self.emit_events(matched, per_cluster_phase)

    def _source_supported(self) -> bool:
        """True when the cache declares a source this version implements.

        v0.1 implements only huggingFace. New sources extend this and the
        dispatch in _job_manifest()."""
        return self.xr.spec.source.huggingFace is not None

    # Stubs — each is replaced by its real implementation in a later task, so
    # the Composer is complete and importable from Task 1 onward and every
    # task's tests run against a whole object (no AttributeError mid-pipeline).
    def resolve_inputs(self) -> bool:  # Task 2
        return False

    def match_clusters(self) -> list:  # Task 2
        return []

    def compose_cluster_resources(self, cluster) -> None:  # Task 2
        pass

    def derive_cluster_phase(self, cluster_name: str) -> str:  # Task 4  # noqa: ARG002 (stub)
        return PHASE_PENDING

    def mark_ready_resources(self, per_cluster_phase) -> None:  # Task 4
        pass

    def write_status(self, matched, per_cluster_phase) -> None:  # Task 4
        pass

    def derive_conditions(self, matched, per_cluster_phase) -> None:  # Task 4
        pass

    def emit_events(self, matched, per_cluster_phase) -> None:  # Task 4
        pass
