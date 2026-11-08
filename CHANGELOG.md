# Changelog

## [0.2.0](https://github.com/mdenhartog/mail-assistant/compare/v0.1.0...v0.2.0) (2026-11-08)


### Features

* **mail-triage:** add a read-only remaining() to the daily model budget ([8916dbb](https://github.com/mdenhartog/mail-assistant/commit/8916dbb3a844934d18a2d6680e77b4ad3db6de00))
* **mail-triage:** add alert delivery with hourly cap and held batch ([0bfbd8f](https://github.com/mdenhartog/mail-assistant/commit/0bfbd8f2f79c913121fe8629ff1e5ffb6e4a7839))
* **mail-triage:** add alert state machine ([35690ba](https://github.com/mdenhartog/mail-assistant/commit/35690baed2fabe9eb65e3820872c2fd098dad79f))
* **mail-triage:** add alert text and digest builders ([5825eee](https://github.com/mdenhartog/mail-assistant/commit/5825eee0584768458e06094dcc1ad0586df7ae27))
* **mail-triage:** add Anthropic model adapter with budget and escalation ([98b83da](https://github.com/mdenhartog/mail-assistant/commit/98b83da3150ef221d4aa339909764ed38a99b966))
* **mail-triage:** add command router, run loop and Google/budget settings ([3edefb6](https://github.com/mdenhartog/mail-assistant/commit/3edefb6c387e8dfc7de5cdbf33adec106787026f))
* **mail-triage:** add component skeleton and fail-closed configuration ([64ab299](https://github.com/mdenhartog/mail-assistant/commit/64ab299b1ad1e378a92b8997cea1d19ccae01f15))
* **mail-triage:** add daily overview ([3a7baa1](https://github.com/mdenhartog/mail-assistant/commit/3a7baa1a93ac4bb083ab196be8e5040f52d26da9))
* **mail-triage:** add encrypted token store and one-time consent flow ([b336b3d](https://github.com/mdenhartog/mail-assistant/commit/b336b3deca564ecd5bb25c4e386d558006bc2dc3))
* **mail-triage:** add end-to-end runbook and seed mails ([543a4bf](https://github.com/mdenhartog/mail-assistant/commit/543a4bfab0f22a97d5c40c1fa7188b93cc1a4617))
* **mail-triage:** add Gmail read and label adapter ([aa2a7eb](https://github.com/mdenhartog/mail-assistant/commit/aa2a7ebe94dc96741d7b17c8eb69352022fc3095))
* **mail-triage:** add Gmail send adapter for confirmed replies ([4965a45](https://github.com/mdenhartog/mail-assistant/commit/4965a4540639811428a3b79bb481e12152e4a640))
* **mail-triage:** add judgement schema and category policy ([381f04b](https://github.com/mdenhartog/mail-assistant/commit/381f04b060c3206ad6de61c7ac29c7ec8f727463))
* **mail-triage:** add PostgreSQL persistence and migration ([d33bc83](https://github.com/mdenhartog/mail-assistant/commit/d33bc83014d3e08182afa49035e775bddbb52458))
* **mail-triage:** add PostgreSQL store, migration 0002 and content retention ([0f332da](https://github.com/mdenhartog/mail-assistant/commit/0f332dad696918ab70985a7eeb8f4b7aac07b444))
* **mail-triage:** add reply flow with confirmation ([1affec4](https://github.com/mdenhartog/mail-assistant/commit/1affec4d75cff2ca66e8aeb68930fc2daacfdc52))
* **mail-triage:** add snooze, close and release-when-due commands ([13852af](https://github.com/mdenhartog/mail-assistant/commit/13852afbf98aebb76e59169ba1c0bcd9ca52c95e))
* **mail-triage:** add Telegram long-polling intake for the owner only ([a2f09be](https://github.com/mdenhartog/mail-assistant/commit/a2f09be7c2e612c5235ed5303818f20d2a476f2a))
* **mail-triage:** add Telegram outbox for alerts, notes and button acknowledgements ([e9785d2](https://github.com/mdenhartog/mail-assistant/commit/e9785d266b26b1f2d33d9ebf5dfad7493f0f6f11))
* **mail-triage:** add the catch-up state table and the backlog flag (migration 0003) ([277ba64](https://github.com/mdenhartog/mail-assistant/commit/277ba64d317bf3791e985c504c61e5d2362977bf))
* **mail-triage:** add the catch-up use case that files old unread mail newest first ([8f8bfd3](https://github.com/mdenhartog/mail-assistant/commit/8f8bfd34616a539df52c242f17708de0fb232e47))
* **mail-triage:** add time policy for quiet hours, snooze and overview ([cd0acb6](https://github.com/mdenhartog/mail-assistant/commit/cd0acb691a8e229f0c6c52bf2aeac89cf9139cfd))
* **mail-triage:** add triage pipeline with ports, retry limit and outage handling ([49f6d8f](https://github.com/mdenhartog/mail-assistant/commit/49f6d8ff2cb936df6a20091c017e9ab59ca55153))
* **mail-triage:** add worker Helm chart, hardened compose service and deploy tests ([4a2672b](https://github.com/mdenhartog/mail-assistant/commit/4a2672b9ddf3adffa8edc334b53c29c82b18c21c))
* **mail-triage:** cap the alerts of the catch-up at five ([d8a78b7](https://github.com/mdenhartog/mail-assistant/commit/d8a78b775d0386f3083fb1b8aeb4e191a9420dd6))
* **mail-triage:** keep a budget reserve for new mail and stop the catch-up when it is used ([7c22d17](https://github.com/mdenhartog/mail-assistant/commit/7c22d173c2010e2b9025dbd81cd8c9362eeccaae))
* **mail-triage:** list old urgent mail without an alert in the daily overview ([8300028](https://github.com/mdenhartog/mail-assistant/commit/83000288e9b63ae22c04846ccf466e470d2965e0))
* **mail-triage:** list unread inbox mail before a cut-off and expose Gmail labels ([af8dd11](https://github.com/mdenhartog/mail-assistant/commit/af8dd11df0808369c5763ed52a50e2f285d8c9a2))
* **mail-triage:** mail triage agent with a one-time catch-up of unread mail ([#1](https://github.com/mdenhartog/mail-assistant/issues/1)) ([1e23a71](https://github.com/mdenhartog/mail-assistant/commit/1e23a71c2b4cd7e937ec69c2a45c44d9e1408582))
* **mail-triage:** migrate the schema at start-up and ship migrations in the image ([87d15d8](https://github.com/mdenhartog/mail-assistant/commit/87d15d8b5d84894dea7b85fc1a97b59b83b5b51f))
* **mail-triage:** pass capped mail content to the store and record ADR-0020 ([e2acc1c](https://github.com/mdenhartog/mail-assistant/commit/e2acc1cb4e3915ee619c3e43e9812e5272d066b0))
* **mail-triage:** redact mail text and secrets from logs and error reports ([83d03b5](https://github.com/mdenhartog/mail-assistant/commit/83d03b5cb16a60a9c1a5757692755d2ba6139b9c))
* **mail-triage:** run the catch-up after new mail in every cycle and share one budget ([4f45808](https://github.com/mdenhartog/mail-assistant/commit/4f45808ae0e17043b0e4ba865cd6fd1156f7e631))
* **mail-triage:** store the catch-up state and count backlog alerts ([668265c](https://github.com/mdenhartog/mail-assistant/commit/668265cbd67b29504b2458b5010470c3c308323d))
* **mail-triage:** wire the agent together and complete .env.example ([9d5ae8e](https://github.com/mdenhartog/mail-assistant/commit/9d5ae8e2349aee0068bb1ac51dc1e966d4ef1568))


### Bug Fixes

* **mail-triage:** read the answer from the text block and leave room for thinking ([baef77f](https://github.com/mdenhartog/mail-assistant/commit/baef77f6ba4dd32a2740cef32f3a637c7b868fc7))
* **mail-triage:** remove pip from the runtime image ([2584fcf](https://github.com/mdenhartog/mail-assistant/commit/2584fcfde5215e54a39a9f4f0fdb1af074eb25b7))
