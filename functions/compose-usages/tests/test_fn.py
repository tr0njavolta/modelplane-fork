"""Tests for the compose-usages function."""

import dataclasses
import unittest

from crossplane.function import logging, resource
from crossplane.function.proto.v1 import run_function_pb2 as fnv1
from function import fn
from google.protobuf import duration_pb2 as durationpb
from google.protobuf import json_format
from google.protobuf import struct_pb2 as structpb

_NAMESPACE = "test-ns"
_PC = "test-cluster"

_RELEASE = {
    "apiVersion": "helm.m.crossplane.io/v1beta1",
    "kind": "Release",
    "metadata": {"namespace": _NAMESPACE},
    "spec": {
        "providerConfigRef": {"kind": "ProviderConfig", "name": _PC},
        "forProvider": {"chart": {"name": "cert-manager"}},
    },
}

_OBJECT = {
    "apiVersion": "kubernetes.m.crossplane.io/v1alpha1",
    "kind": "Object",
    "metadata": {"namespace": _NAMESPACE},
    "spec": {
        "providerConfigRef": {"kind": "ProviderConfig", "name": _PC},
        "forProvider": {"manifest": {"apiVersion": "v1", "kind": "Namespace"}},
    },
}

# Not a consumer kind: a ProviderConfig gets no Usage of its own.
_PROVIDER_CONFIG = {
    "apiVersion": "helm.m.crossplane.io/v1beta1",
    "kind": "ProviderConfig",
    "metadata": {"name": _PC, "namespace": _NAMESPACE},
    "spec": {},
}

# A consumer kind (Object) that references no ProviderConfig: gets no Usage.
_OBJECT_NO_PC = {
    "apiVersion": "kubernetes.m.crossplane.io/v1alpha1",
    "kind": "Object",
    "metadata": {"namespace": _NAMESPACE},
    "spec": {"forProvider": {"manifest": {"apiVersion": "v1", "kind": "ConfigMap"}}},
}

# A Release that already carries a label, to check relabeling preserves it.
_RELEASE_WITH_LABEL = {
    "apiVersion": "helm.m.crossplane.io/v1beta1",
    "kind": "Release",
    "metadata": {"namespace": _NAMESPACE, "labels": {"existing": "keep"}},
    "spec": {
        "providerConfigRef": {"kind": "ProviderConfig", "name": _PC},
        "forProvider": {"chart": {"name": "prometheus"}},
    },
}


def _labelled(d: dict, consumer: str) -> dict:
    """A copy of d with the usage-consumer label stamped on it."""
    out = {**d, "metadata": {**d.get("metadata", {})}}
    out["metadata"]["labels"] = {
        **d.get("metadata", {}).get("labels", {}),
        "modelplane.ai/usage-consumer": consumer,
    }
    return out


def _usage(api_version: str, kind: str, consumer: str) -> dict:
    return {
        "apiVersion": "protection.crossplane.io/v1beta1",
        "kind": "Usage",
        "metadata": {"namespace": _NAMESPACE},
        "spec": {
            "of": {
                "apiVersion": api_version,
                "kind": "ProviderConfig",
                "resourceRef": {"name": _PC},
            },
            "by": {
                "apiVersion": api_version,
                "kind": kind,
                "resourceSelector": {
                    "matchControllerRef": True,
                    "matchLabels": {"modelplane.ai/usage-consumer": consumer},
                },
            },
            "replayDeletion": True,
        },
    }


def _composite(namespace: str | None = _NAMESPACE) -> structpb.Struct:
    metadata = {"name": "test"}
    if namespace is not None:
        metadata["namespace"] = namespace
    return resource.dict_to_struct(
        {
            "apiVersion": "infrastructure.modelplane.ai/v1alpha1",
            "kind": "ServingStack",
            "metadata": metadata,
        }
    )


@dataclasses.dataclass
class Case:
    """A test case for compose-usages."""

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
        cases = [
            Case(
                name="labels each consumer and composes a Usage per ProviderConfig reference",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(composite=fnv1.Resource(resource=_composite())),
                    desired=fnv1.State(
                        composite=fnv1.Resource(resource=_composite()),
                        resources={
                            "cert-manager": fnv1.Resource(resource=resource.dict_to_struct(_RELEASE)),
                            "gateway-namespace": fnv1.Resource(resource=resource.dict_to_struct(_OBJECT)),
                            "prometheus": fnv1.Resource(resource=resource.dict_to_struct(_RELEASE_WITH_LABEL)),
                            "config-map": fnv1.Resource(resource=resource.dict_to_struct(_OBJECT_NO_PC)),
                            "provider-config-helm": fnv1.Resource(resource=resource.dict_to_struct(_PROVIDER_CONFIG)),
                        },
                    ),
                ),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
                    desired=fnv1.State(
                        composite=fnv1.Resource(resource=_composite()),
                        resources={
                            "cert-manager": fnv1.Resource(
                                resource=resource.dict_to_struct(_labelled(_RELEASE, "cert-manager")),
                            ),
                            "gateway-namespace": fnv1.Resource(
                                resource=resource.dict_to_struct(_labelled(_OBJECT, "gateway-namespace")),
                            ),
                            # Existing labels are preserved when the consumer label is stamped.
                            "prometheus": fnv1.Resource(
                                resource=resource.dict_to_struct(_labelled(_RELEASE_WITH_LABEL, "prometheus")),
                            ),
                            # An Object with no providerConfigRef is left untouched, no Usage.
                            "config-map": fnv1.Resource(
                                resource=resource.dict_to_struct(_OBJECT_NO_PC),
                            ),
                            "provider-config-helm": fnv1.Resource(
                                resource=resource.dict_to_struct(_PROVIDER_CONFIG),
                            ),
                            "usage-pc-cert-manager": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    _usage("helm.m.crossplane.io/v1beta1", "Release", "cert-manager")
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                            "usage-pc-gateway-namespace": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    _usage("kubernetes.m.crossplane.io/v1alpha1", "Object", "gateway-namespace")
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                            "usage-pc-prometheus": fnv1.Resource(
                                resource=resource.dict_to_struct(
                                    _usage("helm.m.crossplane.io/v1beta1", "Release", "prometheus")
                                ),
                                ready=fnv1.READY_TRUE,
                            ),
                        },
                    ),
                    context=structpb.Struct(),
                ),
            ),
            Case(
                name="no Usages when the composite has no namespace",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(composite=fnv1.Resource(resource=_composite(namespace=None))),
                    desired=fnv1.State(
                        composite=fnv1.Resource(resource=_composite(namespace=None)),
                        resources={
                            "cert-manager": fnv1.Resource(resource=resource.dict_to_struct(_RELEASE)),
                        },
                    ),
                ),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
                    desired=fnv1.State(
                        composite=fnv1.Resource(resource=_composite(namespace=None)),
                        resources={
                            "cert-manager": fnv1.Resource(resource=resource.dict_to_struct(_RELEASE)),
                        },
                    ),
                    context=structpb.Struct(),
                ),
            ),
            Case(
                name="no consumers means no Usages",
                req=fnv1.RunFunctionRequest(
                    observed=fnv1.State(composite=fnv1.Resource(resource=_composite())),
                    desired=fnv1.State(
                        composite=fnv1.Resource(resource=_composite()),
                        resources={
                            "provider-config-helm": fnv1.Resource(resource=resource.dict_to_struct(_PROVIDER_CONFIG)),
                        },
                    ),
                ),
                want=fnv1.RunFunctionResponse(
                    meta=fnv1.ResponseMeta(ttl=durationpb.Duration(seconds=60)),
                    desired=fnv1.State(
                        composite=fnv1.Resource(resource=_composite()),
                        resources={
                            "provider-config-helm": fnv1.Resource(
                                resource=resource.dict_to_struct(_PROVIDER_CONFIG),
                            ),
                        },
                    ),
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
