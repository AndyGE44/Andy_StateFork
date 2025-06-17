#!/bin/bash
# set -euo pipefail

usage() {
    cat <<EOF
Usage: $0 -k <kernel_suffix> [options]

Options:
  -k <kernel_suffix>   Set local kernel version suffix (required)
  -b                   Enable Basic Debugging (default: disabled)
  -m                   Enable Memory Debugging (default: disabled)
  -l                   Enable Lock Debugging (default: disabled)
  -f                   Enable ftrace Debugging (default: disabled)
  -r                   Enable CRIU support (default: disabled)
  -n                   No confirmation prompt (auto proceed)
  -h                   Show this help message and exit
EOF
}

# Default values (debugging disabled)
kernel_provided=false
kname=""
d_basic=0
d_memory=0
d_lock=0
d_ftrace=0
d_criu=0
confirm=true

# Parse command-line options.
while getopts "k:bmlfrnh" opt; do
    case "$opt" in
        k) kname="$OPTARG"; kernel_provided=true ;;
        b) d_basic=1 ;;
        m) d_memory=1 ;;
        l) d_lock=1 ;;
        f) d_ftrace=1 ;;
        r) d_criu=1 ;;
        n) confirm=false ;;
        h) usage; exit 0 ;;
        \?) usage; exit 1 ;;
    esac
done

# Report function for colored messages.
report() {
    echo -e "\033[1;33mAKCS >> $1\033[0m"
}

# Function to prompt the user to run a command.
run_step() {
    local prompt="$1"
    local cmd="$2"
    if $confirm; then
        read -rp "$prompt (y/n): " ans
        if [[ "$ans" != "y" && "$ans" != "Y" ]]; then
            report "Skipped: $cmd"
            return
        fi
    fi
    report "Running: $cmd"
    eval "$cmd"
}

# Trap errors and print a message.
trap 'echo "An error occurred. Exiting." >&2' ERR

# Welcome message.
report "Welcome to the Alex Kernel Configuration Script!"

# Check if kernel suffix is provided.
if [ "$kernel_provided" = false ] || [ -z "$kname" ]; then
    report "Error: Kernel version suffix is required."
    usage
    exit 1
fi

# Display the current configuration.
echo "Kernel Configuration Script"
echo "---------------------------"
echo "Kernel Suffix        : $kname"
echo "Basic Debugging      : $([ "$d_basic" -eq 1 ] && echo "Enabled" || echo "Disabled")"
echo "Memory Debugging     : $([ "$d_memory" -eq 1 ] && echo "Enabled" || echo "Disabled")"
echo "Lock Debugging       : $([ "$d_lock" -eq 1 ] && echo "Enabled" || echo "Disabled")"
echo "ftrace Debugging     : $([ "$d_ftrace" -eq 1 ] && echo "Enabled" || echo "Disabled")"
echo "CRIU Support         : $([ "$d_criu" -eq 1 ] && echo "Enabled" || echo "Disabled")"
echo ""

if $confirm; then
    read -rp "Proceed with the above configuration? (y/n): " answer
    if [[ "$answer" != "y" && "$answer" != "Y" ]]; then
        echo "Aborted by user."
        exit 1
    fi
fi

report "Starting kernel configuration process..."

# Ensure we are inside a git repository.
repo_root=$(git rev-parse --show-toplevel 2>/dev/null) || {
    echo "Not inside a git repository. Exiting." >&2
    exit 1
}
cd "$repo_root" || exit 1
report "Switched to repository root: $(pwd)"

# Check that the linux directory exists.
if [ ! -d "linux" ]; then
    echo "Directory 'linux' not found in repository root. Exiting." >&2
    exit 1
fi

cd linux || exit 1
report "Changed directory to: $(pwd)"

# Clean previous configurations.
report "Removing previous configuration files..."
make mrproper

# Generate the default configuration.
report "Generating default configuration..."
make olddefconfig

# Set the local kernel version suffix.
report "Setting local version to '$kname'..."
scripts/config --set-str LOCALVERSION "$kname"

# Clear system trusted keys.
report "Clearing system trusted keys..."
scripts/config --set-str SYSTEM_TRUSTED_KEYS ""
scripts/config --set-str SYSTEM_REVOCATION_KEYS ""

# Optimize configuration by turning off unused modules.
run_step "Optimizing configuration by turning off unused modules..." "yes '' | make localmodconfig"

# Apply debugging options based on the configuration.
if [ "$d_basic" -eq 1 ]; then
    report "Enabling Basic Debugging..."
    scripts/config --enable CONFIG_DEBUG_KERNEL
    scripts/config --enable CONFIG_DEBUG_INFO
    scripts/config --enable CONFIG_KALLSYMS
    scripts/config --enable CONFIG_PRINTK_CALLER
fi

if [ "$d_memory" -eq 1 ]; then
    report "Enabling Memory Debugging..."
    scripts/config --enable CONFIG_KASAN
    scripts/config --enable CONFIG_KASAN_INLINE
    scripts/config --enable CONFIG_STACK_VALIDATION
    scripts/config --enable CONFIG_SLUB_DEBUG
    scripts/config --enable CONFIG_DEBUG_KMEMLEAK
fi

if [ "$d_lock" -eq 1 ]; then
    report "Enabling Lock Debugging..."
    scripts/config --enable CONFIG_PROVE_LOCKING
    scripts/config --enable CONFIG_DEBUG_LOCKDEP
    scripts/config --enable CONFIG_DEBUG_SPINLOCK
fi

if [ "$d_ftrace" -eq 1 ]; then
    report "Enabling ftrace Debugging..."
    scripts/config --enable CONFIG_FUNCTION_TRACE
    scripts/config --enable CONFIG_FUNCTION_GRAPH_TRACER
    scripts/config --enable CONFIG_STACK_TRACE
    scripts/config --enable CONFIG_DYNAMIC_FTRACE
fi

if [ "$d_criu" -eq 1 ]; then
    report "Enabling CRIU Support..."
    # Key configs, according to "https://criu.org/Linux_kernel"
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
    # Optional features for CRIU
    scripts/config --enable CONFIG_INOTIFY_USER
    scripts/config --enable CONFIG_FANOTIFY
    scripts/config --enable CONFIG_MEMCG
    scripts/config --enable CONFIG_CGROUP_DEVICE
    scripts/config --enable CONFIG_MACVLAN
    scripts/config --enable CONFIG_BRIDGE
    scripts/config --enable CONFIG_BINFMT_MISC
    scripts/config --enable CONFIG_IA32_EMULATION
    # Incremental dump features
    scripts/config --enable CONFIG_MEM_SOFT_DIRTY
    scripts/config --enable CONFIG_USERFAULTFD
    # My personal choices
    scripts/config --enable CONFIG_INET_TCP_DIAG
    scripts/config --enable CONFIG_NETFILTER
    scripts/config --enable CONFIG_NETFILTER_ADVANCED
    scripts/config --enable CONFIG_NETFILTER_XTABLES
    scripts/config --enable CONFIG_NETFILTER_XT_MARK
    scripts/config --enable CONFIG_NETFILTER_XT_TARGET_MARK
    scripts/config --enable CONFIG_NETFILTER_XT_MATCH_MARK
    scripts/config --enable CONFIG_VETH
fi

report "Kernel configuration is complete!"
echo ""

# Interactive execution of the next steps.
run_step "Build the kernel using 'make -j\$(nproc)'?" "time make -j\$(nproc)"
run_step "Install kernel modules using 'sudo make modules_install'?" "sudo make modules_install"
run_step "Install the kernel using 'sudo make install'?" "sudo make install"
run_step "Reboot the system using 'sudo reboot'?" "sudo reboot"

report "Finished all steps. Thank you for using the kernel configuration script!"
