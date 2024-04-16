# k8s-bittorrent

The following are instructions for setting up BitTorrent in Kubernetes. This project uses
* A simple WireGuard container for VPN encryption
* Transmission, as it has the most available GUI programs for remote access.
* nginx to provide encrypted remote access
* Keel for auto-updates
* Liveness probes to keep both containers running hands-free
* Full IPv6 support

Prerequisites:
* VPN provider that supports WireGuard, and a forwarded port
* A registered domain, DDNS records linking it to your node's IP, and valid SSL certs
* A Kubernetes cluster with the ability to set unsafe sysctls on the node
* `wireguard-tools` installed on the node's host system
* Keel (https://keel.sh/docs/1)
* A private k8s registry for Transmission's liveness probe (https://www.linuxtechi.com/setup-private-docker-registry-kubernetes/)

# Instructions

1. Create, or re-create, the desired node with the unsafe sysctl `net.ipv4.conf.all.src_valid_mark` enabled (and, optionally, `net.ipv6.conf.all.forwarding`). I use kubeadm, here's an example join config file:

```
apiVersion: kubeadm.k8s.io/v1beta3
kind: JoinConfiguration
discovery:
  bootstrapToken:
    apiServerEndpoint: <endpoint:port>
    caCertHashes: 
      - <your certhash>
    token: <your join token>
nodeRegistration:
  kubeletExtraArgs:
    allowed-unsafe-sysctls: "net.ipv4.conf.all.src_valid_mark,net.ipv6.conf.all.forwarding"
```


2. Retrieve a WireGuard configuration file from your VPN provider, name it `wg0.conf` and, at the end of the `[Interface]` section, add the following:

```
PostUp = DROUTE=$(ip route | grep default | awk '{print $3}'); HOMENET=192.168.0.0/16; HOMENET2=10.0.0.0/24; HOMENET3=172.16.0.0/12; ip route add $HOMENET3 via $DROUTE; ip route add $HOMENET2 via $DROUTE; ip route add $HOMENET via $DROUTE; iptables -I OUTPUT -d $HOMENET -j ACCEPT; iptables -A OUTPUT -d $HOMENET2 -j ACCEPT; iptables -A OUTPUT -d $HOMENET3 -j ACCEPT; iptables -A OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT

PreDown = HOMENET=192.168.0.0/16; HOMENET2=10.0.0.0/24; HOMENET3=172.16.0.0/12; ip route del $HOMENET3 via $DROUTE;ip route del $HOMENET2 via $DROUTE; ip route del $HOMENET via $DROUTE; iptables -D OUTPUT ! -o %i -m mark ! --mark $(wg show %i fwmark) -m addrtype ! --dst-type LOCAL -j REJECT; iptables -D OUTPUT -d $HOMENET -j ACCEPT; iptables -D OUTPUT -d $HOMENET2 -j ACCEPT; iptables -D OUTPUT -d $HOMENET3 -j ACCEPT
```
These rules allow your LAN and Kubernetes subnets to communicate with the Transmission RPC port while blocking all other traffic not bound for the WireGuard tunnel, wg0.

IMPORTANT: Adjust subnet sizes in the rules to match your LAN and Kubernetes network ranges. For example, 10.0.0.0/8 might be appropriate for some cases, however, I use AirVPN for which the DNS server is located at 10.128.0.1, so using 10.0.0.0/8 might result in DNS leakage.


3. Encode your credentials and the forwarded port from your VPN provider into base64:

```
➜  ~ echo admin | base64
YWRtaW4K
➜  ~ echo password | base64
cGFzc3dvcmQK
➜  ~ echo 42069 | base64
NDIwNjkK
```

Enter the base64 values into `secrets_transmission.yaml` and run `kubectl apply -f secrets_transmission.yaml`. 


4. To build the Transmission liveness server into your private registry, cd into the `liveserver/` directory and execute the following commands:

```
chmod +x proxy.py
docker build -t transmission-liveness-server .
docker tag transmission-liveness-server <registry IP:port>/transmission-liveness-server
docker push <registry IP:port>/transmission-liveness-server
```


5. Prepare the main manifest for deployment by editing `deployment.yaml`. Specifically, pay attention to:
* node name
* timezone
* `<registry node IP>:<port>` in transmission-liveness-server image
* volume host paths (leave `/lib/modules`)
* mounting nginx-logs is optional for fail2ban integration


6. Next we'll set the bind addresses in Transmission to prevent data leakage outside of wg0, then deploy the pod. If you already have a Transmission config file from a previous setup, open it. Otherwise, execute `kubectl apply -f deployment.yaml` to generate the file `transmission/config/settings.json`, then `kubectl delete deployment bittorrent` to kill the pod (`settings.json` cannot be edited while Transmission is live). 

Locate the bind address settings:
```
    "bind-address-ipv4": "0.0.0.0",
    "bind-address-ipv6": "::",
```

Enter the `Addresses` from the `[Interfaces]` section of your WireGuard config. 

Finally, bring the pod back up, start the nginx NodePort service, and check for errors with the following commands: 

```
kubectl apply -f deployment.yaml -f service_nginx.yaml
kubectl logs <bittorrent pod name> wireguard
kubectl logs <bittorrent pod name> transmission
kubectl logs <bittorrent pod name> transmission-liveness-server
kubectl logs <bittorrent pod name> bittorrent-nginx
```

You should now be able to access your Transmission RPC at `https://<node IP>:<NodePort port>` and, once the port is forwarded on your router, `https://your.domain:<NodePort port>`.
