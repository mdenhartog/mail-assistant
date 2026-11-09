# Memory index

One line per item: `id · title · area · tags · path`. Valid items only; superseded items live in `archive/` and not here. Managed with the skill `app-memory`.

- ADR-0001 · Development process: claude-sdlc-kit · area:process · tags:sdlc,tdd,security · decisions/ADR-0001-sdlc-kit.md
- ADR-0002 · Mobile target: no native app; responsive web · area:mobile-target · tags:mobile · decisions/ADR-0002-mobile-target.md
- ADR-0003 · Work tracking: repo docs · area:work-tracking · tags:specs,plans,git · decisions/ADR-0003-work-tracking.md
- ADR-0004 · Source control: GitHub · area:source-control · tags:github,ci,releases · decisions/ADR-0004-source-control.md
- ADR-0005 · Agent platform: self with Telegram · area:agent-platform · tags:agents,mcp,a2a · decisions/ADR-0005-agent-platform.md
- ADR-0006 · GxP relevance: not a GxP system · area:gxp · tags:gamp5,validation · decisions/ADR-0006-gxp.md
- ADR-0007 · Database: PostgreSQL, no extensions · area:database · tags:postgresql,database · decisions/ADR-0007-database.md
- ADR-0009 · Design process: clickable prototype per feature · area:design-process · tags:prototype,ux,design · decisions/ADR-0009-design-process.md
- ADR-0010 · Design system: generate modern AI-first style · area:design-system · tags:design,tokens,tailwind · decisions/ADR-0010-design-system.md
- ADR-0011 · API integrations: Gmail and Google Calendar · area:api-style · tags:gmail,google-calendar,rest,oauth2 · decisions/ADR-0011-api-integrations.md
- ADR-0012 · Hosting: Kubernetes via Helm + Argo CD · area:hosting · tags:kubernetes,helm,argocd · decisions/ADR-0012-hosting.md
- ADR-0013 · Observability: Sentry + Grafana · area:observability · tags:sentry,grafana,monitoring · decisions/ADR-0013-observability.md
- ADR-0014 · Model routing: automatic Haiku → Sonnet → Opus · area:model-routing · tags:llm,model-routing · decisions/ADR-0014-model-routing.md
- ADR-0015 · Bug agent: fix mode · area:bug-agent · tags:bug-agent,automation · decisions/ADR-0015-bug-agent.md
- ADR-0016 · Process autonomy: fixed gates only · area:process · tags:autonomy,gates · decisions/ADR-0016-process-autonomy.md
- ADR-0017 · Models through the Anthropic API, not Amazon Bedrock · area:agent-platform · tags:llm,anthropic,bedrock · decisions/ADR-0017-anthropic-api.md
- ADR-0018 · Mail triage: accepted data-disclosure risks · area:security · tags:privacy,anthropic,telegram · decisions/ADR-0018-mail-triage-accepted-risks.md
- ADR-0019 · Mail triage: one new agent component with its own Telegram client · area:architecture · tags:mail-triage,agents,telegram · decisions/ADR-0019-mail-triage-architecture.md

- ADR-0020 · Mail triage: store capped alert content for 30 days · area:data · tags:mail-triage,privacy,retention · decisions/ADR-0020-mail-triage-alert-content.md
- ADR-0021 · Mail triage: one-time catch-up of unread inbox mail · area:architecture · tags:mail-triage,gmail,budget,state · decisions/ADR-0021-mail-triage-catch-up.md
- ADR-0022 · Dependency cooldown of 7 days for uv, pnpm and Renovate · area:security · tags:supply-chain,uv,pnpm,renovate · decisions/ADR-0022-dependency-cooldown.md
- ADR-0023 · Adjustable quiet hours: settings in a shared PostgreSQL table · area:architecture · tags:mail-triage,settings,postgresql,web · decisions/ADR-0023-settings-shared-table.md
- ADR-0024 · Web sign-in: generic OIDC provider, identity scopes only · area:identity · tags:oidc,oauth2,authentication,web · decisions/ADR-0024-web-signin-generic-oidc.md
- ADR-0025 · Settings contract: own schema, agent-owned migrations, shared policy package · area:architecture · tags:mail-triage,settings,postgresql,contract · decisions/ADR-0025-settings-contract.md
- ADR-0026 · Mail triage: one conversation state for all Telegram dialogues · area:architecture · tags:mail-triage,telegram,state · decisions/ADR-0026-single-conversation-state.md
- ADR-0027 · Wall-clock times: resolution of non-existent and ambiguous local times · area:architecture · tags:mail-triage,time,dst · decisions/ADR-0027-wall-clock-resolution.md
- ADR-0028 · Time-zone lookup: a hand-curated list of cities, countries and aliases · area:architecture · tags:mail-triage,time-zone,data · decisions/ADR-0028-place-list.md
- component · Project workflow · area:process · tags:workflow,phases · components/project-workflow.md
