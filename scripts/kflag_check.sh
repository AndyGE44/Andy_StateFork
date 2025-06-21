#!/bin/bash
# Verifies whether key kernel flags are enabled in the currently running kernel

KERNEL_CONFIG="/boot/config-$(uname -r)"

echo "Verifying kernel flags in: $KERNEL_CONFIG"

readarray -t CONFIG_LINES <<'EOF'
scripts/config --enable CONFIG_EMBEDDED
scripts/config --enable CONFIG_EXPERT
scripts/config --enable CONFIG_CHECKPOINT_RESTORE
scripts/config --enable CONFIG_NAMESPACES
scripts/config --enable CONFIG_UTS_NS
scripts/config --enable CONFIG_IPC_NS
scripts/config --enable CONFIG_SYSVIPC_SYSCTL
scripts/config --enable CONFIG_PID_NS
scripts/config --enable CONFIG_NET_NS
scripts/config --enable CONFIG_FHANDLE
scripts/config --enable CONFIG_EVENTFD
scripts/config --enable CONFIG_EPOLL
scripts/config --enable CONFIG_UNIX_DIAG
scripts/config --enable CONFIG_INET_DIAG
scripts/config --enable CONFIG_INET_UDP_DIAG
scripts/config --enable CONFIG_PACKET_DIAG
scripts/config --enable CONFIG_NETLINK_DIAG
scripts/config --enable CONFIG_NETFILTER_XT_MARK
scripts/config --enable CONFIG_TUN
scripts/config --enable CONFIG_INOTIFY_USER
scripts/config --enable CONFIG_FANOTIFY
scripts/config --enable CONFIG_MEMCG
scripts/config --enable CONFIG_CGROUP_DEVICE
scripts/config --enable CONFIG_MACVLAN
scripts/config --enable CONFIG_BRIDGE
scripts/config --enable CONFIG_BINFMT_MISC
scripts/config --enable CONFIG_IA32_EMULATION
scripts/config --enable CONFIG_MEM_SOFT_DIRTY
scripts/config --enable CONFIG_USERFAULTFD
scripts/config --enable CONFIG_INET_TCP_DIAG
scripts/config --enable CONFIG_NETFILTER
scripts/config --enable CONFIG_NETFILTER_ADVANCED
scripts/config --enable CONFIG_NETFILTER_XTABLES
scripts/config --enable CONFIG_NETFILTER_XT_MARK
scripts/config --enable CONFIG_NETFILTER_XT_TARGET_MARK
scripts/config --enable CONFIG_NETFILTER_XT_MATCH_MARK
scripts/config --enable CONFIG_VETH
EOF

MISSING=0

for line in "${CONFIG_LINES[@]}"; do
  flag=$(echo "$line" | awk '{print $3}')
  if grep -q "^$flag=" "$KERNEL_CONFIG"; then
    echo -e "\033[92m    $flag is set\033[0m"
  else
    echo -e "\033[93m    $flag is MISSING\033[0m"
    ((MISSING++))
  fi
done

if [ "$MISSING" -eq 0 ]; then
  echo -e "\033[92mAll required flags are enabled.\033[0m"
else
  echo -e "\033[91m$MISSING flag(s) missing.\033[0m"
  exit 1
fi