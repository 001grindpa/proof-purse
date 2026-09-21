import { createClient } from "https://esm.sh/genlayer-js@0.18.0?bundle";
import { studionet } from "https://esm.sh/genlayer-js@0.18.0/chains?bundle";

const CONTRACT_ADDRESS = "0x97298FdFf27aE250e8194a7cC66ea82975ea2B36";
const RPC_URL = "https://studio.genlayer.com/api";
const CHAIN_ID = studionet.id;
const CHAIN_HEX = `0x${Number(CHAIN_ID).toString(16)}`;
const EXPLORER = "https://explorer-studio.genlayer.com";
const ZERO = "0x0000000000000000000000000000000000000000";
const WALLET_KEY = "proofpurse.wallet";
const WALLET_RDNS_KEY = "proofpurse.wallet.rdns";
const VIEW_KEY = "proofpurse.view";
const THEME_KEY = "proofpurse.theme";

const CODE_HOSTS = [
    "github.com",
    "gitlab.com",
    "bitbucket.org",
    "codeberg.org",
    "sr.ht",
    "git.sr.ht",
    "gist.github.com",
    "raw.githubusercontent.com",
];

const state = {
    account: null,
    provider: null,
    readClient: createClient({ chain: studionet, endpoint: RPC_URL, account: ZERO }),
    writeClient: null,
};

const wallets = [];
window.addEventListener("eip6963:announceProvider", (event) => {
    const { info, provider } = event.detail || {};
    if (!provider || !info?.rdns) return;
    if (wallets.some((w) => w.rdns === info.rdns)) return;
    wallets.push({ rdns: info.rdns, name: info.name || info.rdns, provider });
});
window.dispatchEvent(new Event("eip6963:requestProvider"));

const $ = (id) => document.getElementById(id);

function setStatus(msg, kind = "") {
    const el = $("status-msg");
    el.textContent = msg;
    el.style.color = kind === "err" ? "#f07178" : kind === "ok" ? "#7fd99a" : "#9aa3b2";
}

function showTx(hash) {
    const box = $("tx-link");
    const a = $("tx-hash") || box;
    a.href = `${EXPLORER}/tx/${hash}`;
    a.textContent = hash;
    box.classList.remove("hidden");
}

function formButton(form) {
    return form.querySelector("button[type='submit']");
}

function setBusy(button, on) {
    if (!button) return;
    button.disabled = on;
    button.classList.toggle("loading", on);
}

function formatTxError(err) {
    return err?.shortMessage || err?.details || err?.message || String(err);
}

function parseGen(value) {
    const normalized = value.trim();
    if (!/^\d+(\.\d{1,18})?$/.test(normalized) || Number(normalized) <= 0) {
        throw new Error("Amount must be a positive GEN value.");
    }
    const [whole, fraction = ""] = normalized.split(".");
    return BigInt(whole) * 1000000000000000000n + BigInt(fraction.padEnd(18, "0"));
}

function formatGen(raw) {
    try {
        const n = BigInt(String(raw));
        const whole = n / 1000000000000000000n;
        const frac = (n % 1000000000000000000n).toString().padStart(18, "0").replace(/0+$/, "");
        return frac ? `${whole}.${frac} GEN` : `${whole} GEN`;
    } catch {
        return String(raw);
    }
}

function parseMaybeJson(value) {
    if (value && typeof value === "object") return value;
    if (typeof value === "string") {
        try {
            return JSON.parse(value);
        } catch {
            return { raw: value };
        }
    }
    return { raw: value };
}

function hostOf(url) {
    try {
        return new URL(url).hostname.toLowerCase().replace(/^www\./, "");
    } catch {
        return "";
    }
}

function isCodeHost(url) {
    const host = hostOf(url);
    return CODE_HOSTS.some((h) => host === h || host.endsWith("." + h));
}

function deadlineUnix() {
    const raw = $("deadline").value;
    if (!raw) throw new Error("Deadline is required.");
    const ms = Date.parse(raw);
    if (Number.isNaN(ms)) throw new Error("Deadline is invalid.");
    return String(Math.floor(ms / 1000));
}

function showLanding() {
    $("landing-view").classList.add("view-active");
    $("landing-view").classList.remove("view-hidden");
    $("app-view").classList.add("view-hidden");
    $("app-view").classList.remove("view-active");
    localStorage.setItem(VIEW_KEY, "landing");
}

function showApp() {
    $("landing-view").classList.add("view-hidden");
    $("landing-view").classList.remove("view-active");
    $("app-view").classList.remove("view-hidden");
    $("app-view").classList.add("view-active");
    localStorage.setItem(VIEW_KEY, "app");
    refreshStats();
}

function applyTheme(theme) {
    const light = theme === "light";
    document.body.classList.toggle("app-theme-light", light);
    const toggle = $("theme-toggle-btn");
    toggle?.setAttribute("aria-pressed", String(light));
    toggle?.setAttribute("aria-label", light ? "Switch to dark theme" : "Switch to light theme");
    const icon = toggle?.querySelector(".theme-toggle-icon");
    if (icon) icon.textContent = light ? "☾" : "☼";
}

function setConnectedUi(account) {
    const connect = $("connect-btn");
    connect.textContent = `${account.slice(0, 6)}…${account.slice(-4)}`;
    $("connect-btn").classList.add("hidden");
    $("disconnect-btn").classList.remove("hidden");
}

function setDisconnectedUi() {
    $("connect-btn").textContent = "Connect wallet";
    $("connect-btn").classList.remove("hidden");
    $("disconnect-btn").classList.add("hidden");
}

function pickProvider(preferredRdns) {
    const list = [...wallets];
    if (window.ethereum && !list.some((w) => w.provider === window.ethereum)) {
        list.push({ rdns: "injected", name: "Injected", provider: window.ethereum });
    }
    if (!list.length) throw new Error("No injected wallet found.");
    if (preferredRdns) {
        const match = list.find((w) => w.rdns === preferredRdns);
        if (match) return match;
    }
    return list.find((w) => /metamask/i.test(`${w.rdns} ${w.name}`)) || list[0];
}

async function ensureNetwork(provider) {
    const current = await provider.request({ method: "eth_chainId" });
    if (Number.parseInt(String(current), 16) !== Number(CHAIN_ID)) {
        try {
            await provider.request({
                method: "wallet_switchEthereumChain",
                params: [{ chainId: CHAIN_HEX }],
            });
        } catch (error) {
            if ((error?.code ?? error?.data?.originalError?.code) === 4902) {
                await provider.request({
                    method: "wallet_addEthereumChain",
                    params: [{
                        chainId: CHAIN_HEX,
                        chainName: "GenLayer Studionet",
                        nativeCurrency: { name: "GEN", symbol: "GEN", decimals: 18 },
                        rpcUrls: [RPC_URL],
                        blockExplorerUrls: [EXPLORER],
                    }],
                });
            } else {
                throw error;
            }
        }
    }
}

async function read(method, args = []) {
    return state.readClient.readContract({
        address: CONTRACT_ADDRESS,
        functionName: method,
        args,
        stateStatus: "accepted",
        account: state.account || ZERO,
    });
}

async function sendWrite(functionName, args, value = 0n) {
    if (!state.account) throw new Error("Connect a wallet first.");
    const provider = state.provider || window.ethereum;
    state.writeClient = createClient({ chain: studionet, account: state.account, provider });
    return state.writeClient.writeContract({
        address: CONTRACT_ADDRESS,
        functionName,
        args,
        value,
    });
}

async function refreshStats() {
    try {
        const [count, reserved] = await Promise.all([
            read("get_bounty_count"),
            read("get_reserved_bounties"),
        ]);
        $("stat-count").textContent = String(count ?? "0");
        $("stat-reserved").textContent = formatGen(reserved ?? 0);
    } catch {
        $("stat-count").textContent = "—";
        $("stat-reserved").textContent = "—";
    }
}

async function connectWallet(preferredAccount, preferredRdns) {
    const selected = pickProvider(preferredRdns || localStorage.getItem(WALLET_RDNS_KEY));
    const accounts = await selected.provider.request({ method: "eth_requestAccounts" });
    if (!accounts?.length) throw new Error("No account returned.");
    const account =
        preferredAccount && accounts.some((a) => a.toLowerCase() === preferredAccount.toLowerCase())
            ? accounts.find((a) => a.toLowerCase() === preferredAccount.toLowerCase())
            : accounts[0];
    await ensureNetwork(selected.provider);
    state.account = account;
    state.provider = selected.provider;
    localStorage.setItem(WALLET_KEY, account);
    localStorage.setItem(WALLET_RDNS_KEY, selected.rdns);
    setConnectedUi(account);
    setStatus(`Connected on StudioNet.`, "ok");
}

function disconnectWallet() {
    state.account = null;
    state.provider = null;
    state.writeClient = null;
    localStorage.removeItem(WALLET_KEY);
    localStorage.removeItem(WALLET_RDNS_KEY);
    setDisconnectedUi();
    setStatus("Disconnected.");
}

async function restoreWallet() {
    const stored = localStorage.getItem(WALLET_KEY);
    if (!stored) return refreshStats();
    try {
        const selected = pickProvider(localStorage.getItem(WALLET_RDNS_KEY));
        const silent = await selected.provider.request({ method: "eth_accounts" });
        if (silent?.length) await connectWallet(stored, selected.rdns);
        else setDisconnectedUi();
    } catch {
        setDisconnectedUi();
    }
    await refreshStats();
}

function requireCodePair(urlA, urlB, label) {
    if (!urlA.toLowerCase().startsWith("https://") || !urlB.toLowerCase().startsWith("https://")) {
        throw new Error(`${label} must be https URLs.`);
    }
    if (!isCodeHost(urlA) || !isCodeHost(urlB)) {
        throw new Error(`${label} must be GitHub, GitLab, Bitbucket, Codeberg, or SourceHut.`);
    }
    if (hostOf(urlA) === hostOf(urlB)) {
        throw new Error(`${label} must come from two different hosts.`);
    }
}

$("contract-link").href = `${EXPLORER}/address/${CONTRACT_ADDRESS}`;
$("contract-link").textContent = CONTRACT_ADDRESS;

document.querySelectorAll(".enter-app-trigger").forEach((button) => button.addEventListener("click", showApp));
$("back-landing").addEventListener("click", showLanding);
$("theme-toggle-btn").addEventListener("click", () => {
    const next = localStorage.getItem(THEME_KEY) === "light" ? "dark" : "light";
    localStorage.setItem(THEME_KEY, next);
    applyTheme(next);
});
$("connect-btn").addEventListener("click", () => connectWallet().then(refreshStats).catch((err) => setStatus(formatTxError(err), "err")));
$("disconnect-btn").addEventListener("click", disconnectWallet);

async function runWrite(form, fn) {
    const btn = formButton(form);
    try {
        setBusy(btn, true);
        if (!state.account) await connectWallet();
        await fn();
    } catch (err) {
        setStatus(formatTxError(err), "err");
    } finally {
        setBusy(btn, false);
    }
}

$("create-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runWrite(event.currentTarget, async () => {
        const title = $("title").value.trim();
        const spec = $("spec-text").value.trim();
        const a = $("spec-a").value.trim();
        const b = $("spec-b").value.trim();
        if (title.length < 4 || spec.length < 12) throw new Error("Title and spec are too short.");
        requireCodePair(a, b, "Spec URLs");
        const hash = await sendWrite(
            "create_bounty",
            [title, spec, a, b, deadlineUnix()],
            parseGen($("amount").value)
        );
        showTx(hash);
        setStatus("Bounty submitted. Wait for Accepted, then inspect the next ID.", "ok");
        await refreshStats();
    });
});

$("submit-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runWrite(event.currentTarget, async () => {
        const id = $("submit-id").value.trim();
        const a = $("work-a").value.trim();
        const b = $("work-b").value.trim();
        if (!id) throw new Error("Bounty ID is required.");
        requireCodePair(a, b, "Work URLs");
        const hash = await sendWrite("submit_work", [id, a, b], 0n);
        showTx(hash);
        setStatus("Work submitted.", "ok");
    });
});

$("resolve-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runWrite(event.currentTarget, async () => {
        const id = $("resolve-id").value.trim();
        if (!id) throw new Error("Bounty ID is required.");
        const hash = await sendWrite("resolve", [id], 0n);
        showTx(hash);
        setStatus("Resolve submitted. Inspect after Accepted.", "ok");
    });
});

$("cancel-form").addEventListener("submit", (event) => {
    event.preventDefault();
    runWrite(event.currentTarget, async () => {
        const id = $("cancel-id").value.trim();
        if (!id) throw new Error("Bounty ID is required.");
        const hash = await sendWrite("cancel", [id], 0n);
        showTx(hash);
        setStatus("Cancel submitted.", "ok");
        await refreshStats();
    });
});

$("lookup-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const out = $("lookup-out");
    const btn = formButton(event.currentTarget);
    try {
        setBusy(btn, true);
        const id = $("lookup-id").value.trim();
        if (!id) throw new Error("Bounty ID is required.");
        out.classList.remove("empty");
        out.textContent = JSON.stringify(parseMaybeJson(await read("get_bounty", [id])), null, 2);
        setStatus(`Loaded bounty ${id}.`, "ok");
    } catch (err) {
        out.textContent = formatTxError(err);
        setStatus(formatTxError(err), "err");
    } finally {
        setBusy(btn, false);
    }
});

applyTheme(localStorage.getItem(THEME_KEY) || "dark");
if (localStorage.getItem(VIEW_KEY) === "app") showApp();
restoreWallet();