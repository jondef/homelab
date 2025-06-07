Corrected Steps for Newer ZFS on Ubuntu
If you want the latest ZFS version (beyond what Ubuntu and JonathonF's PPA offer), use these general steps:

Install build dependencies:

bash
sudo apt install build-essential autoconf automake libtool gawk alien fakeroot dkms libblkid-dev uuid-dev libudev-dev libssl-dev zlib1g-dev libaio-dev libattr1-dev libelf-dev linux-headers-$(uname -r) python3 python3-dev python3-setuptools python3-cffi libffi-dev python3-packaging git
Clone and build ZFS from source:

bash
git clone https://github.com/openzfs/zfs
cd zfs
git checkout <desired-release-tag>
sh autogen.sh
./configure
make -s -j$(nproc)
sudo make install
sudo ldconfig
sudo depmod
sudo modprobe zfs
(Replace <desired-release-tag> with the latest stable release, e.g., zfs-2.2.2.)

Verify installation and module:

bash
zfs version
zpool version
lsmod | grep zfs