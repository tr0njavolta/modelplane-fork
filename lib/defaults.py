"""Populate default values on Pydantic models.

Optional nested fields (status sub-objects, optional spec groups) require
guard chains at every access site. These functions return a deep copy with
all intermediate Optional fields populated with their zero values, so
downstream code can access fields directly.
"""

from ..model.ai.modelplane.inferencecluster import v1alpha1 as icv1alpha1
from ..model.ai.modelplane.inferencegateway import v1alpha1 as igwv1alpha1
from ..model.ai.modelplane.modelreplica import v1alpha1 as mrv1alpha1


def inference_cluster(
    ic: icv1alpha1.InferenceCluster,
) -> icv1alpha1.InferenceCluster:
    """Return a copy with status fields defaulted."""
    ic = ic.model_copy(deep=True)
    ic.status = ic.status or icv1alpha1.Status()
    ic.status.providerConfigRef = ic.status.providerConfigRef or icv1alpha1.ProviderConfigRef()
    ic.status.gateway = ic.status.gateway or icv1alpha1.Gateway()
    ic.status.capacity = ic.status.capacity or icv1alpha1.Capacity()
    ic.status.capacity.gpuPools = ic.status.capacity.gpuPools or []
    return ic


def model_replica(
    r: mrv1alpha1.ModelReplica,
) -> mrv1alpha1.ModelReplica:
    """Return a copy with status fields defaulted."""
    r = r.model_copy(deep=True)
    r.metadata = r.metadata or mrv1alpha1.ModelReplica().metadata
    return r


def inference_gateway(
    gw: igwv1alpha1.InferenceGateway,
) -> igwv1alpha1.InferenceGateway:
    """Return a copy with status fields defaulted."""
    gw = gw.model_copy(deep=True)
    gw.status = gw.status or igwv1alpha1.Status()
    return gw
