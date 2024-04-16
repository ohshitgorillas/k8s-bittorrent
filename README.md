# k8s-bittorrent

The following are instructions for setting up Bittorrent in Kubernetes. This project uses
* A simple WireGuard container for VPN encryption
* Transmission, as it has the most available GUI programs for remote access.
* nginx to provide encrypted remote access
* Keel for auto-updates
* Liveness probes to keep both containers running hands-free

Prerequisites:
* VPN provider that supports WireGuard, and a forwarded port
* Kubernetes cluster with the ability to set unsafe sysctls on the node
* wireguard-tools installed on the node's host system
* Keel (https://keel.sh/docs/1)
* A private k8s registry for Transmission's liveness probe (https://www.linuxtechi.com/setup-private-docker-registry-kubernetes/)

# Instructions

1. Create, or re-create, the desired node with the unsafe sysctl `net.ipv4.conf.all.src_valid_mark` enabled (and, if you want IPv6, `net.ipv6.conf.all.forwarding`). I use kubeadm, here's an example join config file:

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

Take special note of the size of the 10.0.0.0 subnet. For example, if you are using Cilium with the default CIDR of 10.0.0.0/8, a subnet size of /8 is appropriate. In my case, my LAN subnet is 10.0.0.0/24, but the AirVPN DNS server is located at 10.145.0.1, so using /8 for the PostUp/PreDown rules might result in DNS leakage.


3. Determine your username and password for Transmission, and get your forwarded peer port from your VPN provider. Convert the values to base64:

```
➜  ~ echo admin | base64
YWRtaW4K
➜  ~ echo password | base64
cGFzc3dvcmQK
➜  ~ echo 42069 | base64
NDIwNjkK
```

Enter the base64 values into `secrets_transmission.yaml` and run `kubectl apply -f secrets_transmission.yaml`. 


4. To build the Transmission liveness server into your private registry, cd into the `liveserver` directory and execute the following commands:

```
chmod +x proxy.py
docker build -t transmission-liveness-server .
docker tag transmission-liveness-server <registry IP:port>/transmission-liveness-server
docker push <registry IP:port>/transmission-liveness-server
```


5. Edit the deployment manifest `deployment_bittorrent.yaml`. Specifically, pay attention to:
* node name
* timezone
* registry node IP:port in transmission-liveness-server image
* volume host paths (leave /lib/modules but edit the rest for your system)


6. If you already have a Transmission config file from a previous setup, open it. Otherwise, execute `kubectl apply -f deployment_bittorrent.yaml` then `kubectl delete deployment bittorrent` and edit the file `transmission/config/settings.json`. Locate the bind address settings:

```
    "bind-address-ipv4": "0.0.0.0",
    "bind-address-ipv6": "::",
```

Enter the addresses from the `[Interfaces]` section of your WireGuard config. This prevents Transmission from communicating with the internet outside of your WireGuard tunnel. Bring the pod back up, and start its RPC port service, with `kubectl apply -f deployment_bittorrent.yaml -f service_transmission.yaml` and check for errors with 

```
kubectl logs <bittorrent pod name> -c airvpn
kubectl logs <bittorrent pod name> -c transmission
kubectl logs <bittorrent pod name> -c transmission-liveness-server
```


7. Edit the deployment manifest `deployment_nginx.yaml`. Specifically, pay attention to:
* node name
* whether you want to mount nginx-logs or not for fail2ban integration
* volume host paths

Next, edit `service_transmission.yaml` and change to your desired NodePort port. 

Then, run `kubectl apply -f configmap_nginx.yaml -f deployment_nginx.yaml -f service_nginx.yaml`.

You should now be able to access your Transmission RPC at <node IP>:<nodeport port>.
