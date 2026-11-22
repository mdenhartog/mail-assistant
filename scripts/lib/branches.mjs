// Branch names of the build (skill git-workflow), shared by status.mjs, check.mjs, feature.mjs and ci-triage.mjs.
//
//   feature branch   feat/<INT-nnn>/<feature>  (fix/… for a fix; the Control Room's feat/<feature> counts too)
//                    pushed, one pull request per feature, the only branch CI tests
//   unit branch      unit/<INT-nnn>/<feature>/<nn>  (unit U-<feature>-<nn>)
//                    local only: branched from the feature branch, landed back into it, never a pull request
//
// A unit branch cannot live under the feature branch's name (feat/INT-003/pdf-export/02 next to
// feat/INT-003/pdf-export is a ref conflict in git), hence its own `unit/` prefix. The older unit
// branch feat|fix/<INT-nnn>/<feature>/<nn> (kit ≤ 0.6) is still recognised.
import { spawnSync } from "node:child_process";

const SLUG = "[a-z0-9][a-z0-9-]*";
const UNIT = new RegExp(`^(?:origin/)?unit/(INT-\\d+)/(${SLUG})/(\\d+)$`);
const LEGACY_UNIT = new RegExp(`^(?:origin/)?(?:feat|fix)/(INT-\\d+)/(${SLUG})/(\\d+)$`);
const FEATURE = new RegExp(`^(?:origin/)?(feat|fix)/(INT-\\d+)/(${SLUG})$`);
const SHORT_FEATURE = new RegExp(`^(?:origin/)?feat/(${SLUG})$`);

export const stripRemote = (name) => String(name).replace(/^origin\//, "");

/** A unit branch: { intent, feature, nn, unit, legacy } or null. */
export function parseUnitBranch(name) {
  const m = UNIT.exec(name) ?? LEGACY_UNIT.exec(name);
  if (!m) return null;
  return { intent: m[1], feature: m[2], nn: m[3], unit: `U-${m[2]}-${m[3]}`, legacy: !UNIT.test(name) };
}

/** A feature branch: { kind, intent, feature } or null (intent is "" for feat/<feature>). */
export function parseFeatureBranch(name) {
  const m = FEATURE.exec(name);
  if (m) return { kind: m[1], intent: m[2], feature: m[3] };
  const s = SHORT_FEATURE.exec(name);
  return s ? { kind: "feat", intent: "", feature: s[1] } : null;
}

/** U-<feature>-<nn> → { feature, nn }, or null. */
export function parseUnitId(id) {
  const m = new RegExp(`^U-(${SLUG})-(\\d+)$`).exec(String(id));
  return m ? { feature: m[1], nn: m[2] } : null;
}

export const unitBranch = (intent, feature, nn) => `unit/${intent}/${feature}/${nn}`;
export const featureBranch = (intent, feature, kind = "feat") => `${kind}/${intent}/${feature}`;

/** The names a unit's feature branch can have, the preferred one first. */
export function featureCandidates({ intent, feature }) {
  return [...(intent ? [featureBranch(intent, feature), featureBranch(intent, feature, "fix")] : []), `feat/${feature}`];
}

function gitOk(cwd, args) {
  const r = spawnSync("git", args, { cwd, encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : "";
}

/** The first existing ref among the names (local branch first, then origin/), or "". */
export function existingRef(cwd, names) {
  for (const name of names) {
    for (const ref of [name, `origin/${name}`]) if (gitOk(cwd, ["rev-parse", "--verify", "-q", `${ref}^{commit}`])) return ref;
  }
  return "";
}

/**
 * What the current branch is compared with: the feature branch for a unit branch (so earlier units
 * of the feature are not counted as this unit's change), otherwise main.
 */
export function baseRef(cwd, branch = gitOk(cwd, ["rev-parse", "--abbrev-ref", "HEAD"])) {
  const unit = parseUnitBranch(branch);
  if (unit && !unit.legacy) {
    const feature = existingRef(cwd, featureCandidates(unit));
    if (feature) return feature;
  }
  return existingRef(cwd, ["main", "master"]);
}
