# Face Trace: Face Identification & Blockchain Verification

Face Trace is an HH Goa 2026 Task 3 pipeline:

1. Detect and encode the largest face in a public image URL.
2. Search Google Lens and Yandex, filter returned social-media URLs, and rank them with the face fingerprint.
3. Select a discovered post and record a SHA-256 fingerprint of its evidence on a local Ethereum blockchain.
4. Recreate the fingerprint and check it against the on-chain record.

Only the fingerprint and source URL are stored on-chain. No face embedding, image, full post, or biometric record is stored there.

## Stack

- FastAPI, OpenCV, Selenium, Google Lens, Yandex, Python `web3`
- React / Vite
- Hardhat local Ethereum network and `EvidenceRegistry.sol`

## Run

Install dependencies:

```bash
python3 -m pip install -r backend/requirements.txt
cd frontend && npm install
cd ../blockchain && npm install
```

Start local Ethereum in terminal one:

```bash
cd blockchain
npm run node
```

Copy a private key printed by Hardhat (it is safe only for this disposable local network). In terminal two:

```bash
cd blockchain
cp .env.example .env
# Add EVIDENCE_SIGNER_PRIVATE_KEY=<your local Hardhat private key> to .env
set -a && source .env && set +a
npm run deploy
```

Deployment writes `blockchain/deployment.json`, which the API reads automatically. Start the API in terminal three:

```bash
python3 backend/server.py
```

The backend automatically reads `blockchain/.env`; environment variables set
by your shell still take precedence.

Start the UI in terminal four:

```bash
cd frontend
npm run dev
```

## Project layout

```
HH-Goa/
├── frontend/     # React / Vite user interface
├── backend/      # FastAPI app and Python face-search pipeline
├── blockchain/   # Hardhat contract and deployment scripts
├── data/         # generated local images, face crops, and search results
└── README.md
```

Set `CHROMEDRIVER_PATH` if ChromeDriver is installed somewhere other than
`chromedriver-mac-arm64/chromedriver`.

## Demo flow

1. In **01 Search**, paste a public image URL containing a face.
2. The app detects/encodes the face and runs live reverse-image search.
3. In **02 Results**, choose a real social-media result returned by that search.
4. In **03 Verify**, click **Record on blockchain**.
5. Click **Verify record** to compare a newly calculated evidence hash with the on-chain record.

The SHA-256 evidence payload uses stable, sorted JSON:

```json
{
  "face_fingerprint": "face image hash only",
  "source_url": "selected result URL",
  "thumbnail_url": "selected result thumbnail URL",
  "title": "selected result title"
}
```

Changing any included value changes the hash and causes verification to fail.

## Limitations and responsible use

- Use only public images and material you are authorized to process. Do not use this for surveillance or non-consensual identification.
- Search engines can rate-limit/block automated requests or return no social result.
- A public image URL is needed for live reverse search. Local uploads can be face-scanned but cannot be sent to Lens/Yandex as a public URL.
- The OpenCV encoding is a demo-ranking signal, not production biometric recognition.
- Hardhat is a local simulated Ethereum network; restarting it clears records.
