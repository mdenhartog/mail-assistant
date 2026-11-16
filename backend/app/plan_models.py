"""Request and response models of the plan API (U-mail-categories-17, ADR-0044, ADR-0046, ADR-0047)."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

MAX_IDS = 200  # AC-34: the most items one decision may name (the database function checks it again)
PAGE_SIZE = 100  # AC-24: the most items one page of the review returns
MAX_PAGE = 100  # 100 pages of 100 are twice the cap of 5 000 items per plan
MAX_ITEM_ID = 999_999_999_999_999_999  # the largest id the database function accepts (18 digits)
MAX_COUNT = 2_000_000_000  # an item count that fits the database's integer

PlanState = Literal["building", "ready", "scheduled", "applying", "applied", "replaced", "discarded", "cancelled"]
Decision = Literal["approved", "rejected"]

_CONFIG = ConfigDict(frozen=True, extra="forbid", alias_generator=to_camel, populate_by_name=True)


class PlanProgress(BaseModel):
    """How far the build is: mails checked, the cap, the unclear mails, the estimate and the mails past the cap."""

    model_config = _CONFIG

    checked: Annotated[int, Field(ge=0)]
    cap: Annotated[int, Field(ge=0)]
    unclear: Annotated[int, Field(ge=0)]
    estimate: Annotated[int, Field(ge=0)] | None  # "about M"; None until the agent has an estimate (AC-43)
    not_looked_at: Annotated[int, Field(ge=0)]  # in scope but past the cap


class GroupExample(BaseModel):
    """One mail of a group, shown as text (ADR-0044): the lowest-numbered item, cleaned when the plan was built."""

    model_config = _CONFIG

    sender_name: str
    sender_address: str
    subject: str


class PlanGroup(BaseModel):
    """The items that move from one category to another; the nil UUID is the built-in "Other"."""

    model_config = _CONFIG

    from_category: Annotated[uuid.UUID, Field(serialization_alias="from")]
    to_category: Annotated[uuid.UUID, Field(serialization_alias="to")]
    count: Annotated[int, Field(ge=1)]
    approved: Annotated[int, Field(ge=0)]  # items of the group approved so far (AC-13)
    rejected: Annotated[int, Field(ge=0)]  # items of the group rejected so far (AC-13)
    example: GroupExample  # the row the collapsed group shows (C-18)


class PlanCounts(BaseModel):
    """Items of the open plan by decision."""

    model_config = _CONFIG

    items: Annotated[int, Field(ge=0)]
    pending: Annotated[int, Field(ge=0)]
    approved: Annotated[int, Field(ge=0)]
    rejected: Annotated[int, Field(ge=0)]


class LastPlan(BaseModel):
    """The plan applied most recently, the one "Move back" is offered for."""

    model_config = _CONFIG

    id: uuid.UUID
    state: Literal["applied"]
    applied_at: datetime | None
    moved_count: Annotated[int, Field(ge=0)]  # mails the apply moved; kept on the plan after the items are removed


class PlanView(BaseModel):
    """What ``GET /api/plan`` returns; ``state`` is None while there is no open plan."""

    model_config = _CONFIG

    id: uuid.UUID | None
    state: PlanState | None
    progress: PlanProgress
    groups: list[PlanGroup]
    counts: PlanCounts
    apply_after: datetime | None
    apply_threshold: Annotated[int, Field(ge=1)] | None  # approve above this many mails needs the delay (AC-30)
    apply_delay_minutes: Annotated[int, Field(ge=0)] | None  # None while the apply settings are not stored
    last_plan: LastPlan | None


class PlanItem(BaseModel):
    """One mail of the plan. Sender and subject are text (ADR-0044); the Gmail message id is never exposed."""

    model_config = _CONFIG

    id: Annotated[int, Field(ge=1)]
    sender_name: str
    sender_address: str
    subject: str
    from_category: Annotated[uuid.UUID, Field(serialization_alias="from")]
    to_category: Annotated[uuid.UUID, Field(serialization_alias="to")]
    decision: Literal["pending", "approved", "rejected"]
    state: Literal["pending", "approved", "rejected", "applied", "skipped", "failed"]
    reason: str | None


class PlanItemsPage(BaseModel):
    """At most ``PAGE_SIZE`` items of the open plan."""

    model_config = _CONFIG

    items: list[PlanItem]
    page: Annotated[int, Field(ge=1)]
    has_more: bool


class GroupRef(BaseModel):
    """The two categories of a group."""

    model_config = _CONFIG

    from_category: Annotated[uuid.UUID, Field(alias="from")]
    to_category: Annotated[uuid.UUID, Field(alias="to")]


class GroupScope(BaseModel):
    """Every item of one group; ``group_count`` is the size the user saw, so a changed group is a 409."""

    model_config = _CONFIG

    group: GroupRef
    group_count: Annotated[int, Field(ge=1, le=MAX_COUNT)]


class IdsScope(BaseModel):
    """Named items. More than ``MAX_IDS`` is answered by the route with a reason, so the limit is only documented."""

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
        json_schema_extra={"properties": {"ids": {"maxItems": MAX_IDS}}},
    )

    ids: Annotated[list[Annotated[int, Field(strict=True, ge=1, le=MAX_ITEM_ID)]], Field(min_length=1)]


class AllScope(BaseModel):
    """Every item of the plan."""

    model_config = _CONFIG

    all: Literal[True]


class DecisionRequest(BaseModel):
    """The body of ``POST /api/plan/decisions``: the plan and item count the user saw, the scope and the decision."""

    model_config = _CONFIG

    plan_id: uuid.UUID
    item_count: Annotated[int, Field(ge=0, le=MAX_COUNT)]
    scope: GroupScope | IdsScope | AllScope
    decision: Decision


class ApproveRequest(BaseModel):
    """The body of ``POST /api/plan/approve``."""

    model_config = _CONFIG

    plan_id: uuid.UUID
    item_count: Annotated[int, Field(ge=0, le=MAX_COUNT)]


class DecisionResult(BaseModel):
    """How many items the decision changed."""

    model_config = _CONFIG

    changed: Annotated[int, Field(ge=0)]


class ApprovalResult(BaseModel):
    """The state of the plan after the approval and when the apply may start."""

    model_config = _CONFIG

    state: PlanState
    apply_after: datetime | None


class MoveBackResult(BaseModel):
    """The move-back request of a plan; ``processed`` is True once the agent has restored the labels."""

    model_config = _CONFIG

    plan_id: uuid.UUID
    processed: bool


class PlanConflict409(BaseModel):
    """A plan, count or state mismatch; no row values."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[409]


class PlanProblem422(BaseModel):
    """A refused body: the generic 422, with a ``reason`` when one is known (more ids than a decision may name)."""

    model_config = _CONFIG

    type: str
    title: str
    status: Literal[422]
    reason: Literal["too_many_ids"] | None = None
