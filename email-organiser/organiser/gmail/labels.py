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


def apply(
    service,
    plans: list[Plan],
    only: set[str] | None = None,
    archive_only: set[str] | None = None,
) -> tuple[int, int]:
    """`only` restricts which messages are touched, `archive_only` which get archived.

    None means "no restriction", so the CLI's behaviour is unchanged.
    """
    actionable = [p for p in plans if not p.needs_review and (p.add_labels or p.archive)]
    if only is not None:
        actionable = [p for p in actionable if p.judgement.email.id in only]
    if not actionable:
        return 0, 0

    wanted = {name for plan in actionable for name in plan.add_labels}
    label_ids = ensure_labels(service, wanted)

    labelled = archived = 0
    for plan in actionable:
        body: dict = {}
        if plan.add_labels:
            body["addLabelIds"] = [label_ids[name] for name in plan.add_labels]
        if plan.archive and (archive_only is None or plan.judgement.email.id in archive_only):
            body["removeLabelIds"] = ["INBOX"]
        if not body:
            continue

        service.users().messages().modify(
            userId="me", id=plan.judgement.email.id, body=body
        ).execute()

        if "addLabelIds" in body:
            labelled += 1
        if "removeLabelIds" in body:
            archived += 1

    return labelled, archived
