## Corrected Steps for Newer ZFS on Ubuntu
If you want the latest version of ZFS (beyond what Ubuntu and JonathonF's PPA offer), follow these general steps:

### Install build dependencies

Open a terminal and run the following command to install all necessary build dependencies:
```bash
sudo apt install build-essential autoconf automake libtool gawk alien fakeroot dkms \
libblkid-dev uuid-dev libudev-dev libssl-dev zlib1g-dev libaio-dev libattr1-dev \
libelf-dev linux-headers-$(uname -r) python3 python3-dev python3-setuptools python3-cffi \
libffi-dev python3-packaging git
```
### Clone and build ZFS from source

Run the following commands to clone the ZFS repository, check out the latest stable release (`zfs-2.2.7`), and build it from source:
```bash
git clone https://github.com/openzfs/zfs
cd zfs
git checkout zfs-2.2.7
sh autogen.sh
./configure
make -s -j$(nproc)
sudo make install
sudo ldconfig
sudo depmod
sudo modprobe zfs
```
### Verify installation and module

Run the following commands to verify that ZFS has been installed correctly:
```bash
zfs version
zpool version
lsmod | grep zfs
```
