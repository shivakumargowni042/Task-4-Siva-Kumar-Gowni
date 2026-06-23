import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.environ.get("DECODELABS_DB", os.path.join(BASE_DIR, "decodelabs.db"))
MODELS_DIR = os.path.join(BASE_DIR, "models")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "bmp", "tiff", "webp"}
ALLOWED_MIME_PREFIXES = {"image/"}

LANG_MAP = {
    "eng": "English", "ara": "Arabic", "chi_sim": "Chinese (Simplified)",
    "chi_tra": "Chinese (Traditional)", "fra": "French", "deu": "German",
    "hin": "Hindi", "ita": "Italian", "jpn": "Japanese", "kor": "Korean",
    "por": "Portuguese", "rus": "Russian", "spa": "Spanish", "tur": "Turkish"
}

PSM_MAP = {
    "6": "Uniform text block (default)",
    "3": "Fully automatic",
    "4": "Single column",
    "7": "Single text line",
    "8": "Single word",
    "11": "Sparse text",
    "12": "Sparse text with OSD"
}

MOBILENET_CLASSES = [
    "background", "aeroplane", "bicycle", "bird", "boat",
    "bottle", "bus", "car", "cat", "chair",
    "cow", "diningtable", "dog", "horse", "motorbike",
    "person", "pottedplant", "sheep", "sofa", "train", "tvmonitor"
]
