def test_early_resolve_cannot_close_bounty(
    direct_vm, direct_deploy, direct_alice
):
    contract = direct_deploy("src/BountyBoard.py")

    direct_vm.sender = direct_alice
    bounty_id = contract.create_bounty(
        "Add rate-limit middleware",
        "PR must add middleware and tests. Closes the linked issue.",
        "https://github.com/expressjs/express/issues/42",
        "https://gitlab.com/gitlab-org/gitlab/-/blob/master/README.md",
        0,
        value=10**18,
    )

    locked = contract.get_bounty(bounty_id)
    assert "OPEN" in locked
    assert "RESERVED" in locked

    with direct_vm.expect_revert("no pending submission to resolve"):
        contract.resolve(bounty_id)

    after = contract.get_bounty(bounty_id)
    assert "OPEN" in after
    assert "ACCEPTED" not in after
    assert "PAID_TO_HUNTER" not in after
    assert "REFUNDED_TO_FUNDER" not in after
    assert "RESERVED" in after

    assert contract.get_bounty_status(bounty_id) == "OPEN"