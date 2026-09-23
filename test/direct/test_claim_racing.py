def _open_bounty(contract):
    return contract.create_bounty(
        "Add rate-limit middleware",
        "PR must add middleware and tests. Closes the linked issue.",
        "https://github.com/expressjs/express/issues/42",
        "https://gitlab.com/gitlab-org/gitlab/-/blob/master/README.md",
        0,
        value=10**18,
    )


def test_second_hunter_cannot_claim_pending_bounty(
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

    pending = contract.get_bounty(bounty_id)
    assert "PENDING_REVIEW" in pending

    with direct_vm.expect_revert("a submission is already pending review"):
        contract.submit_work(
            bounty_id,
            "https://github.com/expressjs/express/pull/2",
            "https://gitlab.com/gitlab-org/gitlab/-/commit/def456",
            str(direct_bob),
        )

    after = contract.get_bounty(bounty_id)
    assert "PENDING_REVIEW" in after
    assert "PAID_TO_HUNTER" not in after