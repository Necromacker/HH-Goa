"""Ethereum evidence registry client for the local Hardhat chain."""
import hashlib
import json
import os
from pathlib import Path

from web3 import Web3

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOYMENT_PATH = REPO_ROOT / "blockchain" / "deployment.json"
ENV_PATH = REPO_ROOT / "blockchain" / ".env"
ABI = [
    {"inputs": [{"internalType": "bytes32", "name": "contentHash", "type": "bytes32"}, {"internalType": "string", "name": "sourceUrl", "type": "string"}], "name": "registerEvidence", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
    {"inputs": [{"internalType": "bytes32", "name": "contentHash", "type": "bytes32"}], "name": "getEvidence", "outputs": [{"internalType": "address", "name": "submitter", "type": "address"}, {"internalType": "uint256", "name": "recordedAt", "type": "uint256"}, {"internalType": "string", "name": "sourceUrl", "type": "string"}, {"internalType": "bool", "name": "exists", "type": "bool"}], "stateMutability": "view", "type": "function"},
]


def _load_local_blockchain_env() -> None:
    """Load the project's local Hardhat settings without an extra dependency.

    The API is normally launched from the repository root, not through
    Hardhat, so Node's ``dotenv`` loader is not available to this Python
    process. Existing environment variables always take precedence.
    """
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.removeprefix("export ").strip()
        value = value.strip().strip("\"'")
        if key:
            os.environ.setdefault(key, value)

    # Hardhat commonly calls this RPC_URL while the API calls it
    # EVIDENCE_RPC_URL. Support either spelling in the shared .env file.
    if not os.environ.get("EVIDENCE_RPC_URL") and os.environ.get("RPC_URL"):
        os.environ["EVIDENCE_RPC_URL"] = os.environ["RPC_URL"]


_load_local_blockchain_env()

def canonical_payload(post: dict, face_fingerprint: str) -> dict:
    """Only non-sensitive evidence fields enter the stable hashed payload."""
    return {
        "face_fingerprint": face_fingerprint or "",
        "source_url": post.get("url", ""),
        "thumbnail_url": post.get("thumbnail_url", ""),
        "title": post.get("title", ""),
    }

def fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return hashlib.sha256(encoded).hexdigest()

def _client():
    if not DEPLOYMENT_PATH.exists():
        raise RuntimeError("Blockchain contract is not deployed. Run npm install, npm run node, then npm run deploy in blockchain/.")
    private_key = os.environ.get("EVIDENCE_SIGNER_PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("EVIDENCE_SIGNER_PRIVATE_KEY is not set. Use a local Hardhat account only.")
    deployed = json.loads(DEPLOYMENT_PATH.read_text())
    w3 = Web3(Web3.HTTPProvider(os.environ.get("EVIDENCE_RPC_URL", "http://127.0.0.1:8545")))
    if not w3.is_connected():
        raise RuntimeError("Cannot connect to local blockchain at EVIDENCE_RPC_URL.")
    account = w3.eth.account.from_key(private_key)
    contract = w3.eth.contract(address=Web3.to_checksum_address(deployed["contract_address"]), abi=deployed.get("abi", ABI))
    return w3, account, contract

def register(post: dict, face_fingerprint: str) -> dict:
    payload = canonical_payload(post, face_fingerprint)
    content_hash = fingerprint(payload)
    w3, account, contract = _client()
    existing = contract.functions.getEvidence("0x" + content_hash).call()
    if existing[3]:
        return {"already_registered": True, "content_hash": content_hash, "transaction_hash": None, "block_number": None, "contract_address": contract.address, "network": w3.eth.chain_id, "payload": payload}
    tx = contract.functions.registerEvidence("0x" + content_hash, payload["source_url"]).build_transaction({"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": w3.eth.chain_id, "gas": 300000, "gasPrice": w3.eth.gas_price})
    signed = account.sign_transaction(tx)
    receipt = w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction))
    return {"already_registered": False, "content_hash": content_hash, "transaction_hash": receipt.transactionHash.hex(), "block_number": receipt.blockNumber, "contract_address": contract.address, "network": w3.eth.chain_id, "payload": payload}

def verify(post: dict, face_fingerprint: str) -> dict:
    payload = canonical_payload(post, face_fingerprint)
    content_hash = fingerprint(payload)
    w3, _, contract = _client()
    stored = contract.functions.getEvidence("0x" + content_hash).call()
    return {"verified": bool(stored[3]), "calculated_hash": content_hash, "stored_hash": content_hash if stored[3] else None, "source_url": stored[2] if stored[3] else None, "recorded_at": stored[1] if stored[3] else None, "contract_address": contract.address, "network": w3.eth.chain_id, "payload": payload}
