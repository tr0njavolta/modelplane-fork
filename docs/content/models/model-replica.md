---
title: Understand Replicas
weight: 50
description: One instance of a ModelDeployment placed on a specific cluster. Created automatically by Modelplane.
---
<!-- vale write-good.Passive = NO -->
The `ModelDeployment` composition function creates `ModelReplicas`. Don't create
them directly.

**API:** [`modelplane.ai/v1alpha1` · ModelReplica]({{< ref "reference.md" >}}#crd-modelreplica)

Each replica represents a model deployed to a specific cluster. It reads the
replica's engines and composes a workload per engine from its member roles: a
native Kubernetes Deployment for a Standalone engine, or an llm-d
LeaderWorkerSet for a Leader/Worker gang. One Service and HTTPRoute, spanning
every engine's serving pods, front the replica as a unified OpenAI-compatible
endpoint.

Replicas are pinned to their cluster at creation time (`spec.clusterName`). If
the cluster is temporarily unavailable the replica stays pinned and the parent
`ModelDeployment` surfaces the degraded state via its conditions. If the
cluster is deleted entirely the parent `ModelDeployment` re-places the replica
on another viable cluster.
<!-- vale write-good.Passive = YES -->
