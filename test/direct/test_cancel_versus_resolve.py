def _open_bounty(contract):
    return contract.create_bounty(
        "Add rate-limit middleware",
        "PR must add middleware and tests. Closes the linked issue.",
        "https://github.com/expressjs/express/issues/42",
        "https://gitlab.com/gitlab-org/gitlab/-/blob/master/README.md",
        0,
        value=10**18,
    )


def test_cancel_blocked_while_review_is_live(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy("src/BountyBoard.py")

    direct_vm.sender = direct_alice
    bounty_id = _open_bounty(contract)

    direct_vm.sender = direct_bob
    contract.submit_work(
        bounty_id,
        "https://github.com/expressjs/express/pull/1",
        "https://gitlab.com/gitlab-org/gitlab/-/commit/abc123",
        str(direct_bob),
    )

    direct_vm.sender = direct_alice
    with direct_vm.expect_revert("cannot cancel while a live review is pending"):
        contract.cancel(bounty_id)

    with direct_vm.expect_revert("review timeout has not passed"):
        contract.expire_review(bounty_id)

    after = contract.get_bounty(bounty_id)
    assert "PENDING_REVIEW" in after
    assert "REFUNDED_TO_FUNDER" not in after
    assert "RESERVED" in after


def test_funder_can_cancel_open_bounty(
    direct_vm, direct_deploy, direct_alice
):
    contract = direct_deploy("src/BountyBoard.py")

    direct_vm.sender = direct_alice
    bounty_id = _open_bounty(contract)
    contract.cancel(bounty_id)

    after = contract.get_bounty(bounty_id)
    assert "CANCELLED" in after
    assert "REFUNDED_TO_FUNDER" in after


def test_non_funder_cannot_cancel(
    direct_vm, direct_deploy, direct_alice, direct_bob
):
    contract = direct_deploy("src/BountyBoard.py")

    direct_vm.sender = direct_alice
    bounty_id = _open_bounty(contract)

    direct_vm.sender = direct_bob
    with direct_vm.expect_revert("only the funder can cancel"):
        contract.cancel(bounty_id)