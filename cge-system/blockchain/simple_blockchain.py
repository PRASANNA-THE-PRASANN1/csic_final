import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List


class Blockchain:
    """A simple blockchain implementation for audit trail purposes."""

    def __init__(self, data_path: str = None):
        self.data_path = data_path or os.path.join(
            os.path.dirname(__file__), "blockchain_data.json"
        )
        self.chain: List[Dict] = []
        self._load_chain()

    def _load_chain(self):
        """Load chain from disk, or create genesis block."""
        if os.path.exists(self.data_path):
            try:
                with open(self.data_path, "r") as f:
                    data = json.load(f)
                    self.chain = data.get("chain", [])
            except (json.JSONDecodeError, IOError):
                self.chain = []

        if not self.chain:
            self._create_genesis_block()

    def _create_genesis_block(self):
        """Create the first block in the chain."""
        genesis = {
            "index": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"event": "genesis", "message": "CGE System Blockchain Initialized"},
            "previous_hash": "0",
            "nonce": 0,
            "hash": "",
        }
        genesis["hash"] = self.calculate_hash(genesis)
        self.chain = [genesis]
        self._save_chain()

    def calculate_hash(self, block: Dict) -> str:
        """Calculate SHA-256 hash of a block."""
        block_copy = {
            "index": block["index"],
            "timestamp": block["timestamp"],
            "data": block["data"],
            "previous_hash": block["previous_hash"],
            "nonce": block["nonce"],
        }
        block_string = json.dumps(block_copy, sort_keys=True)
        return hashlib.sha256(block_string.encode()).hexdigest()

    def add_block(self, data: Dict[str, Any]) -> Dict:
        """Add a new block to the chain."""
        previous_block = self.chain[-1]

        new_block = {
            "index": len(self.chain),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "previous_hash": previous_block["hash"],
            "nonce": 0,
            "hash": "",
        }

        while True:
            new_block["hash"] = self.calculate_hash(new_block)
            if new_block["hash"].startswith("00"):
                break
            new_block["nonce"] += 1

        self.chain.append(new_block)
        self._save_chain()
        return new_block

    def is_chain_valid(self) -> bool:
        """Validate the entire blockchain integrity."""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            # Recalculate and compare hash
            if current["hash"] != self.calculate_hash(current):
                return False

            # chain linkage
            if current["previous_hash"] != previous["hash"]:
                return False

        return True

    def get_block(self, index: int) -> Dict:
        """Get a specific block by index."""
        if 0 <= index < len(self.chain):
            return self.chain[index]
        raise IndexError(f"Block index {index} out of range (chain length: {len(self.chain)})")

    def _save_chain(self):
        """Persist the chain to disk as JSON."""
        os.makedirs(os.path.dirname(self.data_path), exist_ok=True)
        with open(self.data_path, "w") as f:
            json.dump({"chain": self.chain}, f, indent=2)

    def __len__(self):
        return len(self.chain)

    def __repr__(self):
        return f"<Blockchain(blocks={len(self.chain)})>"
