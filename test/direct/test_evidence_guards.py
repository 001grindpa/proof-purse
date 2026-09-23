INCOMPLETE = {
    "page_kind": "PULL",
    "repo": "org/repo",
    "artifact_id": "1",
    "summary": "partial work",
    "completeness": "PARTIAL",
    "authorized_recipient": "",
    "page_text": "",
}

COMPLETE = {
    "page_kind": "PULL",
    "repo": "org/repo",
    "artifact_id": "1",
    "summary": "done",
    "completeness": "COMPLETE",
    "authorized_recipient": "",
    "page_text": "",
}


def _open_and_submit(contract, direct_vm, direct_alice, direct_bob):
    direct_vm.sender = direct_alice
    bounty_id = contract.create_bounty(
        "Add rate-limit middleware",
        "PR must add middleware and tests. Closes the linked issue.",
        "https://github.com/expressjs/express/issues/42",
        "https://gitlab.com/gitlab-org/gitlab/-/blob/master/README.md",
        0,
        value=10**18,
    )
    direct_vm.sender = direct_bob
    recipient = str(direct_bob)
    contract.submit_work(
        bounty_id,
        "https://github.com/expressjs/express/pull/1",
        "https://gitlab.com/gitlab-org/gitlab/-/commit/abc123",
        recipient,
    )
    return bounty_id, recipient


def test_fetch_or_parse_failure_reopens_bounty(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy("src/BountyBoard.py")
    bounty_id, _ = _open_and_submit(contract, direct_vm, direct_alice, direct_bob)

    def boom(*_args, **_kwargs):
        raise RuntimeError("fetch failed")

    contract._extract_page = boom
    contract.resolve(bounty_id)

    after = contract.get_bounty(bounty_id)
    assert "OPEN" in after
    assert "UNKNOWN" in after
    assert "PAID_TO_HUNTER" not in after
    assert "RESERVED" in after


def test_partial_evidence_does_not_pay(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy("src/BountyBoard.py")
    bounty_id, recipient = _open_and_submit(
        contract, direct_vm, direct_alice, direct_bob
    )

    def partial_page(url, role, title, spec_text):
        page = dict(INCOMPLETE)
        page["authorized_recipient"] = recipient.lower()
        page["page_text"] = recipient
        return page

    contract._extract_page = partial_page
    contract._judge_work = lambda *args, **kwargs: {
        "verdict": "ACCEPTED",
        "confidence": "HIGH",
        "reason": "should still be blocked",
    }
    contract.resolve(bounty_id)

    after = contract.get_bounty(bounty_id)
    assert "PAID_TO_HUNTER" not in after
    assert "ACCEPTED" not in after or '"status": "ACCEPTED"' not in after
    assert "RESERVED" in after
    assert "OPEN" in after


def test_validator_disagreement_does_not_pay(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy("src/BountyBoard.py")
    bounty_id, recipient = _open_and_submit(
        contract, direct_vm, direct_alice, direct_bob
    )

    calls = {"n": 0}

    def flip_decision(*_args, **_kwargs):
        calls["n"] += 1
        accepted = calls["n"] == 1
        return {
            "verdict": "ACCEPTED" if accepted else "REJECTED",
            "confidence": "HIGH",
            "reason": "leader and validator differ",
            "work_complete": True,
            "recipient_bound": True,
        }

    contract._decision_from_pages = flip_decision

    try:
        contract.resolve(bounty_id)
    except Exception:
        pass

    after = contract.get_bounty(bounty_id)
    assert "PAID_TO_HUNTER" not in after
    assert "RESERVED" in after