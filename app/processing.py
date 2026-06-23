import os
import cv2
import numpy as np
import pytesseract
from PIL import Image

from app.config import MOBILENET_CLASSES, MODELS_DIR
from app.utils import (
    img_to_b64, adjust_brightness_contrast, deskew,
    rotate_image, check_tesseract
)


def ocr_preprocess(img: np.ndarray, params: dict) -> np.ndarray:
    processed = img.copy()

    if params.get("rotation"):
        processed = rotate_image(processed, params["rotation"])

    if params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0:
        processed = adjust_brightness_contrast(processed, params.get("brightness", 0), params.get("contrast", 0))

    if params["grayscale"]:
        processed = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        if params["deskew"]:
            processed = deskew(processed)
        k = params["blur_kernel"]
        if k % 2 == 0:
            k += 1
        k = max(1, min(31, k))
        processed = cv2.GaussianBlur(processed, (k, k), 0)
        if params["threshold_method"] == "otsu":
            _, processed = cv2.threshold(processed, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        elif params["threshold_method"] == "adaptive":
            block = params["threshold_block"]
            if block % 2 == 0:
                block += 1
            block = max(3, min(99, block))
            processed = cv2.adaptiveThreshold(processed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                               cv2.THRESH_BINARY, block, params["threshold_c"])
        else:
            _, processed = cv2.threshold(processed, 128, 255, cv2.THRESH_BINARY)
    else:
        if params["deskew"]:
            processed = deskew(processed)

    return processed


def read_image(image_path: str) -> np.ndarray:
    img = cv2.imread(image_path)
    if img is None:
        pil_img = Image.open(image_path)
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return img


def process_ocr(image_path: str, params: dict) -> dict:
    img = read_image(image_path)
    original_b64 = img_to_b64(img)

    t_err = check_tesseract()
    if t_err:
        return {"error": t_err, "mode": "ocr",
                "original_image": original_b64, "processed_image": original_b64,
                "confidence": 0, "passed": False, "text": "",
                "confidence_details": [], "histogram": {}, "checks": {}}

    processed = ocr_preprocess(img, params)
    processed_b64 = img_to_b64(processed)

    lang = params.get("lang", "eng")
    psm = params.get("psm", "6")
    ocr_config = f"--psm {psm}"
    if lang != "eng":
        ocr_config = f"--psm {psm} -l {lang}"

    text = pytesseract.image_to_string(processed, config=ocr_config)
    conf_data = pytesseract.image_to_data(processed, config=ocr_config, output_type=pytesseract.Output.DICT)
    char_confidences = []
    for i in range(len(conf_data["text"])):
        txt = conf_data["text"][i].strip()
        if txt and conf_data["conf"][i] != -1:
            char_confidences.append({"text": txt, "conf": int(conf_data["conf"][i])})
    conf_values = [c["conf"] for c in char_confidences]
    avg_confidence = round(sum(conf_values) / len(conf_values), 2) if conf_values else 0
    bins = {"90-100": 0, "80-89": 0, "70-79": 0, "60-69": 0, "<60": 0}
    for c in conf_values:
        if c >= 90:
            bins["90-100"] += 1
        elif c >= 80:
            bins["80-89"] += 1
        elif c >= 70:
            bins["70-79"] += 1
        elif c >= 60:
            bins["60-69"] += 1
        else:
            bins["<60"] += 1
    checks = {"library_integration": True, "preprocessing": params.get("grayscale", False) or params.get("deskew", False) or params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0,
              "accuracy": avg_confidence >= 80, "visual_confirmation": len(text.strip()) > 0}
    return {"text": text.strip(), "confidence": avg_confidence, "passed": avg_confidence >= 80,
            "mode": "ocr", "original_image": original_b64, "processed_image": processed_b64,
            "confidence_details": char_confidences[:80], "histogram": bins, "checks": checks}


def process_detection(image_path: str, params: dict) -> dict:
    img = read_image(image_path)
    original_b64 = img_to_b64(img)
    h, w = img.shape[:2]
    prototxt = os.path.join(MODELS_DIR, "deploy.prototxt")
    caffemodel = os.path.join(MODELS_DIR, "mobilenet_ssd.caffemodel")
    if not (os.path.exists(prototxt) and os.path.exists(caffemodel)):
        return {"error": "Model files not found. Run download_models.py", "mode": "detection",
                "original_image": original_b64, "processed_image": original_b64,
                "confidence": 0, "passed": False, "count": 0, "objects": [], "checks": {}}

    processed = img.copy()
    preproc_applied = params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0
    if preproc_applied:
        processed = adjust_brightness_contrast(processed, params.get("brightness", 0), params.get("contrast", 0))

    net = cv2.dnn.readNetFromCaffe(prototxt, caffemodel)
    blob = cv2.dnn.blobFromImage(cv2.resize(processed, (300, 300)), 0.007843, (300, 300), 127.5)
    net.setInput(blob)
    detections = net.forward()
    annotated = processed.copy()
    results = []
    for i in range(detections.shape[2]):
        conf = float(detections[0, 0, i, 2])
        if conf > 0.5:
            class_id = int(detections[0, 0, i, 1])
            label = MOBILENET_CLASSES[class_id] if 0 <= class_id < len(MOBILENET_CLASSES) else f"class_{class_id}"
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            (x1, y1, x2, y2) = box.astype("int")
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (74, 222, 128), 3)
            display_label = f"{label}: {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(display_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(annotated, (x1, y1 - th - 8), (x1 + tw + 8, y1), (74, 222, 128), -1)
            cv2.putText(annotated, display_label, (x1 + 4, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (22, 101, 52), 2)
            results.append({"class": label, "confidence": round(conf * 100, 2),
                            "bbox": [int(x1), int(y1), int(x2), int(y2)]})
    avg_conf = round(sum(r["confidence"] for r in results) / len(results), 2) if results else 0
    processed_b64 = img_to_b64(annotated)
    checks = {"library_integration": True, "preprocessing": preproc_applied,
              "accuracy": avg_conf >= 80 if results else False, "visual_confirmation": len(results) > 0}
    return {"objects": results, "count": len(results), "confidence": avg_conf,
            "passed": avg_conf >= 80 if results else False, "mode": "detection",
            "original_image": original_b64, "processed_image": processed_b64, "checks": checks}


def process_barcode(image_path: str, params: dict) -> dict:
    img = read_image(image_path)
    original_b64 = img_to_b64(img)

    try:
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError:
        return {"error": "pyzbar not installed. Run: pip install pyzbar", "mode": "barcode",
                "original_image": original_b64, "processed_image": original_b64,
                "confidence": 0, "passed": False, "count": 0, "barcodes": [], "checks": {}}

    processed = img.copy()
    if params.get("brightness", 0) != 0 or params.get("contrast", 0) != 0:
        processed = adjust_brightness_contrast(processed, params.get("brightness", 0), params.get("contrast", 0))
    processed_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)

    barcodes = pyzbar_decode(processed_gray)
    annotated = img.copy()
    results = []
    for bc in barcodes:
        (x, y, w, h) = bc.rect
        cv2.rectangle(annotated, (x, y), (x + w, y + h), (74, 222, 128), 3)
        data = bc.data.decode("utf-8", errors="replace")
        bc_type = bc.type
        label = f"{bc_type}: {data[:30]}"
        cv2.putText(annotated, label, (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (22, 101, 52), 2)
        results.append({"type": bc_type, "data": data, "bbox": [x, y, x + w, y + h]})

    confidence = 100 if results else 0
    processed_b64 = img_to_b64(annotated)
    text_output = "\n".join([f"[{r['type']}] {r['data']}" for r in results])
    checks = {"library_integration": True, "preprocessing": True,
              "accuracy": len(results) > 0, "visual_confirmation": len(results) > 0}
    return {"barcodes": results, "count": len(results), "confidence": confidence,
            "passed": len(results) > 0, "mode": "barcode", "text": text_output,
            "original_image": original_b64, "processed_image": processed_b64, "checks": checks}
