#!/bin/bash

SYSTEM_DIR=$1
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
install -m 0755 "$SCRIPT_DIR/S21imu_priority" "$SYSTEM_DIR/etc/init.d/S21imu_priority"
rm -rf $SYSTEM_DIR/mnt/system/usr
rm -rf $SYSTEM_DIR/mnt/system/lib
rm -rf $SYSTEM_DIR/mnt/system/lib/libsns_gc*
rm -rf $SYSTEM_DIR/mnt/system/lib/libsns_imx*
rm -rf $SYSTEM_DIR/mnt/system/lib/libsns_sc*
rm -rf $SYSTEM_DIR/mnt/system/lib/libcipher.so

rm -rf $SYSTEM_DIR/mnt/system/m2m-deinterlace.ko
rm -rf $SYSTEM_DIR/mnt/system/efivarfs.ko

du -sh $SYSTEM_DIR/* |sort -rh

rm -rf $SYSTEM_DIR/etc/init.d/S23ntp
rm -rf $SYSTEM_DIR/bin/ntpd

RNDIS_INIT=$SYSTEM_DIR/etc/init.d/S77rndis
if [ ! -f "$RNDIS_INIT" ]; then
	echo "Missing RNDIS init script: $RNDIS_INIT"
	exit 1
fi
sed -i 's/ifconfig usb0 169\.254\.250\.73/ifconfig usb0 192.168.123.99 netmask 255.255.255.0/' "$RNDIS_INIT"

# Also support existing boot images whose reference DT still assigns FSIN/I2C
# to a nonexistent display panel. Do not let mipi_tx claim those GPIOs.
KO_LOADER="$SYSTEM_DIR/mnt/system/ko/loadsystemko.sh"
if [ -f "$KO_LOADER" ]; then
	sed -i 's@^insmod /mnt/system/ko/cv181x_mipi_tx.ko.*@insmod /mnt/system/ko/cv181x_mipi_tx.ko gpio=-1,0,-1,0,-1,0@' "$KO_LOADER"
fi
