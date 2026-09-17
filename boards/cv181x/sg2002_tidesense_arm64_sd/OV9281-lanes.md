# OV9281 双目 MIPI 配置核查

核查日期：2026-09-17。目标板：TideSense，192.168.123.99。

## 最终配置

| 项目 | 左侧 U4 | 右侧 U12 |
| --- | --- | --- |
| I2C2 的 7-bit 地址 | 0x10 | 0x60 |
| sensor_cfg.ini 十进制地址 | 16 | 96 |
| CVITEK RX dev / ViPipe | 0 / 0 | 1 / 1 |
| 数据 lane 数 | 2 | 1 |
| lane_id（CLK/D0/D1/D2/D3） | 0,1,2,-1,-1 | 3,4,-1,-1,-1 |
| PN swap | 全部 0 | 全部 0 |
| 0x3039 | 0x32 | 0x32 |
| 0x3662（RAW10 lane 配置） | 0x05 | 0x01 |
| 0x303a | 0x00 | 0x00 |
| 0x030d（RAW10 PLL） | 0x50 | 0x50 |
| HTS 0x380c/d | 0x05b0 = 1456 | 0x05b0 = 1456 |
| VTS 0x380e/f | 0x038e = 910 | 0x038e = 910 |

CVITEK 将 lane_id[0] 作为时钟，后面的有效项作为数据 lane；不能把时钟放在数组中间。SoC RX0 对应 MIPIRX0/1/2，RX1 对应 MIPIRX3/4，符合 pin.md。

## 传感器寄存器依据

原先初始化固定使用两路 RAW10 的 0x3662=0x05，板级 INI 地址为 0x60/0x70，CLK/DATA 顺序也不正确。

虽然本地数据手册将 0x3039[7:5] 描述为 lane 数，但直接将右侧改成 0x12、仍保留 0x3662=0x05，上板出现 ECC 错误，不能正确解码 RAW10。左侧切到相同单 lane 设置也复现。

最终采用 ArduCAM 官方仓库的单/双 lane RAW10 配置差异：0x3039 均为 0x32，0x3662 分别为 0x01/0x05。不能仅凭 0x3039=0x32 判断实际输出为双 lane。

来源：[单 lane RAW10 配置](https://github.com/ArduCAM/ArduCAM_USB_Camera_Shield/blob/master/Config/USB3.0_UC-593%20Rev.C/MIPI/OV9281/Channel_A/1Lane/OV9281_MIPI_1Lane_RAW10_10b_1280x800_40fps.cfg)、[双 lane RAW10 配置](https://github.com/ArduCAM/ArduCAM_USB_Camera_Shield/blob/master/Config/USB3.0_UC-593%20Rev.C/MIPI/OV9281/Channel_A/2Lane/OV9281_MIPI_2Lane_RAW10_10b_1280x800_40fps.cfg)。厂商配置注释明确列出 RAW10 单 lane=0x01、双 lane=0x05。

HTS/VTS 使用厂商 [单 lane 60fps 配置](https://github.com/ArduCAM/ArduCAM_USB_Camera_Shield/blob/master/Config/USB3.0_UC-425_Rev.C%2BUC-489%20Rev.C/OV9281/OV9281_MIPI_1Lane_RAW10_10b_1280x800_60fps.cfg) 的 1456/910。原来的 728/1820 虽然总周期相同，但行周期不适合单 lane 的发送带宽。两颗采用同样行/帧周期，AE 默认 VTS 和最大曝光行数同步改为 910/885。60fps 为 24MHz 输入下的标称值，未测量实际帧率。

## 上板验证

使用实际 ov9281_cmos.c/ov9281_sensor_ctl.c 构建独立诊断程序，读取板级 INI 的地址和 lane 映射，将两路配置通过 CVI_MIPI_SET_DEV_ATTR 送入接收驱动，然后初始化两颗传感器。

- 两个地址均读到 chip ID 0x9281。
- 上表关键寄存器全部回读一致，AE VTS/曝光上限一致。
- 自由运行 10 秒后，两路均解码为 RAW10；ECC、CRC、包头、字数和 FIFO 错误均为 0。原始结果见 OV9281-lanes-test.log。
- 测试结束将两颗传感器置于待机。生产 INI 保持 hw_sync=1，外部 FSIN 同步、完整帧抓取和实际帧率尚未验证。

SDK 的 /proc/mipi-rx PHY 状态显示存在位域错位：cif_get_csi_phy_state 将 DBG_90 与 DBG_94<<16 合并，而 mipi_phy_state 的数据位从 bit8 开始，右路时钟又读取 bit4。PHY 2L/4L 寄存器定义中 CK_HS 实际均为 DBG_90 bit0。此次直接读右路 DBG_90（0x0a0d0690）为 0x1，时钟在 HS；因此不要将 proc 中右路 CK_HS=0/CK_ULPS=1 当作实测时钟状态。此次未修改这个通用内核显示问题。

## 编译与部署范围

build_middleware 已完成，生成 libsns_ov9281.so/.a 及 SDK samples。本次没有重制整卡镜像；目标板 /mnt/data/sensor_cfg.ini 更新为本目录配置，新动态库另存于 /mnt/data/ov9281-update/libsns_ov9281.so。已有静态链接的相机应用须重新链接后部署才能使用新初始化逻辑。
