#!/usr/bin/env python3
"""Install the built TideSense applications into the SD partition trees."""

import argparse
import hashlib
import os
import shutil
from pathlib import Path

import yaml


SCHUR_PACKAGE = "schurvins-gcc11-static-micro-ros"
PACKAGES = {
    SCHUR_PACKAGE: (
        "bin/schurvins_stereo", "bin/schurvins_imu_test", "bin/prepare-imu.sh", "run.sh", "schurvins.yaml",
        "synthetic.yaml", "BUILD-INFO", "SHA256SUMS",
    ),
    "tidesense-dataset": (
        "bin/tidesense_record", "bin/prepare-imu.sh", "run.sh",
    ),
    "tidesense-uvc": (
        "bin/tidesense_uvc", "run.sh", "sensor_cfg.ini", "decode.py", "README.md", "VALIDATION.md",
    ),
    "tidesense-depth": (
        "bin/tidesense_depth", "bin/schurvins_camera", "bin/fsin.sh", "run.sh",
        "sensor_cfg.ini", "calibration.yaml", "receive.py", "README.md", "VALIDATION.md",
    ),
    "tidesense-vio-depth": (
        "bin/tidesense_vio_depth", "bin/schurvins_camera", "bin/fsin.sh", "bin/prepare-imu.sh",
        "run.sh", "sensor_cfg.ini", "calibration.yaml", "receive.py", "README.md", "BUILD-INFO", "SHA256SUMS",
    ),
    "perf": ("perf", "perf-smoke", "tips.txt", "COPYING-GPLV2", "COPYING-LGPLV3"),
}


VIO_PACKAGES = {
    "micro-ros": SCHUR_PACKAGE,
    "native-dds": "schurvins-gcc11-native-dds",
    "none": "schurvins-gcc11-static",
}


def packages_for_backend(backend):
    selected = VIO_PACKAGES[backend]
    packages = {selected if name == SCHUR_PACKAGE else name: files for name, files in PACKAGES.items()}
    if backend == "native-dds":
        packages[selected] += ("lib/ld-linux-aarch64.so.1", "lib/librcl.so", "lib/librmw_cyclonedds_cpp.so", "lib/libddsc.so.0", "cyclonedds.xml")
    return packages


def validate_apps(install_dir, backend="micro-ros"):
    for package, files in packages_for_backend(backend).items():
        for name in files:
            path = install_dir / package / name
            if not path.is_file():
                raise FileNotFoundError(f"Missing TideSense application: {path}; run build_tidesense_apps")
            if (name.startswith("bin/") or name in ("run.sh", "perf", "perf-smoke", "lib/ld-linux-aarch64.so.1")) and not os.access(path, os.X_OK):
                raise ValueError(f"Application is not executable: {path}")
    schur = install_dir / VIO_PACKAGES[backend]
    info = dict(line.split("=", 1) for line in (schur / "BUILD-INFO").read_text().splitlines() if "=" in line)
    if backend != "micro-ros" or "SCHUR_ROS_BACKEND" in info:
        if info.get("SCHUR_ROS_BACKEND") != backend:
            raise ValueError(f"{schur}/BUILD-INFO requires SCHUR_ROS_BACKEND={backend}")
    for key, expected in (("SCHUR_WITH_MICRO_ROS", "ON" if backend == "micro-ros" else "OFF"), ("IMU_INPUT_DOMAIN", "raw_si"),
                          ("IMU_INTRINSICS", "single_stage")):
        if info.get(key) != expected:
            raise ValueError(f"{schur}/BUILD-INFO requires {key}={expected}; rebuild the applications")
    checked = set()
    for line in (schur / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split(maxsplit=1)
        name = name.removeprefix("*")
        path = (schur / name).resolve()
        if not path.is_relative_to(schur.resolve()):
            raise ValueError(f"Invalid application checksum path: {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Application checksum mismatch: {path}")
        checked.add(name)
    if not {"bin/schurvins_stereo", "run.sh", "schurvins.yaml"} <= checked:
        raise ValueError("SchurVINS checksums must cover the program, launcher and calibration")
    if backend == "native-dds":
        runtime = {str(path.relative_to(schur)) for path in (schur / "lib").iterdir() if path.is_file()}
        if not runtime | {"cyclonedds.xml"} <= checked:
            raise ValueError("Native DDS checksums must cover the complete runtime and discovery config")
    config = yaml.safe_load((schur / "schurvins.yaml").read_text())
    imu = config.get("imu_params", {})
    if len(config.get("cameras", [])) != 2 or imu.get("input_domain") != "raw_si":
        raise ValueError("SchurVINS requires a full stereo calibration with raw_si IMU intrinsics")
    if config.get("imu_input_is_corrected", False):
        raise ValueError("The live calibration must accept uncorrected IMU samples")
    for name in ("accel_inverse_matrix", "gyro_inverse_matrix", "gyro_accel_matrix"):
        matrix = imu.get(name, [])
        if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
            raise ValueError(f"Missing or invalid unified IMU matrix: {name}")


def install_apps(install_dir, data_dir, rootfs_dir, backend="micro-ros"):
    validate_apps(install_dir, backend)
    data_dir.mkdir(parents=True, exist_ok=True)
    for package in packages_for_backend(backend):
        target = data_dir / package
        # Replace only generated application directories; leave user data alone.
        if target.is_symlink():
            target.unlink()
        elif target.exists():
            shutil.rmtree(target)
        shutil.copytree(install_dir / package, target, symlinks=True)
    binary_dir = rootfs_dir / "usr/bin"
    binary_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(install_dir / "perf/perf", binary_dir / "perf")
    tips_dir = rootfs_dir / "usr/share/doc/perf-tip"
    tips_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(install_dir / "perf/tips.txt", tips_dir / "tips.txt")
    init_dir = rootfs_dir / "etc/init.d"
    init_dir.mkdir(parents=True, exist_ok=True)
    priority_init = init_dir / "S21imu_priority"
    shutil.copy2(Path(__file__).parent / "rootfs_script/S21imu_priority", priority_init)
    priority_init.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--install-dir", type=Path, required=True)
    parser.add_argument("--ros-backend", choices=tuple(VIO_PACKAGES), default="micro-ros")
    args = parser.parse_args()
    install_dir = args.install_dir.resolve()
    install_apps(install_dir, install_dir / "data", install_dir / "rootfs", args.ros_backend)
    print(f"Installed SchurVINS ({args.ros_backend}), dataset recorder, UVC, stereo depth, joint VIO/depth and perf into {install_dir}")


if __name__ == "__main__":
    main()
