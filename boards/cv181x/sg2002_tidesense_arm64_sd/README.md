# TideSense SG2002 ARM64 / SD 配置

选择 `sg2002_tidesense_arm64_sd` 编译。系统架构为 ARM64（CA53），启动和根文件系统都放在 TF/SD 卡上。SD 分区定义在 `partition/partition_sd.xml`。

```sh
source build/envsetup_soc.sh
defconfig sg2002_tidesense_arm64_sd
build_all
```

## 制作并烧录 SD 卡

`build_all` 完成后，生成按三分区布局制作的整卡镜像：

```sh
python3 build/boards/cv181x/sg2002_tidesense_arm64_sd/make_sdcard_image.py
```

镜像路径为 `install/soc_sg2002_tidesense_arm64_sd/tidesense-sdcard.img`。脚本按 `partition_sd.xml` 创建 MBR 和 BOOT/ROOTFS/DATA 三个分区：BOOT 是 FAT32，内含 `fip.bin` 和 `boot.sd`；ROOTFS 是 ext4，卷标为小写 `rootfs` 以匹配 initramfs 的挂载脚本；DATA 是 ext4，并在系统启动时挂载到 `/mnt/data`。

在 Linux 上先用 `lsblk` 确认 SD 卡对应的整盘设备，然后写入整张卡（下面的 `/dev/sdX` 必须替换成实际设备，例如 `/dev/sdb`，不能写成分区 `/dev/sdb1`）：

```sh
lsblk -o NAME,SIZE,MODEL,TRAN,MOUNTPOINTS
sudo umount /dev/sdX1 /dev/sdX2 /dev/sdX3 2>/dev/null || true
sudo dd if=install/soc_sg2002_tidesense_arm64_sd/tidesense-sdcard.img of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

不要把 `upgrade.zip` 或 `rawimages/*.sd` 直接 `dd` 到卡上：它们是升级包或单独的分区镜像，不是整卡镜像。

## 引脚与外设

- SD0：TF 卡 4-bit 总线；不启用 1.8 V UHS。`SD0_CD` 接地，卡座的 `SD0_DET` 没有接入 SoC，因此设备树不使用 GPIO 卡检测，需始终插入启动卡。
- 摄像头：I2C2 走 `PWR_GPIO1/2`，FSIN 走 `PWR_GPIO0`，两路 XSHUTDOWN 走 `PWR_WAKEUP0` 和 `PWR_BUTTON1`。
- OV9281：CVITEK sensor adapter 已加入，默认双路为 1280×800 RAW10 60fps。编译启用 `CONFIG_SENSOR_OV_OV9281=y`。SDK sample 从 `/mnt/data/sensor_cfg.ini` 读取双目配置；本目录的 `sensor_cfg.ini` 可复制到 SD 卡 DATA 分区的根目录。示例中两个 7-bit I²C 地址分别是 `0x60` 和 `0x70`，由于 SDK parser 使用 `atoi()`，配置值写十进制 `96` 和 `112`。lane 映射按 `pin.md` 中 U4/U12 的 MIPIRX 引脚填写；`hw_sync=1` 会设置 OV9281 外部 VSYNC 输入，实际 FSIN 脉冲需为 60 Hz。
- USB RNDIS：启动时在 USB1 Type-C 上启用 USB gadget 网卡，设备端地址固定为 `192.168.123.99/24`。主机设置为 `192.168.123.x/24`，例如 `192.168.123.100/24`。启用项为 `CONFIG_TARGET_PACKAGE_RNDIS_SCRIPT=y`。
- IMU：SPI2 走 `SD1_D3/D0/CMD/CLK`，中断走 `SD1_D1`；未连接的 `SD1_D2` 保持为 GPIO。
- 不配置 SPI NOR、SPI NAND、eMMC 或 MTD 闪存。Linux/U-Boot 的通用 SPI 控制器仍保留给 SPI2 IMU 总线。

## 尚需按实物确认

- `pin.md` 未给出 DRAM 容量。当前 `memmap.py` 沿用 SDK SG2002 ARM64 参考板的 256 MiB 地址布局；如果 TideSense 实物 DRAM 容量不同，必须同步修改此内存图及 DDR 初始化配置。
- ISP tuning 仍使用 SDK 默认值；产品成像质量需要后续标定。共享 FSIN 的双路同步配置已接入 CVITEK `hw_sync` 开关，但脉冲极性、相位和上板同步效果仍需实测。
- 源码中仍没有 SC7U22 驱动；IMU 运行需要单独加入对应 SPI 驱动。
- 原理图中 USB_VBUS_DET 固定接 1.8 V；板级初始化不把该脚改作 GPIO。`pin.md` 还标明 Type-C 的 CC1/CC2 未连接；请确认板上有适合设备模式的 Rd 电阻。否则 Type-C 对 Type-C 连接可能无法完成 attach，需用实际线缆验证。
