# Change log

## 2026-08-30 — keyboard profile and voice trigger repair

- Restored the original voice behavior: CapsLock emits the plugin-owned F24
  signal, Ctrl uses `overload(control, f24)`, and F24 runs
  `voxtype record toggle` on release. F9 remains the user's own toggle.
- Added independent CapsLock, Left Ctrl, and Right Ctrl state reporting and
  mappings, including tests for the complete voice-key set.
- Added a keyboard keyd profile selector. It lists `/etc/keyd/*.conf` and the
  IDs in each `[ids]` section, persists the selected profile, and applies a
  marked plugin block to an explicitly selected profile without discarding its
  existing mappings.
- Fixed the privileged helper boundary for selected keyd profiles and added a
  passwordless-sudo fallback for systems where a Polkit prompt is unavailable.
- On the development machine, selected the MINILA-R profile
  (`k:0c45:22b8`), removed the conflicting plugin wildcard config, and applied
  the managed voice mappings to the actual keyboard profile.

## Compatibility

When no explicit profile is selected, the plugin continues to use its own
`/etc/keyd/hancore-ctrl-swap.conf` wildcard profile. User-specific profiles are
only changed after selection in the panel.
