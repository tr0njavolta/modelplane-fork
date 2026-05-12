"""Serving profile matching.

Shared between the deploy function (scheduling) and the replica function
(profile resolution). Both need to walk a model's serving[] array and find
the first profile matching a cluster's labels.
"""

from ..model.ai.modelplane.clustermodel import v1alpha1 as cmv1alpha1
from ..model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1


def match_profile(
    model: cmv1alpha1.ClusterModel,
    cluster: icv1alpha1.InferenceCluster,
) -> cmv1alpha1.ServingItem | None:
    """Find the first serving profile that matches a cluster.

    A profile matches if its environmentSelector (if set) matches the
    cluster's labels. With no selector, the profile matches any cluster.
    """
    cluster_labels = cluster.metadata.labels or {}

    for profile in model.spec.serving or []:
        if profile.environmentSelector and profile.environmentSelector.matchLabels:
            required_labels = profile.environmentSelector.matchLabels
            if not all(cluster_labels.get(k) == v for k, v in required_labels.items()):
                continue

        return profile

    return None
