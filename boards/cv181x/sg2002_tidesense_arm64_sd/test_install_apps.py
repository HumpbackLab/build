#!/usr/bin/env python3
"""Check image application installation and SDK build ordering without compiling."""

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from install_apps import PACKAGES, SCHUR_PACKAGE, install_apps


REPO = Path(__file__).resolve().parents[4]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for package, names in PACKAGES.items():
            for name in names:
                path = self.root / package / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test application\n")
                path.chmod(0o755)
        schur = self.root / SCHUR_PACKAGE
        (schur / "BUILD-INFO").write_text(
            "SCHUR_WITH_MICRO_ROS=ON\nIMU_INPUT_DOMAIN=raw_si\nIMU_INTRINSICS=single_stage\n")
        (schur / "schurvins.yaml").write_text((REPO / "scripts/schurvins/tidesense.yaml").read_text())
        self.checksums()

    def checksums(self):
        schur = self.root / SCHUR_PACKAGE
        (schur / "SHA256SUMS").write_text("".join(
            f"{hashlib.sha256((schur / name).read_bytes()).hexdigest()}  {name}\n"
            for name in ("bin/schurvins_stereo", "run.sh", "schurvins.yaml")))

    def stage(self):
        install_apps(self.root, self.root / "data", self.root / "rootfs")

    def test_packages_and_perf_installed_and_stale_files_removed(self):
        self.stage()
        stale = self.root / "data" / SCHUR_PACKAGE / "obsolete"
        stale.touch()
        user_data = self.root / "data/dataset-example"
        user_data.mkdir()
        self.stage()
        self.assertFalse(stale.exists())
        self.assertTrue(user_data.is_dir())
        for package, names in PACKAGES.items():
            for name in names:
                self.assertEqual((self.root / package / name).read_bytes(),
                                 (self.root / "data" / package / name).read_bytes())
        self.assertEqual((self.root / "perf/perf").read_bytes(),
                         (self.root / "rootfs/usr/bin/perf").read_bytes())

    def test_missing_recorder_fails_before_changing_data(self):
        (self.root / "tidesense-dataset/bin/tidesense_record").unlink()
        with self.assertRaises(FileNotFoundError):
            self.stage()
        self.assertFalse((self.root / "data").exists())

    def test_rejects_non_micro_ros_build(self):
        (self.root / SCHUR_PACKAGE / "BUILD-INFO").write_text("SCHUR_WITH_MICRO_ROS=OFF\n")
        with self.assertRaisesRegex(ValueError, "SCHUR_WITH_MICRO_ROS=ON"):
            self.stage()

    def test_rejects_modified_calibration(self):
        with (self.root / SCHUR_PACKAGE / "schurvins.yaml").open("a") as stream:
            stream.write("# changed after packaging\n")
        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.stage()

    def test_rejects_legacy_imu_domain(self):
        path = self.root / SCHUR_PACKAGE / "schurvins.yaml"
        config = yaml.safe_load(path.read_text())
        del config["imu_params"]["input_domain"]
        path.write_text(yaml.safe_dump(config))
        self.checksums()
        with self.assertRaisesRegex(ValueError, "raw_si"):
            self.stage()


class BuildOrderTests(unittest.TestCase):
    def test_application_build_forces_micro_ros_on_and_orders_dependencies(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in ("schurvins", "dataset", "uvc", "depth", "vio-depth", "perf"):
                path = root / "scripts" / name / "build.sh"
                path.parent.mkdir(parents=True)
                path.write_text(f'#!/bin/sh\necho "{name}:$SCHUR_WITH_MICRO_ROS"\n')
                path.chmod(0o755)
            script = ('source build/envsetup_soc.sh >/dev/null\n'
                      f'TOP_DIR={temp}\nOUTPUT_DIR={temp}/install\n'
                      'PROJECT_FULLNAME=sg2002_tidesense_arm64_sd\n'
                      'SCHUR_WITH_MICRO_ROS=OFF\n'
                      'python3() { echo install; }\nbuild_tidesense_apps\n')
            result = subprocess.run(["bash", "-c", script], cwd=REPO, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), ["schurvins:ON", "dataset:ON", "uvc:ON", "depth:ON", "vio-depth:ON", "perf:ON", "install"])

    def run_build(self, project="sg2002_tidesense_arm64_sd", failure=0):
        steps = ("build_uboot build_kernel build_ramboot build_osdrv build_3rd_party "
                 "build_middleware build_cvi_rtsp build_tpu_sdk build_pqtool_server "
                 "pack_cfg pack_rootfs pack_data pack_system copy_tools pack_upgrade").split()
        script = 'source build/envsetup_soc.sh >/dev/null\n'
        for name in steps:
            script += f'{name}() {{ echo {name}; }}\n'
        script += f'build_tidesense_apps() {{ echo apps; return {failure}; }}\n'
        script += 'python3() { echo image; }\n'
        script += f'PROJECT_FULLNAME={project}\nBOARD=test\nTPU_REL=0\nbuild_all\n'
        return subprocess.run(["bash", "-c", script], cwd=REPO, text=True, capture_output=True)

    def test_apps_before_both_partitions_and_image_last(self):
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stderr)
        steps = result.stdout.splitlines()
        self.assertLess(steps.index("apps"), steps.index("pack_rootfs"))
        self.assertLess(steps.index("apps"), steps.index("pack_data"))
        self.assertEqual(steps[-1], "image")

    def test_failed_application_build_stops_packaging(self):
        result = self.run_build(failure=23)
        self.assertEqual(result.returncode, 23)
        self.assertNotIn("pack_rootfs", result.stdout)
        self.assertNotIn("image", result.stdout)

    def test_other_boards_do_not_build_tidesense_apps(self):
        result = self.run_build(project="sg2002_wevb_arm64_sd")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("apps", result.stdout)
        self.assertNotIn("image", result.stdout)


if __name__ == "__main__":
    unittest.main()
