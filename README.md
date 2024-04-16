# k8s-bittorrent

The following are instructions for setting up Bittorrent in Kubernetes. This project uses
* A simple WireGuard container for VPN encryption
* Transmission, as it has the most available GUI programs for remote access.
* nginx to provide encrypted remote access
* Keel for auto-updates
* Liveness probes to keep both containers running hands-free

Prerequisites:
* VPN provider that supports WireGuard and port forwarding
* Kubernetes cluster with the ability to set unsafe sysctls on the node
* wireguard-tools installed on the node's host system
* Keel (https://keel.sh/docs/1)
* A private k8s registry hold Transmission's liveness probe for Transmission (https://www.linuxtechi.com/setup-private-docker-registry-kubernetes/)

# Instructions

1. Create, or re-create, the desired node with the unsafe sysctl `net.ipv4.conf.all.src_valid_mark` enabled (and, if you want IPv6, `net.ipv6.conf.all.forwarding`). I use kubeadm, here's an example join config file:

```
apiVersion: kubeadm.k8s.io/v1beta3
kind: JoinConfiguration
patches:
  directory: /root/kubeadm-join-config-patches
discovery:
  bootstrapToken:
    apiServerEndpoint: 10.0.0.238:6443
    caCertHashes: 
      - sha256:a7f113898879a87e6ac782d87ba0bf2cf96a68d54aae6ce92c177f60af37fec6
    token: 9raiy6.h83aktcg2enuc6g2
nodeRegistration:
  kubeletExtraArgs:
    allowed-unsafe-sysctls: "net.ipv4.ip_forward,net.ipv6.conf.all.forwarding"
```
