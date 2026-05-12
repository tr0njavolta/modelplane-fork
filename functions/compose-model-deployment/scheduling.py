"""Schedule model replicas across inference clusters.

Matches serving profiles against clusters by optional label selector,
filters by GPU capacity, accounts for GPU usage by other deployments, and
returns a stable list of candidates that prefers clusters with existing
replicas.
"""

import math
from dataclasses import dataclass

from .lib import metadata, quantities, serving
from .model.ai.modelplane.clustermodel import v1alpha1 as cmv1alpha1
from .model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from .model.ai.modelplane.modeldeployment import v1alpha1 as mdv1alpha1
from .model.ai.modelplane.modelreplica import v1alpha1 as mrv1alpha1

# Supported scaling signals. All clusters use the same backend, so
# scaling capabilities are uniform.
SUPPORTED_SCALING_SIGNALS = {"Fixed", "Concurrency"}


@dataclass
class Candidate:
    """A cluster that matched scheduling criteria."""

    name: str
    gateway_address: str | None
    profile_name: str


def _pool_has_enough_nodes(pool, gpus_needed: int) -> bool:
    """Check whether a pool has enough nodes for multi-node inference.

    Returns True if the model fits on a single node or if there are enough
    nodes for multi-node.
    """
    count_per_node = int(pool.countPerNode or 0)
    if count_per_node <= 0 or gpus_needed <= count_per_node:
        return True  # Single-node — fits on one node.
    nodes_needed = math.ceil(gpus_needed / count_per_node)
    return int(pool.nodes or 0) >= nodes_needed


def schedule(
    deployment: mdv1alpha1.ModelDeployment,
    model: cmv1alpha1.ClusterModel,
    clusters: list[icv1alpha1.InferenceCluster],
    all_replicas: list[mrv1alpha1.ModelReplica],
) -> list[Candidate]:
    """Select clusters for model replicas.

    All inputs should be passed through their respective defaults.*
    functions before calling this — the function assumes Optional fields
    are populated with zero values.

    For each candidate cluster, walks the model's serving[] array to find
    the first profile whose environmentSelector (if any) matches the
    cluster's labels. Filters by VRAM capacity, subtracts GPUs used by
    other deployments' replicas, sorts to prefer clusters that already
    have replicas for this deployment (stability), and returns at most
    deployment.spec.clusters candidates.
    """
    model_vram_bytes = quantities.parse_quantity(model.spec.resources.vram)

    # Clusters that already have a replica for this deployment.
    existing_clusters = {
        r.spec.inferenceClusterRef.name
        for r in all_replicas
        if (r.metadata.labels or {}).get(metadata.LABEL_KEY_DEPLOYMENT) == deployment.metadata.name
    }

    candidates = []
    for cluster in clusters:
        # Find the first serving profile that matches this cluster.
        profile = serving.match_profile(model, cluster)
        if not profile:
            continue

        # Check scaling signal capability.
        if deployment.spec.scaling.signal not in SUPPORTED_SCALING_SIGNALS:
            continue

        # Find the pool that needs the fewest GPUs for this model.
        best_gpus_needed = None
        eligible_total = 0
        for pool in cluster.status.capacity.gpuPools:
            pool_mem = quantities.parse_quantity(pool.memory or "0Gi")
            if pool_mem <= 0:
                continue
            gpus_needed = max(1, math.ceil(model_vram_bytes / pool_mem))

            if not _pool_has_enough_nodes(pool, gpus_needed):
                continue

            eligible_total += int(pool.countPerNode or 0) * int(pool.nodes or 0)
            if best_gpus_needed is None or gpus_needed < best_gpus_needed:
                best_gpus_needed = gpus_needed

        if best_gpus_needed is None:
            continue

        # Subtract GPUs used by other deployments' replicas on this cluster.
        used_gpus = 0
        for r in all_replicas:
            if (r.metadata.labels or {}).get(metadata.LABEL_KEY_DEPLOYMENT) == deployment.metadata.name:
                continue  # Don't count our own replicas against us.
            if r.spec.inferenceClusterRef.name == cluster.metadata.name:
                used_gpus += r.status.resources.gpu.count or 0

        if eligible_total - used_gpus < best_gpus_needed:
            continue

        candidates.append(
            Candidate(
                name=cluster.metadata.name,
                gateway_address=cluster.status.gateway.address,
                profile_name=profile.name,
            )
        )

    # Prefer clusters that already have replicas for this deployment.
    # This prevents rescheduling when a new cluster comes online.
    # Within each group (existing vs new), sort by name for determinism.
    candidates.sort(
        key=lambda c: (
            0 if c.name in existing_clusters else 1,
            c.name,
        )
    )
    return candidates[: int(deployment.spec.clusters)]
