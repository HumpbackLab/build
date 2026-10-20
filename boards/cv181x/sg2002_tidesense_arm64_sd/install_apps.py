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
        "bin/schurvins_stereo", "bin/schurvins_camera", "bin/schurvins_imu_test",
        "bin/fsin.sh", "bin/prepare-imu.sh", "run.sh", "schurvins.yaml",
        "synthetic.yaml", "BUILD-INFO", "SHA256SUMS",
    ),
    "tidesense-dataset": (
        "bin/tidesense_record", "bin/schurvins_camera", "bin/fsin.sh",
        "bin/prepare-imu.sh", "run.sh",
    ),
    "perf": ("perf", "perf-smoke", "tips.txt", "COPYING-GPLV2", "COPYING-LGPLV3"),
}


def validate_apps(install_dir):
    for package, files in PACKAGES.items():
        for name in files:
            path = install_dir / package / name
            if not path.is_file():
                raise FileNotFoundError(f"Missing TideSense application: {path}; run build_tidesense_apps")
            if (name.startswith("bin/") or name in ("run.sh", "perf", "perf-smoke")) and not os.access(path, os.X_OK):
                raise ValueError(f"Application is not executable: {path}")
    schur = install_dir / SCHUR_PACKAGE
    info = dict(line.split("=", 1) for line in (schur / "BUILD-INFO").read_text().splitlines() if "=" in line)
    for key, expected in (("SCHUR_WITH_MICRO_ROS", "ON"), ("IMU_INPUT_DOMAIN", "raw_si"),
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


def install_apps(install_dir, data_dir, rootfs_dir):
    validate_apps(install_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    for package in PACKAGES:
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
    args = parser.parse_args()
    install_dir = args.install_dir.resolve()
    install_apps(install_dir, install_dir / "data", install_dir / "rootfs")
    print(f"Installed SchurVINS (micro-ROS), dataset recorder and perf into {install_dir}")


if __name__ == "__main__":
    main()
