
from pathlib import Path
from PIL import Image, UnidentifiedImageError


def check_image(image_path):
    """Бесплатная техническая проверка изображения."""

    image_path = Path(image_path)

    result = {
        "file": image_path.name,
        "status": "FAIL",
        "width": None,
        "height": None,
        "format": None,
        "errors": [],
    }

    if not image_path.is_file():
        result["errors"].append(
            "Изображение не найдено"
        )
        return result

    try:
        with Image.open(image_path) as img:
            width, height = img.size
            image_format = img.format

            result["width"] = width
            result["height"] = height
            result["format"] = image_format

            if image_format not in ("PNG", "JPEG"):
                result["errors"].append(
                    "Формат должен быть PNG или JPEG"
                )


            if width >= height:
                result["errors"].append(
                    "Изображение должно быть вертикальным"
                )

            # Эталон Playrix: 430 × 480, пропорции 43:48.
            # Допускаем погрешность до 1 пикселя
            # при пропорциональном масштабировании.

            expected_ratio = 43 / 48
            actual_ratio = width / height
            ratio_tolerance = 0.05

            if abs(actual_ratio - expected_ratio) / expected_ratio > ratio_tolerance:
                result["errors"].append(
                    "Неверные пропорции: требуется 43:48 "
                    "(допустимое отклонение до 5%)"
                )

            if width < 430 or height < 480:
                result["errors"].append(
                    "Недостаточное разрешение: минимум 430×480"
                )


            img.verify()

    except (UnidentifiedImageError, OSError, ValueError) as error:
        result["errors"].append(
            f"Не удалось прочитать изображение: {error}"
        )

    if not result["errors"]:
        result["status"] = "PASS"

    return result
