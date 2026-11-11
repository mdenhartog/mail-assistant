"""Rule to field map: which fields of the settings form a refused rule belongs to (AC-10).

Plain strings on purpose: ``tests/test_settings_read.py`` compares the keys with ``schedule_policy.RULES``, so a rule
added to the package without a mapping fails there. Field names are those of the API (camelCase).
"""

TIME_FIELDS = ("quietStart", "quietEnd", "overviewAt", "remindAt")
_WINDOW = ("quietStart", "quietEnd")

FIELD_OF_RULE: dict[str, tuple[str, ...]] = {
    "zone_unknown": ("timeZone",),
    # A malformed time can be any of the four; the write route picks the one that failed.
    "time_not_whole_minute": TIME_FIELDS,
    "time_has_zone": TIME_FIELDS,
    "quiet_window_empty": _WINDOW,
    "quiet_window_length": _WINDOW,
    "overview_in_quiet_hours": ("overviewAt",),
    "remind_in_quiet_hours": ("remindAt",),
}
