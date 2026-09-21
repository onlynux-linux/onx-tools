# Requested base coverage

Requested packages:
ncurses coreutils findutils diffutils libgcc bash grep gzip file sed gawk less util-linux which tar man-pages shadow e2fsprogs btrfs-progs xfsprogs f2fs-tools dosfstools procps-ng tzdata pciutils usbutils iana-etc kbd kmod acpid openssh dhcpcd iproute2 iputils iw wpa_supplicant traceroute ethtool sudo nvi nano linux glibc glibc-locales systemd dbus pam linux-firmware ca-certificates openssl onlynux-filesystem.

Initial reviewed adapters: gzip, sed, plus dependency seed zlib.
All other packages remain pending, not placeholder recipes advertised as ready.

Next: simple GNU tools, ncurses/readline, toolchain/glibc bootstrap, systemd/PAM integration,
filesystem ownership/layout, kernel/firmware.
libgcc is a GCC output; glibc-locales is a glibc output. Both need package splitting.
Toolchain dependency cycles require explicit bootstrap stages.
