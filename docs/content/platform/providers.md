---
title: Supported Providers
weight: 40
description: The clouds and neoclouds Modelplane runs on today, and the Crossplane providers it grows into.
---
Modelplane is built on [Crossplane](https://crossplane.io) and shares its
infrastructure providers, so the set of clouds and neoclouds it reaches grows
alongside Crossplane itself. This page shows where Modelplane runs today and
where it's headed.

A provider can show up here in three ways:

{{< hint "note" >}}
- **Provisioning supported.** Modelplane creates and manages the whole cluster
  from an `InferenceCluster`, selected through `provisioning.provider`. GKE and
  EKS work this way today.
- **Bring your own supported.** Register a cluster you already run with
  `source: Existing`. This works on any provider whose Kubernetes meets
  Modelplane's requirements (Dynamic Resource Allocation and a recent Kubernetes
  version), so you can run on the providers below now, ahead of native
  provisioning.
- **Crossplane provider exists.** A Crossplane provider is published for the
  cloud. That provider is the path by which native provisioning lands, so it
  marks where Modelplane can grow next.
{{< /hint >}}

## Clouds and neoclouds

Listed alphabetically, spanning hyperscalers and GPU-specialist neoclouds. Each
runs a managed Kubernetes service with GPU node pools, so the bring-your-own path
covers them all today. Where a Crossplane provider exists, it's the path to
native provisioning.

{{< table >}}
| Provider / service | Accelerators | Provisioning | BYO | Crossplane |
|---|---|---|---|---|
| Alibaba Cloud (ACK) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-upjet-alibabacloud" "provider-upjet-alibabacloud" "community" >}} |
| AWS (EKS) | {{< accel nvidia >}} {{< accel trainium >}} | ✓ | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-upjet-aws" "provider-upjet-aws" "community" >}} |
| Civo (K3s) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-civo" "provider-civo" "community" >}} |
| CoreWeave (CKS) | {{< accel nvidia >}} | Planned | ✓ | none yet |
| Crusoe (CMK) | {{< accel nvidia >}} {{< accel amd >}} | Planned | ✓ | none yet |
| DigitalOcean (DOKS) | {{< accel nvidia >}} {{< accel amd >}} | Planned | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-upjet-digitalocean" "provider-upjet-digitalocean" "community" >}} |
| Fluidstack (Managed Kubernetes) | {{< accel nvidia >}} | Planned | ✓ | none yet |
| Google Cloud (GKE) | {{< accel nvidia >}} {{< accel tpu >}} | ✓ | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-upjet-gcp" "provider-upjet-gcp" "community" >}} |
| Huawei Cloud (CCE) | {{< accel nvidia >}} {{< accel ascend >}} | Planned | ✓ | {{< repolink "https://github.com/huaweicloud/provider-huaweicloud" "provider-huaweicloud" "alpha" >}} |
| IBM Cloud (IKS) | {{< accel nvidia >}} | Planned | ✓ | none active |
| Lambda (Managed Kubernetes) | {{< accel nvidia >}} | Planned | ✓ | none yet |
| Linode / Akamai (LKE) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/linode/provider-linode" "provider-linode" "official" >}} |
| Microsoft Azure (AKS) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-upjet-azure" "provider-upjet-azure" "community" >}} |
| Nebius (Managed Kubernetes) | {{< accel nvidia >}} | Planned | ✓ | none yet |
| Oracle Cloud (OKE) | {{< accel nvidia >}} {{< accel amd >}} | Planned | ✓ | {{< repolink "https://github.com/oracle/crossplane-provider-oci" "crossplane-provider-oci" "official" >}} |
| OVHcloud (Managed Kubernetes) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/edixos/provider-ovh" "edixos/provider-ovh" "community" >}} |
| Scaleway (Kapsule) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/scaleway/crossplane-provider-scaleway" "crossplane-provider-scaleway" "official" >}} |
| Tencent Cloud (TKE) | {{< accel nvidia >}} | Planned | ✓ | {{< repolink "https://github.com/crossplane-contrib/provider-tencentcloud" "provider-tencentcloud" "community" >}} |
| Voltage Park (Managed Kubernetes) | {{< accel nvidia >}} | Planned | ✓ | none yet |
| Vultr (VKE) | {{< accel nvidia >}} {{< accel amd >}} | Planned | ✓ | {{< repolink "https://github.com/vultr/crossplane-provider-vultr" "crossplane-provider-vultr" "official" >}} |
{{< /table >}}

{{< hint "note" >}}
**On-premises and bare metal.** Running NVIDIA DGX systems (BasePOD or SuperPOD)
or any bare-metal cluster on your own hardware works the same way: stand up
Kubernetes with NVIDIA Base Command Manager, Run:ai, or your own tooling, then
register it with `source: Existing`. Modelplane installs its serving stack on the
cluster you bring; it doesn't provision the hardware.
{{< /hint >}}

Native provisioning expands as more Crossplane providers ship; until then, the
bring-your-own path runs Modelplane on any conformant Kubernetes cluster today.

{{< hint "tip" >}}
Don't see your cloud or neocloud, or want to be added?
[Open an issue](https://github.com/modelplaneai/modelplane/issues/new) and we'll
track it.
{{< /hint >}}

{{< cardgroup cols="2" >}}
{{< card title="Register a Cluster" href="/platform/inference-cluster/" >}}
Add a cluster to Modelplane, provisioned or bring-your-own.
{{< /card >}}
{{< card title="Define Hardware Classes" href="/platform/inference-class/" >}}
Describe the GPUs and provisioning recipe each node pool uses.
{{< /card >}}
{{< /cardgroup >}}
