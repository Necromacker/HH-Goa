"""Step 1: Face identification — detect and encode a face from an input image.

Meets HH-Goa Task 3 requirement:
  "Detect and encode a face from an input image (any library acceptable)."

Uses only OpenCV Haar cascade + Pillow + numpy (no dlib build issues on ARM Mac).
Falls back to whole-image encoding if no face found so the pipeline never blocks.

Usage:
    python3 face_detection.py <image_path_or_url> [--out data/faces]
    python3 face_detection.py 'https://.../face.jpg'
    python3 face_detection.py ./my_face.jpg
"""
import argparse
import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image


YUNET_MODEL_URL = (
    "https://github.com/opencv/opencv_zoo/raw/main/models/"
    "face_detection_yunet/face_detection_yunet_2023mar.onnx"
)


def _yunet_model_path() -> Path:
    p = Path(__file__).resolve().parent / "data" / "models" / \
        "face_detection_yunet_2023mar.onnx"
    if not p.is_file():
        p.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(YUNET_MODEL_URL, timeout=120,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        p.write_bytes(r.content)
    return p


def _detect_haar(img) -> list[dict]:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cascade_path = (
        Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    )
    clf = cv2.CascadeClassifier(str(cascade_path))
    faces = clf.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )
    return [{"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            for (x, y, w, h) in faces]


def _detect_yunet(img) -> list[dict]:
    """YuNet DNN detector (OpenCV >= 5 where Haar was removed)."""
    h, w = img.shape[:2]
    model = str(_yunet_model_path())
    det = cv2.FaceDetectorYN_create(model, "", (w, h),
                                    score_threshold=0.5)
    det.setInputSize((w, h))
    ok, faces = det.detect(img)
    if not ok or faces is None:
        return []
    out = []
    for f in faces:
        x, y, bw, bh, score = float(f[0]), float(f[1]), float(f[2]), \
            float(f[3]), float(f[14])
        if score < 0.5 or bw < 10 or bh < 10:
            continue
        out.append({"x": max(0, int(x)), "y": max(0, int(y)),
                    "w": int(bw), "h": int(bh)})
    return out


def detect_faces(image_path: str) -> list[dict]:
    """Detect faces. Haar on OpenCV 4, YuNet DNN on OpenCV 5+. Returns [{x,y,w,h}]."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Cannot read image: {image_path}")
    if hasattr(cv2, "CascadeClassifier"):
        return _detect_haar(img)
    if hasattr(cv2, "FaceDetectorYN_create"):
        return _detect_yunet(img)
    return []


def _dhash(pil_img: "Image.Image") -> str:
    """64-bit difference hash as 16-char hex string."""
    small = pil_img.convert("L").resize((9, 8), Image.BILINEAR)
    px = np.asarray(small, dtype=np.int16)
    diff = px[:, 1:] > px[:, :-1]  # 8x8 booleans
    bits = "".join("1" if b else "0" for b in diff.flatten())
    return f"{int(bits, 2):016x}"


def encode_face(image_path: str, bbox: dict | None = None) -> dict:
    """Crop to bbox (or whole image), return {phash, embedding, bbox}.

    embedding: 32x32 grayscale normalized float vector (1024-d), for
    cosine comparison in Step 2 re-ranking.
    """
    pil = Image.open(image_path).convert("RGB")
    if bbox:
        w, h = pil.size
        x = max(0, bbox["x"])
        y = max(0, bbox["y"])
        x2 = min(w, x + bbox["w"])
        y2 = min(h, y + bbox["h"])
        if x2 > x and y2 > y:
            pil = pil.crop((x, y, x2, y2))
    phash = _dhash(pil)
    emb_img = pil.convert("L").resize((32, 32), Image.BILINEAR)
    emb = np.asarray(emb_img, dtype=np.float32).flatten() / 255.0
    # zero-mean for cosine stability
    emb = emb - emb.mean()
    return {"phash": phash, "embedding": emb.tolist(),
            "bbox": bbox}


def hamming_distance(h1: str, h2: str) -> int:
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def compare_faces(enc1: dict, enc2: dict) -> float:
    """Similarity 0.0-1.0. 1.0 = identical.

    0.7 * hash similarity + 0.3 * embedding cosine similarity.
    """
    hash_sim = 1.0 - hamming_distance(enc1["phash"], enc2["phash"]) / 64.0
    a = np.array(enc1["embedding"], dtype=np.float64)
    b = np.array(enc2["embedding"], dtype=np.float64)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    cos = float(np.dot(a, b) / denom) if denom > 1e-9 else 0.0
    cos_sim = (cos + 1.0) / 2.0  # -1..1 -> 0..1
    return round(0.7 * hash_sim + 0.3 * cos_sim, 4)


def _resolve_input(source: str, out_dir: Path) -> Path:
    """Download URL or validate local path. Returns local image path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if source.startswith("http://") or source.startswith("https://"):
        r = requests.get(source, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        # stable filename from URL hash so re-runs don't duplicate
        name = hashlib.sha256(source.encode()).hexdigest()[:12] + ".jpg"
        dest = out_dir / name
        dest.write_bytes(r.content)
        # validate it opens
        Image.open(dest).verify()
        return dest
    p = Path(source)
    if not p.is_file():
        raise FileNotFoundError(f"Input file not found: {source}")
    return p


def process_face_scan(source: str, out_dir: str = "data/faces") -> dict:
    """End-to-end Step 1: input URL/path -> face crop + encoding.

    Returns dict with keys:
      source, image_path, face_found(bool), faces, query_bbox,
      face_crop_path, query_encoding{phash, embedding}
    """
    out = Path(out_dir)
    local = _resolve_input(source, out)
    faces = detect_faces(str(local))

    img = Image.open(local).convert("RGB")
    if faces:
        # largest face = primary subject
        bbox = max(faces, key=lambda b: b["w"] * b["h"])
        face_found = True
    else:
        w, h = img.size
        bbox = {"x": 0, "y": 0, "w": w, "h": h}
        face_found = False

    x, y, w, h = bbox["x"], bbox["y"], bbox["w"], bbox["h"]
    crop = img.crop((max(0, x), max(0, y),
                     min(img.size[0], x + w), min(img.size[1], y + h)))
    crop_path = out / (Path(local).stem + "_face.jpg")
    crop.save(crop_path, "JPEG")

    encoding = encode_face(str(local), bbox)
    return {
        "source": source,
        "image_path": str(local),
        "image_w": img.size[0],
        "image_h": img.size[1],
        "face_found": face_found,
        "faces": faces,
        "query_bbox": bbox,
        "face_crop_path": str(crop_path),
        "query_encoding": encoding,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Step 1: detect + encode face")
    ap.add_argument("input", help="local image path or public image URL")
    ap.add_argument("--out", default="data/faces", help="output dir")
    args = ap.parse_args()

    try:
        res = process_face_scan(args.input, args.out)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    print(f"image: {res['image_path']}")
    print(f"face_found: {res['face_found']} "
          f"({len(res['faces'])} face(s))")
    print(f"bbox: {res['query_bbox']}")
    print(f"face_crop: {res['face_crop_path']}")
    print(f"phash: {res['query_encoding']['phash']}")
    if not res["face_found"]:
        print("NOTE: no face detected — whole image used as fallback "
              "encoding so pipeline continues.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
