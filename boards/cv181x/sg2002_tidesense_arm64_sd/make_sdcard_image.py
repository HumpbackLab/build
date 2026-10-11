#!/usr/bin/env python3
"""Create a bootable three-partition TideSense SD card image."""

import argparse
import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


BOARD_DIR = Path(__file__).resolve().parent
REPO_DIR = BOARD_DIR.parents[3]
PARTITION_XML = BOARD_DIR / "partition" / "partition_sd.xml"
DEFAULT_INSTALL_DIR = REPO_DIR / "install" / "soc_sg2002_tidesense_arm64_sd"
SECTOR_SIZE = 512
ALIGN_SECTORS = 2048

DATA_MOUNT_SCRIPT = """#!/bin/sh
${CVI_SHOPTS}
case "$1" in
  start)
    mkdir -p /mnt/data
    n=0
    while [ ! -b /dev/mmcblk0p3 ] && [ "$n" -lt 10 ]; do
      sleep 1
      n=$((n + 1))
    done
    if [ -b /dev/mmcblk0p3 ]; then
      /sbin/auto-grow-data || echo "TideSense DATA expansion failed; retry next boot"
      # Buffered writes keep VIO logging from blocking on every SD write.
      mount -t ext4 -o rw,async /dev/mmcblk0p3 /mnt/data
    else
      echo "TideSense DATA partition /dev/mmcblk0p3 is unavailable"
    fi
    ;;
  stop)
    umount /mnt/data
    ;;
esac
exit $?
"""


def run(*args):
    print("+", " ".join(map(str, args)), flush=True)
    subprocess.run(args, check=True)


def repair_ext4(path):
    e2fsck = find_tool("e2fsck")
    print("+", e2fsck, "-fy", path, flush=True)
    result = subprocess.run((e2fsck, "-fy", str(path)))
    # e2fsck returns 1 when it made the padding-bit repair emitted by this
    # SDK's make_ext4fs; 0 means no repairs were needed.
    if result.returncode not in (0, 1):
        raise subprocess.CalledProcessError(result.returncode, (e2fsck, "-fy", str(path)))


def find_tool(name, fallback=None):
    found = shutil.which(name)
    if found:
        return found
    if fallback and fallback.is_file():
        return str(fallback)
    raise FileNotFoundError(f"Required tool not found: {name}")


def read_partitions():
    root = ET.parse(PARTITION_XML).getroot()
    if root.attrib.get("type") != "sd":
        raise ValueError(f"Expected SD partition layout in {PARTITION_XML}")
    parts = []
    for node in root.findall("partition"):
        size_kib = node.attrib.get("size_in_kb")
        if size_kib is None:
            raise ValueError(f"Missing size_in_kb for {node.attrib.get('label')}")
        size_bytes = int(size_kib) * 1024
        if size_bytes % SECTOR_SIZE:
            raise ValueError(f"Partition {node.attrib['label']} is not sector aligned")
        parts.append(
            {
                "label": node.attrib["label"],
                "file": node.attrib["file"],
                "size_bytes": size_bytes,
                "size_sectors": size_bytes // SECTOR_SIZE,
            }
        )
    if [p["label"] for p in parts] != ["BOOT", "ROOTFS", "DATA"]:
        raise ValueError("Expected BOOT, ROOTFS, DATA partitions in that order")
    return parts


def mbr_entry(status, partition_type, start_sector, size_sectors):
    # Saturated CHS values are standard for LBA-addressed MBR partitions.
    chs = b"\xfe\xff\xff"
    return struct.pack(
        "<B3sB3sII",
        status,
        chs,
        partition_type,
        chs,
        start_sector,
        size_sectors,
    )


def make_mbr(parts, total_sectors):
    mbr = bytearray(SECTOR_SIZE)
    mbr[440:444] = os.urandom(4)  # Disk signature.
    entries = bytearray()
    partition_types = (0x0C, 0x83, 0x83)  # FAT32 LBA, Linux, Linux.
    cursor = ALIGN_SECTORS
    for i, (part, ptype) in enumerate(zip(parts, partition_types)):
        start = ((cursor + ALIGN_SECTORS - 1) // ALIGN_SECTORS) * ALIGN_SECTORS
        part["start_sector"] = start
        entries.extend(
            mbr_entry(0x80 if i == 0 else 0, ptype, start, part["size_sectors"])
        )
        cursor = start + part["size_sectors"]
    if cursor != total_sectors:
        raise ValueError("Internal error calculating image size")
    mbr[446 : 446 + len(entries)] = entries
    mbr[510:512] = b"\x55\xaa"
    return bytes(mbr)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--install-dir", type=Path, default=DEFAULT_INSTALL_DIR,
        help="build output directory (default: %(default)s)",
    )
    parser.add_argument(
        "--output", type=Path, help="output .img path (default: <install-dir>/tidesense-sdcard.img)",
    )
    args = parser.parse_args()

    install_dir = args.install_dir.resolve()
    output = (args.output or install_dir / "tidesense-sdcard.img").resolve()
    rootfs_dir = install_dir / "rootfs"
    data_dir = install_dir / "data"
    fip = install_dir / "fip.bin"
    boot = install_dir / "rawimages" / "boot.sd"
    for required in (rootfs_dir, data_dir, fip, boot):
        if not required.exists():
            raise FileNotFoundError(f"Build output is missing: {required}")

    parts = read_partitions()
    # Calculate aligned offsets before constructing the MBR.
    cursor = ALIGN_SECTORS
    for part in parts:
        start = ((cursor + ALIGN_SECTORS - 1) // ALIGN_SECTORS) * ALIGN_SECTORS
        part["start_sector"] = start
        cursor = start + part["size_sectors"]
    total_sectors = cursor
    mbr = make_mbr(parts, total_sectors)

    mkfs_vfat = find_tool("mkfs.vfat")
    mcopy = find_tool("mcopy")
    make_ext4fs = find_tool(
        "make_ext4fs", REPO_DIR / "build" / "tools" / "common" / "prebuild" / "make_ext4fs"
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    run("bash", str(REPO_DIR / "scripts/sd-grow/build.sh"))
    with tempfile.TemporaryDirectory(prefix="tidesense-sd-") as temp_name:
        temp = Path(temp_name)
        boot_fs = temp / "boot.fat"
        rootfs_fs = temp / "rootfs.ext4"
        data_fs = temp / "data.ext4"
        staged_rootfs = temp / "rootfs"
        staged_data = temp / "data"

        boot_fs.touch()
        boot_fs.open("r+b").truncate(parts[0]["size_bytes"])
        run(mkfs_vfat, "-F", "32", "-s", "2", "-n", "BOOT", str(boot_fs))
        run(mcopy, "-o", "-i", str(boot_fs), str(fip), "::/fip.bin")
        run(mcopy, "-o", "-i", str(boot_fs), str(boot), "::/boot.sd")

        shutil.copytree(rootfs_dir, staged_rootfs, symlinks=True)
        for name in ("tidesense-grow-data", "resize2fs", "e2fsck"):
            shutil.copy2(REPO_DIR / "install/tidesense-grow" / name,
                         staged_rootfs / "sbin" / name)
        shutil.copy2(REPO_DIR / "scripts/sd-grow/auto-grow-data",
                     staged_rootfs / "sbin/auto-grow-data")
        license_dir = staged_rootfs / "usr/share/licenses/e2fsprogs"
        license_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(REPO_DIR / "install/tidesense-grow/e2fsprogs-1.47.2/NOTICE",
                     license_dir / "NOTICE")
        mount_script = staged_rootfs / "etc" / "init.d" / "S10auto_mount"
        mount_script.write_text(DATA_MOUNT_SCRIPT)
        mount_script.chmod(0o755)

        shutil.copytree(data_dir, staged_data, symlinks=True)
        shutil.copy2(BOARD_DIR / "sensor_cfg.ini", staged_data / "sensor_cfg.ini")
        fsin_dir = staged_data / "ov9281-update"
        fsin_dir.mkdir(exist_ok=True)
        shutil.copy2(REPO_DIR / "scripts/ov9281/fsin.sh", fsin_dir / "fsin.sh")

        rootfs_size_mib = parts[1]["size_bytes"] // (1024 * 1024)
        data_size_mib = parts[2]["size_bytes"] // (1024 * 1024)
        run(
            make_ext4fs, "-l", f"{rootfs_size_mib}M", "-L", "rootfs",
            str(rootfs_fs), str(staged_rootfs),
        )
        repair_ext4(rootfs_fs)
        run(
            make_ext4fs, "-l", f"{data_size_mib}M", "-L", "DATA",
            str(data_fs), str(staged_data),
        )
        repair_ext4(data_fs)

        with output.open("wb") as image:
            image.truncate(total_sectors * SECTOR_SIZE)
            image.seek(0)
            image.write(mbr)
            for part, source in zip(parts, (boot_fs, rootfs_fs, data_fs)):
                image.seek(part["start_sector"] * SECTOR_SIZE)
                with source.open("rb") as stream:
                    shutil.copyfileobj(stream, image, length=1024 * 1024)

    print("Partitions:")
    for part in parts:
        print(
            f"  {part['label']}: start={part['start_sector']} sectors, "
            f"size={part['size_bytes'] // (1024 * 1024)} MiB"
        )
    print(f"Image: {output} ({output.stat().st_size} bytes)")
    print(f"SHA256: {sha256(output)}")


if __name__ == "__main__":
    main()
