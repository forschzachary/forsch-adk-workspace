# Changelog

## [0.2.0](https://github.com/forschzachary/forsch-adk-workspace/compare/live-agent-graph-v0.1.0...live-agent-graph-v0.2.0) (2026-07-01)


### Features

* **chat:** per-cluster history persistence + compact/hideable tool calls ([ecc217a](https://github.com/forschzachary/forsch-adk-workspace/commit/ecc217af18317579ed5c7e786d860bb4d1b86d51))
* **cockpit:** bigger swimlane workspace ([#47](https://github.com/forschzachary/forsch-adk-workspace/issues/47)) ([3cd44cd](https://github.com/forschzachary/forsch-adk-workspace/commit/3cd44cde29759dcf290b6c0866c9205d6cb2928f))
* **cockpit:** bundles as blobs with their tools haloing them (physics layout) ([#44](https://github.com/forschzachary/forsch-adk-workspace/issues/44)) ([46eb389](https://github.com/forschzachary/forsch-adk-workspace/commit/46eb389d4bfb0955672dbac0ad6388d0e152d165))
* **cockpit:** center a delegating hub agent among its targets ([#53](https://github.com/forschzachary/forsch-adk-workspace/issues/53)) ([4336965](https://github.com/forschzachary/forsch-adk-workspace/commit/43369653f782de05ed46e3752eb5511eb51d02c3))
* **cockpit:** clean-line layout — bundles under agents, agents under interfaces ([#46](https://github.com/forschzachary/forsch-adk-workspace/issues/46)) ([ae7a52f](https://github.com/forschzachary/forsch-adk-workspace/commit/ae7a52fe3422b04740606000bf7e0eeb03aed07b))
* **cockpit:** live-agent-graph semantic-shapes update ([#58](https://github.com/forschzachary/forsch-adk-workspace/issues/58)) ([4104445](https://github.com/forschzachary/forsch-adk-workspace/commit/410444589d8bf141a0c8bbd346a597da12528c50))
* **cockpit:** readable halos + tool inspect card ([#48](https://github.com/forschzachary/forsch-adk-workspace/issues/48)) ([1537027](https://github.com/forschzachary/forsch-adk-workspace/commit/15370271dd3c54718c6a69bbb878e04c3fe0e127))
* **cockpit:** wire cluster Active/Off/Restart buttons to systemctl control ([#60](https://github.com/forschzachary/forsch-adk-workspace/issues/60)) ([64dffcf](https://github.com/forschzachary/forsch-adk-workspace/commit/64dffcf6986ea360b5c93f7b89448fa967fe97e8))
* derive the ScreeningRoom native bots from the bridge code (graph↔code parity) ([#54](https://github.com/forschzachary/forsch-adk-workspace/issues/54)) ([c5ba623](https://github.com/forschzachary/forsch-adk-workspace/commit/c5ba623a0b95cfb7bb7ec47eff2602bf74fee07c))
* **graph:** decouple cockpit from Frappe CRM — repo is the single source of truth ([#37](https://github.com/forschzachary/forsch-adk-workspace/issues/37)) ([fd1a864](https://github.com/forschzachary/forsch-adk-workspace/commit/fd1a8641fa43d178f1ec6a683c702c72e6e47d74))
* **growth:** LinkedIn + personal-brand + website launch team ([#34](https://github.com/forschzachary/forsch-adk-workspace/issues/34)) ([f791db9](https://github.com/forschzachary/forsch-adk-workspace/commit/f791db9153aeaec052f6326ea7cabf09b7411436))
* **screeningroom:** real Huberto-&gt;Ops delegation over A2A + honest graph edge ([#50](https://github.com/forschzachary/forsch-adk-workspace/issues/50)) ([350b835](https://github.com/forschzachary/forsch-adk-workspace/commit/350b835669e8d1effd5b2509a5ba6ce6ed285a1e))
* session consolidation — ScreeningRoom native bots + forsch CLI/goal/eval/skills ([#36](https://github.com/forschzachary/forsch-adk-workspace/issues/36)) ([1339831](https://github.com/forschzachary/forsch-adk-workspace/commit/13398312cc691a7f98f8cd0cb19280211bac9696))
* tool bundles — schema + factory expansion + graph layer + cockpit picker ([#42](https://github.com/forschzachary/forsch-adk-workspace/issues/42)) ([a55c6b0](https://github.com/forschzachary/forsch-adk-workspace/commit/a55c6b0eb5568df7f16f5f00f63b133e950d527c))
* uv workspace + enforcement scaffolding (verify, release-please, bijection, pre-commit) ([81c73b6](https://github.com/forschzachary/forsch-adk-workspace/commit/81c73b61e094fc7cb5a703c60d40246c47f0ab95))


### Bug Fixes

* **bridge:** add a2a_delegation module + wire curator delegation ([#52](https://github.com/forschzachary/forsch-adk-workspace/issues/52)) ([95221f1](https://github.com/forschzachary/forsch-adk-workspace/commit/95221f10676ce8a0d4f4d1224c794ac38c2aac91))
* **chat:** raise cockpit→chat proxy timeout to 280s + point AGENTS.md at the forsch CLI ([#38](https://github.com/forschzachary/forsch-adk-workspace/issues/38)) ([ed71e10](https://github.com/forschzachary/forsch-adk-workspace/commit/ed71e10b153770fa10b1b0c7711127a66771f6c7))
* **cockpit:** bundles render as blobs with their tools floating around them ([#43](https://github.com/forschzachary/forsch-adk-workspace/issues/43)) ([552964e](https://github.com/forschzachary/forsch-adk-workspace/commit/552964ef3c661344694f53578c3e53a3d80b3cf0))
* **cockpit:** robust even agent spacing under high tool density ([#56](https://github.com/forschzachary/forsch-adk-workspace/issues/56)) ([2e46b10](https://github.com/forschzachary/forsch-adk-workspace/commit/2e46b107038844b5040596a0c880c1fcccb58478))
* **cockpit:** zoom-out collapse + split ScreeningRoom Discord channels ([#49](https://github.com/forschzachary/forsch-adk-workspace/issues/49)) ([03d0040](https://github.com/forschzachary/forsch-adk-workspace/commit/03d00404dcf2270c9a7ce785f567f52606bc4476))
* **migration:** repoint stale component paths after consolidation ([12115be](https://github.com/forschzachary/forsch-adk-workspace/commit/12115bee29767a646f674c779f5650bf23c97004))
* **monorepo:** green check_structure + check_bijection (Task 6) ([93706e5](https://github.com/forschzachary/forsch-adk-workspace/commit/93706e5146d55c9266ff83a99ae6b1c9714c06d4))
* **security:** validate agent_id before it reaches docker exec (code injection) ([#62](https://github.com/forschzachary/forsch-adk-workspace/issues/62)) ([885988d](https://github.com/forschzachary/forsch-adk-workspace/commit/885988d76f7387e408f104b040d7264426f166e4))
* **surfaces:** stream-message init, SSE tail flush, tool guard, atomic + locked manifest writes ([#66](https://github.com/forschzachary/forsch-adk-workspace/issues/66)) ([cbf049b](https://github.com/forschzachary/forsch-adk-workspace/commit/cbf049b76ffaef2a6827d90a1986215549949639))
