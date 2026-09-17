#!/bin/bash

SYSTEM_DIR=$1
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
