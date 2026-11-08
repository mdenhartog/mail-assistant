# Production signals

Signal files `SIG-nnn-<slug>.md` written in phase 10 (skill `production-signals`): what production, evals, security scans and users report, and the decision taken (new intent or closed with a reason).

Bugs in a released version are registered here by the bug agent (skill `bug-loop`, command `/sdlc:bugs`) with `kind: bug` and a `status` that goes from `new` through `reproduced`, `fixing` and `pr-open` to `released` and `verified`.
