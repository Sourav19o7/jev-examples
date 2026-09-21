"""The only module that mutates the mailbox."""

from organiser.policy import Plan


def ensure_labels(service, names: set[str]) -> dict[str, str]:
    """Map label name to id, creating any that don't exist yet."""
    existing = {
        label["name"]: label["id"]
        for label in service.users()
        .labels()
        .list(userId="me")
        .execute()
        .get("labels", [])
    }

    for name in sorted(names):
        if name in existing:
            continue
        # Gmail creates the parent of a nested label implicitly.
        created = (
            service.users()
            .labels()
            .create(
                userId="me",
                body={
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                },
            )
            .execute()
        )
        existing[name] = created["id"]

    return existing


def apply(service, plans: list[Plan]) -> tuple[int, int]:
    actionable = [p for p in plans if not p.needs_review and (p.add_labels or p.archive)]
    if not actionable:
        return 0, 0

    wanted = {name for plan in actionable for name in plan.add_labels}
    label_ids = ensure_labels(service, wanted)

    labelled = archived = 0
    for plan in actionable:
        body: dict = {}
        if plan.add_labels:
            body["addLabelIds"] = [label_ids[name] for name in plan.add_labels]
        if plan.archive:
            body["removeLabelIds"] = ["INBOX"]

        service.users().messages().modify(
            userId="me", id=plan.judgement.email.id, body=body
        ).execute()

        if plan.add_labels:
            labelled += 1
        if plan.archive:
            archived += 1

    return labelled, archived
