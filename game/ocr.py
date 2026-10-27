"""Lightweight OpenCV + Tesseract recognizer for photographed Sudoku grids."""
import shutil
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np


def _largest_grid(gray):
    """寻找最大四边形并做透视矫正，未识别到时退化为等比网格。"""
    blurred = cv2.GaussianBlur(gray, (7, 7), 0)
    threshold = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                      cv2.THRESH_BINARY_INV, 11, 2)
    contours, _ = cv2.findContours(threshold, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        perimeter = cv2.arcLength(contour, True)
        corners = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(corners) == 4 and cv2.contourArea(corners) > gray.size * .15:
            points = corners.reshape(4, 2).astype("float32")
            sums, diffs = points.sum(1), np.diff(points, axis=1).reshape(-1)
            ordered = np.array([points[np.argmin(sums)], points[np.argmin(diffs)],
                                points[np.argmax(sums)], points[np.argmax(diffs)]], dtype="float32")
            return cv2.warpPerspective(gray, cv2.getPerspectiveTransform(
                ordered, np.array([[0, 0], [899, 0], [899, 899], [0, 899]], dtype="float32")), (900, 900))
    return cv2.resize(gray, (900, 900))


def recognize_grid(path):
    """逐格识别 1–9；缺少 Tesseract 时返回可人工填写的空网格。"""
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise ValueError("无法读取图片，请换用清晰的 JPG 或 PNG")
    grid_image = _largest_grid(image)
    executable = shutil.which("tesseract")
    if not executable:
        return [[0] * 9 for _ in range(9)], "未找到 Tesseract，已创建空白校正表，请手动填写"
    result = []
    with tempfile.TemporaryDirectory(prefix="sudoku-ocr-") as temp_dir:
        temp = Path(temp_dir)
        # 切掉每格边缘可减少网格线对单字符 OCR 的干扰。
        for row in range(9):
            values = []
            for col in range(9):
                cell = grid_image[row * 100 + 12:(row + 1) * 100 - 12,
                                  col * 100 + 12:(col + 1) * 100 - 12]
                cell = cv2.resize(cell, (180, 180))
                cell = cv2.threshold(cell, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
                target = temp / f"{row}-{col}.png"
                cv2.imwrite(str(target), cell)
                run = subprocess.run([executable, str(target), "stdout", "--psm", "10",
                                      "-c", "tessedit_char_whitelist=123456789"],
                                     capture_output=True, text=True, timeout=8)
                text = "".join(ch for ch in run.stdout if ch in "123456789")
                values.append(int(text[0]) if text else 0)
            result.append(values)
    return result, "OCR 已完成，请逐格核对；空格会在校正页显示为空白"
