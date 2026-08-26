import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "mpos-gen-app-web" / "scripts" / "build_visual_asset.py"
PLAN_VALIDATOR = ROOT / "mpos-analyze-app-web" / "scripts" / "validate_visual_asset_plan.py"


class VisualAssetPipelineTests(unittest.TestCase):
    def _run(self, spec, directory, runtime_format="auto"):
        root = Path(directory)
        spec_path = root / "spec.json"
        preview_path = root / "preview.png"
        runtime_path = root / "runtime.bin"
        metadata_path = root / "metadata.json"
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--spec",
                str(spec_path),
                "--preview-output",
                str(preview_path),
                "--runtime-output",
                str(runtime_path),
                "--metadata-output",
                str(metadata_path),
                "--format",
                runtime_format,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return result, preview_path, runtime_path, metadata_path

    def _validate_plan(self, plan, directory, allow_external=False, allow_web=False):
        path = Path(directory) / "plan.json"
        path.write_text(json.dumps(plan), encoding="utf-8")
        command = [sys.executable, str(PLAN_VALIDATOR), "--input", str(path)]
        if allow_external:
            command.append("--allow-external")
        if allow_web:
            command.append("--allow-web")
        return subprocess.run(command, capture_output=True, text=True, check=False)

    def test_opaque_asset_is_deterministic_rgb565(self):
        spec = {
            "schema_version": "mpos-visual-asset-spec-v1",
            "id": "space_background",
            "width": 32,
            "height": 20,
            "background": "#081426",
            "supersample": 2,
            "shapes": [
                {
                    "type": "gradient",
                    "x": 0,
                    "y": 0,
                    "width": 32,
                    "height": 20,
                    "start_color": "#081426",
                    "end_color": "#34256f",
                    "direction": "vertical",
                },
                {
                    "type": "circle",
                    "cx": 9,
                    "cy": 7,
                    "radius": 3,
                    "color": "#f7d76b",
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result, preview, runtime, metadata = self._run(spec, directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(preview.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            payload = runtime.read_bytes()
            self.assertEqual(payload[0], 0x19)
            self.assertEqual(payload[1], 0x12)
            self.assertEqual(struct.unpack_from("<HHH", payload, 4), (32, 20, 64))
            self.assertEqual(len(payload), 12 + 32 * 20 * 2)
            record = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(record["runtime_format"], "RGB565")
            self.assertEqual(record["runtime_sha256"], hashlib.sha256(payload).hexdigest())

            first_preview_hash = hashlib.sha256(preview.read_bytes()).hexdigest()
            first_runtime_hash = hashlib.sha256(payload).hexdigest()
            result, preview, runtime, _ = self._run(spec, directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(hashlib.sha256(preview.read_bytes()).hexdigest(), first_preview_hash)
            self.assertEqual(hashlib.sha256(runtime.read_bytes()).hexdigest(), first_runtime_hash)

    def test_transparent_asset_uses_rgb565a8(self):
        spec = {
            "schema_version": "mpos-visual-asset-spec-v1",
            "id": "player_ship",
            "width": 16,
            "height": 12,
            "background": "#00000000",
            "shapes": [
                {
                    "type": "polygon",
                    "points": [[8, 0], [15, 11], [8, 8], [0, 11]],
                    "color": "#4fd1ffff",
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result, _, runtime, metadata = self._run(spec, directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = runtime.read_bytes()
            self.assertEqual(payload[1], 0x14)
            self.assertEqual(struct.unpack_from("<HHH", payload, 4), (16, 12, 32))
            self.assertEqual(len(payload), 12 + 16 * 12 * 3)
            record = json.loads(metadata.read_text(encoding="utf-8"))
            self.assertEqual(record["runtime_format"], "RGB565A8")
            self.assertTrue(record["has_alpha"])

    def test_a8_mask_and_rgb565_alpha_rejection(self):
        spec = {
            "schema_version": "mpos-visual-asset-spec-v1",
            "id": "status_mask",
            "width": 10,
            "height": 6,
            "background": "#00000000",
            "shapes": [
                {"type": "circle", "cx": 5, "cy": 3, "radius": 2, "color": "#ffffffff"}
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            result, _, runtime, metadata = self._run(spec, directory, runtime_format="A8")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = runtime.read_bytes()
            self.assertEqual(payload[1], 0x0E)
            self.assertEqual(struct.unpack_from("<HHH", payload, 4), (10, 6, 10))
            self.assertEqual(len(payload), 12 + 10 * 6)
            self.assertEqual(json.loads(metadata.read_text(encoding="utf-8"))["runtime_format"], "A8")

            result, _, _, _ = self._run(spec, directory, runtime_format="RGB565")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cannot preserve transparent pixels", result.stderr)

    def test_rejects_unknown_shapes_and_unsafe_ids(self):
        base = {
            "schema_version": "mpos-visual-asset-spec-v1",
            "id": "safe_name",
            "width": 8,
            "height": 8,
            "background": "#000000",
            "shapes": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            unknown = dict(base)
            unknown["shapes"] = [{"type": "python", "source": "import os"}]
            result, _, _, _ = self._run(unknown, directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsupported shape type", result.stderr)

            unsafe = dict(base)
            unsafe["id"] = "../escape"
            result, _, _, _ = self._run(unsafe, directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("invalid asset id", result.stderr)

    def test_rejects_asset_over_pixel_budget(self):
        spec = {
            "schema_version": "mpos-visual-asset-spec-v1",
            "id": "too_large",
            "width": 1024,
            "height": 1024,
            "background": "#000000",
            "shapes": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            result, _, _, _ = self._run(spec, directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("pixel budget", result.stderr)

    def test_web_skill_contracts_share_the_visual_asset_reference(self):
        required_skills = (
            "mpos-dev-web",
            "mpos-plan-app-web",
            "mpos-analyze-app-web",
            "mpos-prepare-deps-web",
            "mpos-gen-app-web",
            "mpos-test-app-web",
            "mpos-package-app-web",
        )
        for skill in required_skills:
            text = (ROOT / skill / "SKILL.md").read_text(encoding="utf-8")
            reference = "reference/visual_assets.md" if skill == "mpos-dev-web" else "mpos-dev-web/reference/visual_assets.md"
            self.assertIn(reference, text, skill)

        analyzer = (ROOT / "mpos-analyze-app-web" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Automatically classify requested visuals", analyzer)
        self.assertIn('"decision_mode": "automatic"', analyzer)

        artifacts = (ROOT / "mpos-dev-web" / "reference" / "artifact_manifest.md").read_text(encoding="utf-8")
        for role in (
            "visual_asset_spec",
            "visual_asset_source_record",
            "visual_asset_source",
            "app_runtime_image",
            "visual_asset_build_log",
        ):
            self.assertIn(role, artifacts)

        errors = (ROOT / "mpos-dev-web" / "reference" / "error_codes.md").read_text(encoding="utf-8")
        for code in (
            "VISUAL_ASSET_SPEC_INVALID",
            "VISUAL_ASSET_TOOLCHAIN_MISSING",
            "VISUAL_ASSET_BUILD_FAILED",
            "VISUAL_ASSET_BUDGET_EXCEEDED",
            "VISUAL_ASSET_LOAD_FAILED",
            "VISUAL_ASSET_SEARCH_FAILED",
            "VISUAL_ASSET_FETCH_FAILED",
            "VISUAL_ASSET_RIGHTS_UNVERIFIED",
        ):
            self.assertIn(code, errors)

        capabilities = (ROOT / "mpos-dev-web" / "reference" / "capabilities.md").read_text(encoding="utf-8")
        self.assertIn('"web_image_search": true', capabilities)
        self.assertIn('"remote_image_fetch": true', capabilities)

        visual_reference = (ROOT / "mpos-dev-web" / "reference" / "visual_assets.md").read_text(
            encoding="utf-8"
        )
        self.assertIn('"generation_mode": "web"', visual_reference)
        self.assertIn("visual_asset_source_record", visual_reference)
        self.assertNotIn("use my uploaded artwork", visual_reference)

        protocol = (ROOT / "mpos-dev-web" / "reference" / "protocol.md").read_text(encoding="utf-8")
        self.assertIn('"operation": "write_binary"', protocol)
        self.assertIn('"role": "app_runtime_image"', protocol)

    def test_automatic_plan_accepts_static_art_and_rejects_dynamic_raster(self):
        asset = {
            "id": "player_ship",
            "purpose": "game_sprite",
            "reason": "Detailed static artwork",
            "required": True,
            "dynamic": False,
            "interactive": False,
            "contains_text": False,
            "width": 32,
            "height": 24,
            "transparent": True,
            "generation_mode": "procedural",
            "fallback": "Show a colored LVGL polygon",
        }
        plan = {
            "schema_version": "mpos-visual-asset-plan-v1",
            "decision_mode": "automatic",
            "render_strategy": "hybrid",
            "assets": [asset],
            "lvgl_elements": ["score_label", "fire_button"],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = self._validate_plan(plan, directory)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["asset_count"], 1)

            dynamic_plan = json.loads(json.dumps(plan))
            dynamic_plan["assets"][0]["dynamic"] = True
            result = self._validate_plan(dynamic_plan, directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("must remain lvgl_native", result.stdout)

    def test_web_plan_requires_capability_and_rejects_uploaded_mode(self):
        asset = {
            "id": "named_character",
            "purpose": "character_artwork",
            "reason": "The user requested an exact recognizable character",
            "required": True,
            "dynamic": False,
            "interactive": False,
            "contains_text": False,
            "width": 160,
            "height": 160,
            "transparent": True,
            "generation_mode": "web",
            "search_query": "official named character transparent artwork",
            "fallback": "Show a generic native LVGL mascot",
        }
        plan = {
            "schema_version": "mpos-visual-asset-plan-v1",
            "decision_mode": "automatic",
            "render_strategy": "hybrid",
            "assets": [asset],
            "lvgl_elements": ["start_button"],
        }
        with tempfile.TemporaryDirectory() as directory:
            result = self._validate_plan(plan, directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("web image search and network_read capability", result.stdout)

            result = self._validate_plan(plan, directory, allow_web=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            normalized = json.loads(result.stdout)["assets"][0]
            self.assertEqual(normalized["generation_mode"], "web")
            self.assertEqual(normalized["search_query"], asset["search_query"])

            uploaded_plan = json.loads(json.dumps(plan))
            uploaded_plan["assets"][0]["generation_mode"] = "uploaded"
            del uploaded_plan["assets"][0]["search_query"]
            result = self._validate_plan(uploaded_plan, directory, allow_web=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("generation_mode is invalid", result.stdout)


if __name__ == "__main__":
    unittest.main()
