# Bridge directory note

Purpose: Discord ingress for ADK agents. The bridge receives Discord messages, resolves the target team agent from `bridge_config.yaml`, runs the selected ADK agent through `google.adk.runners.Runner`, and streams responses back to Discord.

Structure:

- `bridge_config.yaml` - channel-to-agent routing, Discord token env name, session DB path, streaming limits, and log path.
- `src/forsch/adk_bridge/bridge.py` - Discord client, ADK Runner wiring, channel map construction, session creation, and streaming buffer.
- `tests/test_stability_route.py` - smoke tests that keep the stability route, package dependency, and manifest entry aligned.
- `data/` - local SQLite ADK session storage when the bridge runs from this directory.

Current organization rule: keep this bridge ADK-native and Hermes-independent. It should handle Discord I/O plus ADK Runner/session services only; shared inspection or business tools belong in `components`, and agent behavior belongs in the owning `agents/<name>` package.

Safety note: route edits are config changes. Validate them with the targeted bridge tests before running the live bridge, and do not restart the live service unless the active task explicitly authorizes it.
