// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// Stores a content fingerprint, not the post itself or biometric data.
contract EvidenceRegistry {
    struct Evidence {
        address submitter;
        uint256 recordedAt;
        string sourceUrl;
        bool exists;
    }

    mapping(bytes32 => Evidence) private evidence;
    event EvidenceRecorded(bytes32 indexed contentHash, address indexed submitter, string sourceUrl, uint256 recordedAt);

    function registerEvidence(bytes32 contentHash, string calldata sourceUrl) external {
        require(!evidence[contentHash].exists, "Evidence already recorded");
        evidence[contentHash] = Evidence(msg.sender, block.timestamp, sourceUrl, true);
        emit EvidenceRecorded(contentHash, msg.sender, sourceUrl, block.timestamp);
    }

    function getEvidence(bytes32 contentHash) external view returns (address submitter, uint256 recordedAt, string memory sourceUrl, bool exists) {
        Evidence memory record = evidence[contentHash];
        return (record.submitter, record.recordedAt, record.sourceUrl, record.exists);
    }
}
