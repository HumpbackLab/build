# TideSense SG2002 ARM64 / SD 配置

选择 `sg2002_tidesense_arm64_sd` 编译。系统架构为 ARM64（CA53），启动和根文件系统都放在 TF/SD 卡上。SD 分区定义在 `partition/partition_sd.xml`。

```sh
source build/envsetup_soc.sh
defconfig sg2002_tidesense_arm64_sd
build_all
```

## 制作并烧录 SD 卡

`build_all` 在编译及升级包打包成功后，会自动生成按三分区布局制作的整卡镜像；镜像生成失败时，`build_all` 也会返回失败。如需单独重新打包，在工程根目录执行：

```sh
python3 build/boards/cv181x/sg2002_tidesense_arm64_sd/make_sdcard_image.py
```

默认构建包含 SchurVINS（强制 `SCHUR_WITH_MICRO_ROS=ON`）、独立 dataset 录制程序及 perf。
仅更新应用并重新制作整卡镜像，可在已有 SDK 构建产物的基础上执行：

```sh
source build/envsetup_soc.sh
defconfig sg2002_tidesense_arm64_sd
build_tidesense_apps
python3 build/boards/cv181x/sg2002_tidesense_arm64_sd/make_sdcard_image.py
```

应用安装到 `/mnt/data/schurvins-gcc11-static-micro-ros/`、`/mnt/data/tidesense-dataset/`
和 `/mnt/data/perf/`；系统命令为 `/usr/bin/perf`。`build_tidesense_apps` 会更新
`install/soc_sg2002_tidesense_arm64_sd/data/` 和 `rootfs/`，随后 `build_all` 将它们打包进分区和升级包。
单独制作整卡镜像时也会从应用产物刷新这三个目录，并校验 SchurVINS 的编译模式、校验和与单级补偿配置；缺件时返回失败。

主机需要 ROS 2 Humble 开发环境、Python venv/PyYAML、Boost 1.74 头文件及
perf 所需的 flex、bison、gettext 等工具；首次构建需要联网下载依赖。
默认 A53 配置启用已验证的 NEON 优化，保留各 `SCHUR_OPT_*` 环境变量覆盖。
micro-ROS 运行时通信仍默认关闭，需设置 Agent 地址后显式启用。
随包 `schurvins.yaml` 来自当前测试板的 640×400/20 Hz、曝光上限 0.5 ms 配置，使用原始 SI 单级 IMU 补偿；其它板卡需重新标定。

镜像路径为 `install/soc_sg2002_tidesense_arm64_sd/tidesense-sdcard.img`。脚本按 `partition_sd.xml` 创建 MBR 和 BOOT/ROOTFS/DATA 三个分区：BOOT 是 FAT32，内含 `fip.bin` 和 `boot.sd`；ROOTFS 是 ext4，卷标为小写 `rootfs` 以匹配 initramfs 的挂载脚本；DATA 是 ext4，并在系统启动时挂载到 `/mnt/data`。

首次启动会自动将 DATA 分区及 ext4 文件系统扩展至 SD 卡末尾，ROOTFS 保持 200 MiB。镜像生成时会自动构建所需的静态扩容工具（首次需要联网下载 e2fsprogs）；详见 SDK 根目录 `scripts/sd-grow/README.md`。

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
- OV9281：CVITEK sensor adapter 已加入，默认双路为 640×400 RAW10 20fps（全视场子采样），保留 640×400/60fps、640×480/60fps 居中裁切和 1280×800/60fps 模式。上板结果与切换方法见 SDK 根目录 `scripts/ov9281/README.md`。编译启用 `CONFIG_SENSOR_OV_OV9281=y`。SDK sample 从 `/mnt/data/sensor_cfg.ini` 读取双目配置；本目录的 `sensor_cfg.ini` 由整卡镜像脚本写入 DATA 分区根目录，也可复制到已运行设备的 `/mnt/data/sensor_cfg.ini`。左侧 U4 的 7-bit I²C 地址为 `0x10`（配置写十进制 `16`），右侧 U12 为 `0x60`（十进制 `96`）。CVITEK 的 `lane_id` 顺序为 CLK/D0/D1/D2/D3：左侧 RX0 使用 `0,1,2,-1,-1`（2 lane），右侧 RX1 使用 `3,4,-1,-1,-1`（1 lane）。适配层按各路 RX 配置选择传感器输出 lane 数，详情见 [OV9281 双目配置核查](OV9281-lanes.md)；`hw_sync=1` 启用 OV9281 单帧快照触发，由 PWR_GPIO0 复用 PWM8 向两颗相机输出 20Hz 脉冲；无脉冲不出图。触发模式内部 VTS=910、曝光上限 546 行；自由运行的 20fps 模式仍为 VTS=2730。整卡镜像打包 `/mnt/data/ov9281-update/fsin.sh`，具体启动顺序和验证见 SDK 根目录 `scripts/ov9281/README.md`。
- USB RNDIS：启动时在 USB1 Type-C 上启用 USB gadget 网卡，设备端地址固定为 `192.168.123.99/24`。主机设置为 `192.168.123.x/24`，例如 `192.168.123.100/24`。启用项为 `CONFIG_TARGET_PACKAGE_RNDIS_SCRIPT=y`。
- IMU：SPI2 走 `SD1_D3/D0/CMD/CLK`，中断走 `SD1_D1`；未连接的 `SD1_D2` 保持为 GPIO。
- perf：已启用 A53 PMU 硬件计数器和采样支持；运行 SDK 根目录的 `scripts/perf/build.sh` 构建工具，详见 `scripts/perf/README.md`。更换此内核时须同时更新匹配的内核与厂商 `.ko` 模块。
- 不配置 SPI NOR、SPI NAND、eMMC 或 MTD 闪存。Linux/U-Boot 的通用 SPI 控制器仍保留给 SPI2 IMU 总线。

## 尚需按实物确认

- `pin.md` 未给出 DRAM 容量。当前 `memmap.py` 沿用 SDK SG2002 ARM64 参考板的 256 MiB 地址布局；如果 TideSense 实物 DRAM 容量不同，必须同步修改此内存图及 DDR 初始化配置。
- ISP tuning 仍使用 SDK 默认值；产品成像质量需要后续标定。共享 FSIN 已上板验证 20Hz 一脉冲两路各一帧和停脉冲停出图；曝光同步精度仍需示波器等独立测量。
- SC7U22：已添加 SPI2 子设备及 spidev 支持，SDK 根目录的 `scripts/sc7u22/run.sh` 可进行用户态六轴/FIFO 测试。1 MHz 与 5 MHz 的上板测试通过，10 MHz 出现异常数据，默认使用 1 MHz；尚未接入正式 IIO 驱动或验证 IMU 中断。
- 原理图中 USB_VBUS_DET 固定接 1.8 V；板级初始化不把该脚改作 GPIO。`pin.md` 还标明 Type-C 的 CC1/CC2 未连接；请确认板上有适合设备模式的 Rd 电阻。否则 Type-C 对 Type-C 连接可能无法完成 attach，需用实际线缆验证。
