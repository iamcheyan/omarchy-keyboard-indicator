"""Offline unit tests for the four-state machine in scripts/ctrl_swap.py.

No root, no keyd, no Hyprland: every privileged or external side effect is
replaced with a recorder. The tests pin the observable contract:

* exactly one keyd config per (swap, voice) combination,
* configs without the schema marker count as drift,
* sync() runs preconditions -> machine -> state files, so a failure can
  never leave the switch files claiming an applied state,
* voice-on installs its bind before keyd flips the mapping,
* enable()/disable() are thin wrappers around sync().
"""

from __future__ import annotations

import json
import inspect
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "scripts"))

import ctrl_swap  # noqa: E402


class FourStateTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="four-state-test-")
        base = pathlib.Path(self.tmp.name)
        self.state_dir = base / "state"
        self.state_dir.mkdir()
        self.keyd_dest = base / "hancore-ctrl-swap.conf"
        patchers = [
            mock.patch.object(ctrl_swap, "STATE_DIR", self.state_dir),
            mock.patch.object(ctrl_swap, "STATE_FILE", self.state_dir / "enabled"),
            mock.patch.object(ctrl_swap, "VOICE_STATE_FILE", self.state_dir / "voice_enabled"),
            mock.patch.object(ctrl_swap, "KEYD_DEST", self.keyd_dest),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def tearDown(self) -> None:
        self.tmp.cleanup()


class ConfigMatrixTest(FourStateTestBase):
    def test_keyd_source_requires_a_full_commit_and_never_clones_head(self):
        self.assertEqual(ctrl_swap.pinned_keyd_commit(), ctrl_swap.KEYD_COMMIT)
        source = inspect.getsource(ctrl_swap.ensure_keyd_installed)
        self.assertNotIn('"clone"', source)
        self.assertIn('"fetch"', source)
        self.assertIn("pinned_keyd_commit", source)

        with mock.patch.object(ctrl_swap, "KEYD_COMMIT", "main"):
            with self.assertRaisesRegex(RuntimeError, "40-character commit SHA"):
                ctrl_swap.pinned_keyd_commit()

    def test_exact_configs_for_all_four_states(self):
        expected = {
            (False, True): "capslock = f24\n",
            (True, False): "capslock = layer(control)\nleftcontrol = capslock\n",
            (True, True): "capslock = overload(control, f24)\nleftcontrol = capslock\n",
        }
        for (swap, voice), mapping in expected.items():
            config = ctrl_swap.keyd_config(swap, voice)
            self.assertIn(f"# schema: {ctrl_swap.CONFIG_SCHEMA}\n", config)
            self.assertTrue(
                config.endswith(f"[main]\n{mapping}"),
                f"unexpected body for swap={swap} voice={voice}: {config!r}",
            )
        # the three mapped states must produce three distinct bodies, and the
        # neutral state must produce no file at all
        bodies = {ctrl_swap.keyd_config(s, v) for s, v in expected}
        self.assertEqual(len(bodies), 3)
        self.assertIsNone(ctrl_swap.keyd_config(False, False))

    def test_neutral_state_is_the_absence_of_our_file(self):
        # keyd picks one config per device and ours sorts after a
        # hand-written default.conf, so an installed identity mapping would
        # void the user's own keyboard config instead of being a no-op.
        self.assertFalse(self.keyd_dest.exists())
        self.assertTrue(ctrl_swap.keyd_config_matches(False, False))
        self.keyd_dest.write_text(ctrl_swap.keyd_config(True, False))
        self.assertFalse(ctrl_swap.keyd_config_matches(False, False))

    def test_neutral_state_does_not_require_keyd_to_be_running(self):
        with mock.patch.object(ctrl_swap, "_keyd_is_active", return_value=False):
            self.assertTrue(ctrl_swap.remap_is_live(False, False))
            self.keyd_dest.write_text(ctrl_swap.keyd_config(False, True))
            self.assertFalse(ctrl_swap.remap_is_live(False, True))

    def test_matches_requires_schema_marker(self):
        good = ctrl_swap.keyd_config(False, True)
        body_only = "\n".join(
            line for line in good.splitlines() if "# schema:" not in line
        ) + "\n"
        for content, want in ((good, True), (body_only, False)):
            self.keyd_dest.write_text(content)
            self.assertEqual(ctrl_swap.keyd_config_matches(False, True), want, content)
        self.assertFalse(ctrl_swap.keyd_config_matches(False, True))  # missing file

    def test_matches_ignores_comments(self):
        good = ctrl_swap.keyd_config(True, False)
        noisy = good.replace("[ids]", "# someone edited here\n[ids]")
        self.keyd_dest.write_text(noisy)
        self.assertTrue(ctrl_swap.keyd_config_matches(True, False))


class SyncOrderTest(FourStateTestBase):
    def setUp(self):
        super().setUp()
        self.calls: list[str] = []
        patchers = [
            mock.patch.object(
                ctrl_swap, "install_voice_binds",
                side_effect=lambda: self.calls.append("install"),
            ),
            mock.patch.object(
                ctrl_swap, "_apply_keyd_unlocked",
                side_effect=lambda s, v, *, force: self.calls.append(f"apply({s},{v})"),
            ),
            mock.patch.object(
                ctrl_swap, "remove_owned_voice_bindings",
                side_effect=lambda: self.calls.append("remove"),
            ),
        ]
        for patcher in patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_voice_on_binds_first_ledger_last(self):
        ctrl_swap._sync_unlocked(False, True, force=True)
        self.assertEqual(self.calls, ["install", "apply(False,True)"])
        self.assertTrue((self.state_dir / "voice_enabled").exists())
        self.assertFalse((self.state_dir / "enabled").exists())  # swap ledger off

    def test_missing_voxtype_blocks_before_any_change(self):
        with mock.patch.object(ctrl_swap.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "Voxtype"):
                ctrl_swap._sync_unlocked(True, True, force=True)
        self.assertEqual(self.calls, [])
        self.assertFalse((self.state_dir / "voice_enabled").exists())
        self.assertFalse((self.state_dir / "enabled").exists())

    def test_failed_keyd_step_never_writes_the_ledger(self):
        self.calls.clear()
        with mock.patch.object(
            ctrl_swap, "_apply_keyd_unlocked",
            side_effect=RuntimeError("denied"),
        ):
            with self.assertRaisesRegex(RuntimeError, "denied"):
                ctrl_swap._sync_unlocked(False, True, force=True)
        self.assertFalse((self.state_dir / "voice_enabled").exists())

    def test_voice_off_stops_emitter_then_removes_bind(self):
        (self.state_dir / "voice_enabled").write_text("1\n")
        (self.state_dir / "enabled").write_text("1\n")
        ctrl_swap._sync_unlocked(True, False, force=True)
        self.assertEqual(self.calls, ["apply(True,False)", "remove"])
        self.assertFalse((self.state_dir / "voice_enabled").exists())
        self.assertTrue((self.state_dir / "enabled").exists())

    def test_enable_passes_current_voice_state_with_force(self):
        (self.state_dir / "voice_enabled").write_text("1\n")
        with mock.patch.object(ctrl_swap, "sync") as sync_mock, \
             mock.patch.object(ctrl_swap, "clear_legacy_xkb_swap"):
            ctrl_swap.enable()
        sync_mock.assert_called_once_with(True, True, force=True)

    def test_disable_passes_current_voice_state_with_force(self):
        with mock.patch.object(ctrl_swap, "sync") as sync_mock:
            ctrl_swap.disable()
        sync_mock.assert_called_once_with(False, False, force=True)


class ApplyKeydTest(FourStateTestBase):
    def test_neutral_apply_removes_the_file_instead_of_installing_one(self):
        self.keyd_dest.write_text(ctrl_swap.keyd_config(True, False))
        with mock.patch.object(
            ctrl_swap, "root_command",
            side_effect=lambda *a, **kw: self.keyd_dest.unlink(missing_ok=True),
        ) as root, \
             mock.patch.object(ctrl_swap, "ensure_keyd_installed") as install, \
             mock.patch.object(ctrl_swap, "_keyd_unit_busy", return_value=True):
            ctrl_swap._apply_keyd_unlocked(False, False, force=True)
        install.assert_not_called()
        root.assert_called_once_with(
            remove=(str(self.keyd_dest),), restart=True
        )
        self.assertFalse(self.keyd_dest.exists())

    def test_neutral_apply_skips_the_pkexec_prompt_when_nothing_to_remove(self):
        with mock.patch.object(ctrl_swap, "root_command") as root, \
             mock.patch.object(ctrl_swap, "ensure_keyd_installed") as install:
            ctrl_swap._apply_keyd_unlocked(False, False, force=True)
        root.assert_not_called()
        install.assert_not_called()

    def test_mapped_apply_still_installs_the_config(self):
        with mock.patch.object(
            ctrl_swap, "root_command",
            side_effect=lambda files=None, **kw: self.keyd_dest.write_bytes(
                next(iter(files.values()))
            ),
        ) as root, \
             mock.patch.object(ctrl_swap, "ensure_keyd_installed", return_value=False), \
             mock.patch.object(ctrl_swap, "_keyd_is_active", return_value=True):
            ctrl_swap._apply_keyd_unlocked(True, False, force=True)
        root.assert_called_once()
        self.assertIn("capslock = layer(control)", self.keyd_dest.read_text())


class VoiceBindTest(FourStateTestBase):
    def _patch_owned(self, owned):
        return mock.patch.object(ctrl_swap, "_owned_voice_binds", return_value=owned)

    def test_install_skips_when_exactly_one_correct_bind_exists(self):
        owned = [{"key": "F24", "release": True,
                  "description": ctrl_swap.VOICE_DESCRIPTION}]
        with self._patch_owned(owned), \
             mock.patch.object(ctrl_swap, "eval_lua") as eval_mock:
            ctrl_swap.install_voice_binds()
        eval_mock.assert_not_called()

    def test_install_rebuilds_on_ghost_duplicates(self):
        owned = [
            {"key": "F24", "release": True, "description": ctrl_swap.VOICE_DESCRIPTION},
            {"key": "", "release": True, "description": ctrl_swap.VOICE_DESCRIPTION},
        ]
        with self._patch_owned(owned), \
             mock.patch.object(ctrl_swap, "remove_owned_voice_bindings") as rm, \
             mock.patch.object(ctrl_swap, "eval_lua") as eval_mock:
            ctrl_swap.install_voice_binds()
        rm.assert_called_once()
        eval_mock.assert_called_once()

    def test_remove_unbinds_observed_keys_plus_legacy_list(self):
        owned = [{"key": "code:58", "description": ctrl_swap.LEGACY_VOICE_DESCRIPTION}]
        with self._patch_owned(owned), \
             mock.patch.object(ctrl_swap, "eval_lua") as eval_mock:
            ctrl_swap.remove_owned_voice_bindings()
        lua = eval_mock.call_args[0][0]
        for token in ("code:58", "F24", "Caps_Lock", "Multi_key", "code:66"):
            self.assertIn(f'hl.unbind("{token}")', lua)

    def test_remove_noop_without_owned_binds(self):
        with self._patch_owned([]), \
             mock.patch.object(ctrl_swap, "eval_lua") as eval_mock:
            ctrl_swap.remove_owned_voice_bindings()
        eval_mock.assert_not_called()


class StatusTest(FourStateTestBase):
    def test_status_reports_files_and_liveness(self):
        import io, contextlib
        (self.state_dir / "enabled").write_text("1\n")
        self.keyd_dest.write_text(ctrl_swap.keyd_config(True, False))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), \
             mock.patch.object(ctrl_swap, "remap_is_live", return_value=True):
            ctrl_swap.status()
        data = json.loads(buf.getvalue())
        self.assertTrue(data["enabled"])
        self.assertFalse(data["voiceEnabled"])
        self.assertTrue(data["remapApplied"])
        self.assertEqual(data["backend"], "keyd")


if __name__ == "__main__":
    unittest.main()
