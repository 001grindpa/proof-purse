# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlparse

from genlayer import *


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass

    class Write:
        pass


ALLOWED_HOSTS = (
    "github.com",
    "www.github.com",
    "gist.github.com",
    "raw.githubusercontent.com",
    "gitlab.com",
    "www.gitlab.com",
    "bitbucket.org",
    "www.bitbucket.org",
    "codeberg.org",
    "www.codeberg.org",
    "sr.ht",
    "git.sr.ht",
)

ACCEPTED_VERDICTS = ("ACCEPTED",)
NON_PAYING_VERDICTS = ("REJECTED", "PARTIAL", "UNRELATED", "UNKNOWN")


@allow_storage
@dataclass
class Bounty:
    funder: Address
    hunter: Address
    title: str
    spec_text: str
    spec_url_a: str
    spec_url_b: str
    work_url_a: str
    work_url_b: str
    amount: u256
    reserved: u256
    deadline_unix: u256
    status: str
    submission_status: str
    observed_verdict: str
    observed_confidence: str
    funds_disposition: str


class BountyBoard(gl.Contract):
    bounties: TreeMap[str, Bounty]
    next_bounty_id: u256
    reserved_bounties: u256

    def __init__(self):
        self.next_bounty_id = 1
        self.reserved_bounties = 0

    def _now(self) -> int:
        return int(datetime.now(timezone.utc).timestamp())

    def _require_bounty(self, bounty_id: str) -> Bounty:
        if bounty_id not in self.bounties:
            raise gl.vm.UserError("bounty not found")
        return self.bounties[bounty_id]

    def _host(self, url: str) -> str:
        return (urlparse(url).hostname or "").lower()

    def _path(self, url: str) -> str:
        return (urlparse(url).path or "").lower()

    def _path_kind(self, url: str) -> str:
        path = self._path(url)
        if "/pull/" in path or "/merge_requests/" in path:
            return "pull"
        if "/issues/" in path:
            return "issue"
        if "/commit/" in path or "/commits/" in path:
            return "commit"
        if "/compare/" in path:
            return "compare"
        if "/blob/" in path or "/src/" in path:
            return "blob"
        if "/raw/" in path or "raw.githubusercontent.com" in self._host(url):
            return "raw"
        if "/wiki/" in path:
            return "wiki"
        return "other"

    def _assert_trusted_url(self, url: str) -> None:
        if not url.startswith("https://"):
            raise gl.vm.UserError("URL must use https")
        host = self._host(url)
        allowed = False
        for allowed_host in ALLOWED_HOSTS:
            if host == allowed_host or host.endswith("." + allowed_host):
                allowed = True
                break
        if not allowed:
            raise gl.vm.UserError("URL host is not on the trusted code-host list")

    def _assert_independent_pair(self, url_a: str, url_b: str) -> None:
        self._assert_trusted_url(url_a)
        self._assert_trusted_url(url_b)
        if url_a.strip() == url_b.strip():
            raise gl.vm.UserError("the two URLs must be distinct")
        if self._path(url_a) == self._path(url_b) and self._host(url_a) == self._host(url_b):
            raise gl.vm.UserError("the two URLs must point at different pages")
        if self._host(url_a) == self._host(url_b) and self._path_kind(url_a) == self._path_kind(url_b):
            raise gl.vm.UserError(
                "same-host evidence must use different page kinds "
                "(issue, pull, commit, compare, blob, or raw)"
            )

    def _extract_page(self, url: str, role: str, title: str, spec_text: str) -> dict:
        page = gl.nondet.web.get(url)
        page_text = page.body.decode("utf-8")[:6000]
        prompt = f"""
You are extracting objective facts from a public software-hosting page.
Role of this page: {role}
Bounty title: {title}
Funder spec text:
{spec_text}

Page URL: {url}
Page content:
{page_text}

Return JSON only, with exactly these fields:
{{
  "page_kind": "ISSUE"|"PULL"|"COMMIT"|"COMPARE"|"BLOB"|"RAW"|"OTHER",
  "repo": "owner/name or UNKNOWN",
  "artifact_id": "issue/PR/commit identifier or UNKNOWN",
  "summary": "one short sentence describing what the page shows",
  "completeness": "COMPLETE"|"PARTIAL"|"UNRELATED"|"UNKNOWN"
}}
Rules:
- COMPLETE means the page clearly shows the named artifact and enough content to judge it.
- UNRELATED means the page is not about this bounty or repository.
- UNKNOWN if the page is empty, blocked, or does not identify the artifact.
- Do not decide whether the bounty should be paid. Only describe the page.
"""
        extracted = json.loads(gl.nondet.exec_prompt(prompt))
        page_kind = str(extracted.get("page_kind", "OTHER")).upper()
        completeness = str(extracted.get("completeness", "UNKNOWN")).upper()
        if page_kind not in ("ISSUE", "PULL", "COMMIT", "COMPARE", "BLOB", "RAW", "OTHER"):
            page_kind = "OTHER"
        if completeness not in ("COMPLETE", "PARTIAL", "UNRELATED", "UNKNOWN"):
            completeness = "UNKNOWN"
        return {
            "page_kind": page_kind,
            "repo": str(extracted.get("repo", "UNKNOWN"))[:120],
            "artifact_id": str(extracted.get("artifact_id", "UNKNOWN"))[:80],
            "summary": str(extracted.get("summary", ""))[:200],
            "completeness": completeness,
        }

    def _judge_work(
        self,
        title: str,
        spec_text: str,
        spec_a: dict,
        spec_b: dict,
        work_a: dict,
        work_b: dict,
    ) -> dict:
        prompt = f"""
You are judging whether submitted work fulfills a public bounty spec.
Decide only from the extracted page facts below. Do not invent repository state.

Bounty title: {title}
Funder spec text:
{spec_text}

Spec page A: {json.dumps(spec_a, sort_keys=True)}
Spec page B: {json.dumps(spec_b, sort_keys=True)}
Work page A: {json.dumps(work_a, sort_keys=True)}
Work page B: {json.dumps(work_b, sort_keys=True)}

Return JSON only, with exactly these fields:
{{
  "verdict": "ACCEPTED"|"REJECTED"|"PARTIAL"|"UNRELATED"|"UNKNOWN",
  "confidence": "HIGH"|"MEDIUM"|"LOW",
  "reason": "one short sentence"
}}
Rules:
- ACCEPTED only if both spec pages describe the same task, both work pages
  describe the same change, and the change clearly fulfills the spec.
- PARTIAL if some work exists but the spec is not fully met.
- UNRELATED if the work is for a different task or repository.
- UNKNOWN if pages are incomplete, contradictory, or unreadable.
- REJECTED if the work is readable and clearly does not fulfill the spec.
- Never use ACCEPTED when any page completeness is UNKNOWN or UNRELATED.
"""
        extracted = json.loads(gl.nondet.exec_prompt(prompt))
        verdict = str(extracted.get("verdict", "UNKNOWN")).upper()
        confidence = str(extracted.get("confidence", "LOW")).upper()
        if verdict not in ("ACCEPTED", "REJECTED", "PARTIAL", "UNRELATED", "UNKNOWN"):
            verdict = "UNKNOWN"
        if confidence not in ("HIGH", "MEDIUM", "LOW"):
            confidence = "LOW"
        return {
            "verdict": verdict,
            "confidence": confidence,
            "reason": str(extracted.get("reason", ""))[:200],
        }

    @gl.public.write.payable
    def create_bounty(
        self,
        title: str,
        spec_text: str,
        spec_url_a: str,
        spec_url_b: str,
        deadline_unix: u256,
    ) -> str:
        if not title.strip():
            raise gl.vm.UserError("title is required")
        if not spec_text.strip():
            raise gl.vm.UserError("spec text is required")
        self._assert_independent_pair(spec_url_a, spec_url_b)

        amount = gl.message.value
        if amount == 0:
            raise gl.vm.UserError("a non-zero bounty amount is required")

        deadline = int(deadline_unix)
        if deadline != 0 and deadline <= self._now():
            raise gl.vm.UserError("deadline must be in the future or zero")

        bounty_id = str(self.next_bounty_id)
        zero = Address("0x0000000000000000000000000000000000000000")
        self.bounties[bounty_id] = Bounty(
            funder=gl.message.sender_address,
            hunter=zero,
            title=title.strip()[:120],
            spec_text=spec_text.strip()[:2000],
            spec_url_a=spec_url_a.strip(),
            spec_url_b=spec_url_b.strip(),
            work_url_a="",
            work_url_b="",
            amount=amount,
            reserved=amount,
            deadline_unix=deadline_unix,
            status="OPEN",
            submission_status="NONE",
            observed_verdict="UNRESOLVED",
            observed_confidence="NONE",
            funds_disposition="RESERVED",
        )
        self.reserved_bounties = self.reserved_bounties + amount
        self.next_bounty_id = self.next_bounty_id + 1
        return bounty_id

    @gl.public.write
    def submit_work(self, bounty_id: str, work_url_a: str, work_url_b: str) -> None:
        bounty = self._require_bounty(bounty_id)
        if bounty.status != "OPEN":
            raise gl.vm.UserError("bounty is not open for submissions")
        if bounty.submission_status == "PENDING":
            raise gl.vm.UserError("a submission is already pending review")
        if int(bounty.deadline_unix) != 0 and self._now() >= int(bounty.deadline_unix):
            raise gl.vm.UserError("bounty deadline has passed")
        if gl.message.sender_address == bounty.funder:
            raise gl.vm.UserError("funder cannot submit work on their own bounty")

        self._assert_independent_pair(work_url_a, work_url_b)

        bounty.hunter = gl.message.sender_address
        bounty.work_url_a = work_url_a.strip()
        bounty.work_url_b = work_url_b.strip()
        bounty.submission_status = "PENDING"
        bounty.status = "PENDING_REVIEW"
        bounty.observed_verdict = "UNRESOLVED"
        bounty.observed_confidence = "NONE"

    @gl.public.write
    def resolve(self, bounty_id: str) -> None:
        bounty = self._require_bounty(bounty_id)
        if bounty.status != "PENDING_REVIEW" or bounty.submission_status != "PENDING":
            raise gl.vm.UserError("no pending submission to resolve")
        if bounty.reserved != bounty.amount:
            raise gl.vm.UserError("bounty reserve is inconsistent")
        if self.balance < bounty.reserved:
            raise gl.vm.UserError("contract is not solvent for this bounty")

        title = bounty.title
        spec_text = bounty.spec_text
        spec_url_a = bounty.spec_url_a
        spec_url_b = bounty.spec_url_b
        work_url_a = bounty.work_url_a
        work_url_b = bounty.work_url_b
        hunter = bounty.hunter
        amount = bounty.amount

        def fetch_and_judge() -> str:
            spec_a = self._extract_page(spec_url_a, "SPEC_A", title, spec_text)
            spec_b = self._extract_page(spec_url_b, "SPEC_B", title, spec_text)
            work_a = self._extract_page(work_url_a, "WORK_A", title, spec_text)
            work_b = self._extract_page(work_url_b, "WORK_B", title, spec_text)

            if spec_a["completeness"] == "UNRELATED" or spec_b["completeness"] == "UNRELATED":
                raise gl.vm.UserError("spec sources are unrelated to the bounty")
            if spec_a["repo"] != "UNKNOWN" and spec_b["repo"] != "UNKNOWN":
                if spec_a["repo"].lower() != spec_b["repo"].lower():
                    raise gl.vm.UserError("spec sources disagree on repository")
            if work_a["completeness"] == "UNRELATED" and work_b["completeness"] == "UNRELATED":
                raise gl.vm.UserError("work sources are unrelated to the bounty")

            judgment = self._judge_work(title, spec_text, spec_a, spec_b, work_a, work_b)
            # Incomplete pages cannot pay, even if the judge said ACCEPTED.
            blocking = (
                spec_a["completeness"] in ("UNKNOWN", "PARTIAL"),
                spec_b["completeness"] in ("UNKNOWN", "PARTIAL"),
                work_a["completeness"] in ("UNKNOWN", "UNRELATED"),
                work_b["completeness"] in ("UNKNOWN", "UNRELATED"),
            )
            if judgment["verdict"] == "ACCEPTED" and any(blocking):
                judgment["verdict"] = "UNKNOWN"
                judgment["confidence"] = "LOW"
                judgment["reason"] = "accepted verdict blocked by incomplete evidence"
            return json.dumps(judgment, sort_keys=True, separators=(",", ":"))

        result = json.loads(gl.eq_principle.strict_eq(fetch_and_judge))
        verdict = str(result["verdict"]).upper()
        confidence = str(result["confidence"]).upper()

        bounty.observed_verdict = verdict
        bounty.observed_confidence = confidence

        # UNKNOWN / PARTIAL / UNRELATED can never move funds to the hunter.
        eligible = verdict == "ACCEPTED"

        if eligible:
            bounty.status = "ACCEPTED"
            bounty.submission_status = "ACCEPTED"
            bounty.reserved = 0
            bounty.funds_disposition = "PAID_TO_HUNTER"
            self.reserved_bounties = self.reserved_bounties - amount
            _Recipient(hunter).emit_transfer(value=amount)
        else:
            # Funds stay reserved for a later hunter or a funder cancel.
            zero = Address("0x0000000000000000000000000000000000000000")
            bounty.status = "OPEN"
            bounty.submission_status = "REJECTED"
            bounty.hunter = zero
            bounty.work_url_a = ""
            bounty.work_url_b = ""
            bounty.funds_disposition = "RESERVED"

    @gl.public.write
    def cancel(self, bounty_id: str) -> None:
        bounty = self._require_bounty(bounty_id)
        if gl.message.sender_address != bounty.funder:
            raise gl.vm.UserError("only the funder can cancel")
        if bounty.status == "ACCEPTED" or bounty.status == "CANCELLED":
            raise gl.vm.UserError("bounty can no longer be cancelled")
        if bounty.submission_status == "PENDING":
            deadline = int(bounty.deadline_unix)
            if deadline == 0 or self._now() < deadline:
                raise gl.vm.UserError("cannot cancel while a submission is pending review")

        if bounty.reserved != bounty.amount:
            raise gl.vm.UserError("bounty reserve is inconsistent")
        if self.balance < bounty.reserved:
            raise gl.vm.UserError("contract is not solvent for this refund")

        amount = bounty.amount
        funder = bounty.funder
        bounty.status = "CANCELLED"
        bounty.submission_status = "NONE"
        bounty.reserved = 0
        bounty.funds_disposition = "REFUNDED_TO_FUNDER"
        self.reserved_bounties = self.reserved_bounties - amount
        _Recipient(funder).emit_transfer(value=amount)

    @gl.public.view
    def get_bounty(self, bounty_id: str) -> str:
        bounty = self._require_bounty(bounty_id)
        return json.dumps(
            {
                "bounty_id": bounty_id,
                "funder": bounty.funder.as_hex,
                "hunter": bounty.hunter.as_hex,
                "title": bounty.title,
                "spec_text": bounty.spec_text,
                "spec_url_a": bounty.spec_url_a,
                "spec_url_b": bounty.spec_url_b,
                "work_url_a": bounty.work_url_a,
                "work_url_b": bounty.work_url_b,
                "amount": int(bounty.amount),
                "reserved": int(bounty.reserved),
                "deadline_unix": int(bounty.deadline_unix),
                "status": bounty.status,
                "submission_status": bounty.submission_status,
                "observed_verdict": bounty.observed_verdict,
                "observed_confidence": bounty.observed_confidence,
                "funds_disposition": bounty.funds_disposition,
            },
            sort_keys=True,
        )

    @gl.public.view
    def get_bounty_status(self, bounty_id: str) -> str:
        return self._require_bounty(bounty_id).status

    @gl.public.view
    def get_bounty_count(self) -> u256:
        return self.next_bounty_id - 1

    @gl.public.view
    def get_reserved_bounties(self) -> u256:
        return self.reserved_bounties
