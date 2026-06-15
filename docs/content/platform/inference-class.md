---
title: Define Hardware Classes
weight: 20
description: Hardware recipe defining GPU type, count, and provisioning for a node pool.
---
<!-- vale write-good.Passive = NO -->
An `InferenceClass` is a tested recipe for a GPU node pool. It bundles:

**API:** [`modelplane.ai/v1alpha1` · InferenceClass]({{< ref "reference.md" >}}#crd-inferenceclass)

- **Devices**: the node's hardware as a list of Dynamic Resource Allocation (DRA)
  style devices, each with a driver, count, typed attributes, and capacity. A
  `claim: DRA` device (a GPU) is bound to pods through a DRA `ResourceClaim`; a
  `claim: Synthetic` device (an InfiniBand NIC, for example) is described for
  scheduling only. The scheduler matches a member's `nodeSelector` against these
  devices.
- **Provisioning** (optional): how to create a node pool of this class on a
  specific cloud. Omit for classes that describe BYO node pools that already
  exist. Set `provisioning.provider: GKE` with `gke.machineType` and
  `gke.accelerator` for GKE pools; set `provisioning.provider: EKS` with
  `eks.instanceType` for EKS. The `accelerator` block is provisioning input
  only — the scheduler matches against `spec.devices`, not this block.

Different clouds and GPU types imply different classes. A GKE L4 pool is
`gke-l4-1x-g2`. A bare-metal H100 pool is `h100-8x-ib` (no provisioning).

## Examples

GKE L4:

{{< manifests "platform/inference-class-gke-l4.yaml" >}}

H100 bare-metal (no provisioning):

{{< manifests "platform/inference-class-h100-byo.yaml" >}}
<!-- vale write-good.Passive = YES -->
