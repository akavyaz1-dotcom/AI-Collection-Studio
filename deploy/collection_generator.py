
import os
import json
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv

BASE = Path(__file__).resolve().parent
BASE = BASE.parent
load_dotenv(BASE / ".env")

KEY = os.getenv("GIGACHAT_AUTH_KEY")
CERT = BASE / "russian_trusted_root_ca_pem.crt"

if not KEY:
    raise SystemExit("Ключ GigaChat не найден в .env")

if not CERT.is_file():
    raise SystemExit("Сертификат GigaChat не найден")

requirements_path = BASE / "artist_requirements.json"

if not requirements_path.is_file():
    raise SystemExit("Не найден artist_requirements.json")

requirements = json.loads(
    requirements_path.read_text(encoding="utf-8")
)

# Пока используем фиксированный жанр.
# Позже добавим ввод жанра и пожеланий продюсера.

def generate_collections(genre, description, variants_count):
    genre = genre.strip()
    if not genre:
        raise ValueError("Укажите жанр проекта.")

    if not isinstance(variants_count, int) or not 3 <= variants_count <= 5:
        raise ValueError("Количество коллекций должно быть от 3 до 5.")

    producer_wishes = description.strip() or (
        "Узнаваемые предметы, разнообразные силуэты, "
        "единый художественный стиль."
    )

    prompt = f"""
    Ты — Senior Game Designer и Art Producer,
    разрабатывающий коллекционные иллюстрации
    для казуальной мобильной игры.

    ЗАДАЧА:
    Предложи {variants_count} разных варианта коллекции
    в жанре {genre}.

    ПОЖЕЛАНИЯ ПРОДЮСЕРА:
    {producer_wishes}

    ТРЕБОВАНИЯ:

    1. В каждом варианте ровно 10 карточек.
    2. Каждая карточка изображает конкретный
       узнаваемый предмет или объект.
    3. Используй категории 1, 2, 3 и 4.
    4. Каждая категория должна присутствовать.
    5. Категории должны соответствовать
       сложности окружения.
    6. Не создавай золотые карточки.
    7. Предметы внутри варианта не должны повторяться.
    8. Варианты должны заметно отличаться друг от друга.
    9. Все предметы должны соответствовать жанру.
    10. Описания должны быть пригодны для
        дальнейшей генерации изображений.

    ОБЯЗАТЕЛЬНЫЕ ОГРАНИЧЕНИЯ ДЛЯ ПРЕДМЕТОВ:

    1. Каждая карточка должна изображать один конкретный
       физический предмет или объект.

    2. Запрещены:
       - люди и персонажи;
       - животные и существа;
       - призраки и человеческие силуэты;
       - следы, тени и абстрактные явления;
       - сюжетные сцены без конкретного главного предмета;
       - неопределённые объекты вроде "Murder Weapon"
         без указания конкретного предмета.

    3. Название карточки должно однозначно определять,
       что художник должен нарисовать.

    4. Для категории 1:
       предмет парит в воздухе, фон простой.

    5. Для категории 2:
       предмет расположен на поверхности, фон простой.

    6. Для категории 3:
       предмет расположен на реалистичной поверхности,
       присутствует простое объёмное окружение.

    7. Для категории 4:
       предмет находится в реалистичном окружении,
       но остаётся главным визуальным акцентом.

    8. Предмет должен хорошо читаться на экране телефона.
       Избегай чрезмерно мелких объектов и деталей.

    9. Не повторяй одинаковые предметы между вариантами
       одной генерации.

    10. Описания должны соответствовать единому стилю:
        premium colorful stylized 3D casual mobile game art,
        simplified geometry, readable silhouette,
        polished materials, soft directional lighting.

    ПРАВИЛО РАЗДЕЛЕНИЯ ОПИСАНИЯ И ОКРУЖЕНИЯ:

    Поле description описывает только главный объект:
    его форму, материал, цвет, конструкцию и детали.

    Не указывай в description фон, поверхность,
    градиенты, узоры или расположение объекта.

    Для категорий 3 и 4 тематическое окружение
    описывай исключительно в поле environment.

    Для категорий 1 и 2 фон и композиция
    будут задаваться отдельно.

    11. Для каждого варианта придумай самостоятельную
        тематическую концепцию в рамках заданного жанра.


ПРИНЦИПЫ ФОРМИРОВАНИЯ НАБОРА:

1. Каждый вариант должен представлять собой цельный
   тематический сет из 10 объектов, а не случайный
   перечень предметов одного жанра.

2. Раскрывай тему через разные смысловые роли:
   - знаковые символы темы;
   - инструменты и оборудование;
   - инфраструктуру и элементы окружения;
   - личные вещи и аксессуары;
   - атмосферные и характерные детали.
   Не обязательно использовать все группы,
   если они не соответствуют выбранной теме.

3. Избегай функциональных повторов.
   Предметы с разными названиями, но одинаковым
   назначением, считаются смысловыми дублями.

4. Сочетай очевидные узнаваемые символы темы
   с менее ожидаемыми, но характерными деталями.
   Не выбирай необычные предметы только ради
   оригинальности.

5. Обеспечивай разнообразие визуальных силуэтов
   и масштабов: компактные предметы, оборудование,
   крупные объекты и сооружения, если это уместно.

6. Каждый предмет должен вносить новую информацию
   о теме набора и дополнять остальные девять.

7. Набор должен создавать целостное представление
   о месте, деятельности, событии или ситуации.

8. Не включай предметы, которые относятся только
   к широкому жанру, но слабо связаны с конкретной
   концепцией варианта.

САМОПРОВЕРКА ПЕРЕД ОТВЕТОМ:

Для каждого варианта мысленно проверь:
- Все ли 10 объектов относятся к одной концепции?
- Раскрывают ли они разные аспекты темы?
- Нет ли функциональных или визуальных дублей?
- Есть ли узнаваемые символы темы?
- Различаются ли силуэты и масштабы объектов?
- Можно ли представить тему по этим 10 предметам
  без дополнительных объяснений?
- Присутствуют ли все четыре категории?
- Подходит ли каждый объект для изображения
  на небольшом экране телефона?

Если обнаружены недостатки, самостоятельно
замени проблемные предметы до выдачи JSON.
Не включай результаты самопроверки в JSON.


    КАТЕГОРИИ:

    {json.dumps(
        requirements["category_rules"],
        ensure_ascii=False,
        indent=2
    )}

    ХУДОЖЕСТВЕННЫЙ СТИЛЬ:

    {json.dumps(
        requirements["reference_style"],
        ensure_ascii=False,
        indent=2
    )}

    ФОРМАТ ОТВЕТА:

    Верни исключительно JSON без Markdown.

    {{
      "genre": "{genre}",
      "variants": [
        {{
          "variant_id": 1,
          "concept": "Название концепции",
          "cards": [
            {{
              "name": "Название предмета на английском",
              "category": 1,
              "description": "Описание на английском",
              "environment": ""
            }}
          ]
        }}
      ]
    }}

    ВАЖНО:
    - В variants должно быть ровно {variants_count} элементов.
    - В cards каждого варианта должно быть ровно 10 элементов.
    - category — целое число от 1 до 4.
    - Для категорий 3 и 4 указывай environment.
    - Для категорий 1 и 2 environment = "".
    - Поля name, description, environment — на английском.
    - Названия концепций — на русском.
    - Не добавляй никаких пояснений вне JSON.
    """

    session = requests.Session()
    session.verify = str(CERT)


    def check(response):
        if not response.ok:
            print("HTTP:", response.status_code)
            print("Ответ:", response.text[:1000])
            response.raise_for_status()
        return response.json()


    # Авторизация GigaChat
    auth = check(session.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Authorization": f"Basic {KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"scope": "GIGACHAT_API_PERS"},
        timeout=30,
    ))

    token = auth["access_token"]

    print("Авторизация GigaChat успешна")
    print("Генерируем варианты коллекции:", genre, flush=True)

    # Генерация вариантов
    result = check(session.post(
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "GigaChat-2-Pro",
            "messages": [
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 7000,
            "stream": False,
        },
        timeout=180,
    ))

    print("Первичный ответ GigaChat получен", flush=True)
    answer = result["choices"][0]["message"]["content"]

    # Сохраняем исходный ответ
    raw_path = BASE / "collections_raw.txt"
    raw_path.write_text(answer, encoding="utf-8")

    # Удаляем Markdown-обёртку, если она есть
    clean_answer = answer.strip()

    if clean_answer.startswith("```"):
        lines = clean_answer.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        clean_answer = "\n".join(lines).strip()

    try:
        collections = json.loads(clean_answer)
    except json.JSONDecodeError as error:
        raise SystemExit(
            f"GigaChat вернул некорректный JSON: {error}"
        )


    # GigaChat иногда возвращает массив вариантов вместо объекта.
    # Нормализуем ответ до формата, ожидаемого интерфейсом.
    if isinstance(collections, list):
        collections = {"genre": genre, "variants": collections}
    elif isinstance(collections, dict) and "variants" not in collections:
        for alternative in ("collections", "results", "data"):
            if isinstance(collections.get(alternative), list):
                collections["variants"] = collections[alternative]
                break
    if not isinstance(collections, dict):
        raise ValueError("GigaChat вернул JSON неподдерживаемого формата; ожидается объект с variants")

    # Проверка явно запрещённых типов карточек.
    # Это дополнительный фильтр, а не полноценная
    # семантическая проверка изображаемого объекта.

    FORBIDDEN_NAMES = {
        "ghostly figure",
        "shadowy figure",
        "mysterious person",
        "detective",
        "passenger",
        "footprints",
        "footprints in snow",
        "spider web",
        "murder weapon",
        "human silhouette",
        "animal",
        "ghost",
        "skeleton hand",
    }

    def validate_object_name(name):
        normalized = " ".join(name.lower().split())

        if normalized in FORBIDDEN_NAMES:
            return False

        return True


    # Проверяем структуру
    variants = collections.get("variants")

    if not isinstance(variants, list):
        raise SystemExit("Нет массива variants")

    if len(variants) != variants_count:
        raise SystemExit(
            f"Ожидалось {variants_count} вариантов, "
            f"получено {len(variants)}"
        )

    for variant in variants:
        cards = variant.get("cards")

        if not isinstance(cards, list) or len(cards) != 10:
            raise SystemExit(
                "Каждый вариант должен содержать 10 карточек"
            )

        categories = set()
        names = set()

        for card in cards:
            name = card.get("name", "").strip()
            category = card.get("category")

            if not name:
                raise SystemExit("У карточки отсутствует название")

            if name.lower() in names:
                raise SystemExit(
                    f"Повтор предмета: {name}"
                )

            names.add(name.lower())
            if not validate_object_name(name):
                raise SystemExit(
                    f"Запрещённый тип карточки: {name}"
                )

            if type(category) is not int or category not in (1, 2, 3, 4):
                raise SystemExit(
                    f"Неверная категория у {name}"
                )

            categories.add(category)

            if not card.get("description"):
                raise SystemExit(
                    f"Нет описания у {name}"
                )

            if category in (3, 4) and not card.get("environment"):
                raise SystemExit(
                    f"Нет окружения у {name}"
                )

        if categories != {1, 2, 3, 4}:
            raise SystemExit(
                "В варианте представлены не все категории"
            )


    # Семантическая проверка после структурной валидации.
    # Проверяем предметы внутри каждого варианта, затем исправляем
    # найденные повторы, не меняя категорию и остальные карточки.
    def ask_semantic_model(instruction, max_tokens=2400):
        response = check(session.post(
            "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": "GigaChat-2-Pro",
                "messages": [{"role": "user", "content": instruction}],
                "temperature": 0.15,
                "max_tokens": max_tokens,
                "stream": False,
            },
            timeout=180,
        ))
        content = response["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        return json.loads(content)

    def semantic_duplicates(cards, concept):
        payload = [
            {"position": i, "name": c["name"], "description": c["description"]}
            for i, c in enumerate(cards)
        ]
        instruction = f"""
Ты независимый редактор коллекционных предметов мобильной игры.
Жанр: {genre}. Концепция: {concept}.
Проверь ВСЕ 10 предметов на смысловые дубликаты.
Считай дублями разновидности одного предмета с одинаковым
основным назначением, даже при разных материалах, форме,
креплении и названиях. Например, стационарная и ручная
душевые лейки — дубли; две разновидности зеркал — дубли.
НЕ считай дублями просто связанные, но разные по назначению
предметы: мыльница и дозатор мыла — разные предметы.
Сохраняй первый из пары; укажи только позиции следующих
повторяющихся предметов для замены. Позиции с нуля.
Карточки: {json.dumps(payload, ensure_ascii=False)}
Ответ строго JSON: {{"duplicate_positions": [1, 5]}}.
Если дублей нет: {{"duplicate_positions": []}}.
"""
        result = ask_semantic_model(instruction, 600)
        if not isinstance(result, dict):
            raise ValueError("Проверка дубликатов вернула массив вместо JSON-объекта")
        positions = result.get("duplicate_positions")
        if not isinstance(positions, list) or any(
            type(pos) is not int or pos < 0 or pos >= len(cards)
            for pos in positions
        ):
            raise ValueError("Некорректный ответ проверки смысловых дублей")
        return sorted(set(positions))

    def repair_duplicates(cards, concept, positions):
        original = [dict(card) for card in cards]
        selected = [
            {"position": pos, "category": original[pos]["category"],
             "old_name": original[pos]["name"]}
            for pos in positions
        ]
        instruction = f"""
Ты редактор предметов для коллекционной мобильной игры.
Жанр: {genre}. Концепция: {concept}.
Текущие карточки: {json.dumps(original, ensure_ascii=False)}
Замени ТОЛЬКО позиции: {json.dumps(selected, ensure_ascii=False)}.
Причина: смысловые дубликаты предметов.
Новые предметы должны выполнять другие основные функции,
не дублировать ни один из остальных предметов, соответствовать
концепции и быть визуально различимыми.
СОХРАНИ исходную category каждой заменяемой карточки.
Для category 1/2 environment должен быть пустой строкой;
для category 3/4 укажи конкретное тематическое окружение.
В description описывай только внешний вид предмета, без фона.
Ответ строго JSON с массивом replacements; каждый элемент:
{{"position": 0, "name": "Object Name", "category": 1,
"description": "Object appearance", "environment": ""}}.
Ровно {len(positions)} замен. Никаких пояснений.
"""
        result = ask_semantic_model(instruction)
        # GigaChat иногда возвращает сам массив замен вместо {"replacements": [...]}.
        if isinstance(result, list):
            replacements = result
        elif isinstance(result, dict):
            replacements = result.get("replacements")
        else:
            raise ValueError("Исправление дубликатов вернуло неизвестный формат JSON")
        if not isinstance(replacements, list) or len(replacements) != len(positions):
            raise ValueError("GigaChat вернул неверное количество замен")
        seen_positions = set()
        names = {
            card["name"].strip().casefold()
            for i, card in enumerate(original) if i not in positions
        }
        for item in replacements:
            pos = item.get("position")
            if type(pos) is not int or pos not in positions or pos in seen_positions:
                raise ValueError("Некорректная позиция замены")
            seen_positions.add(pos)
            name = str(item.get("name", "")).strip()
            if not name or name.casefold() in names or not validate_object_name(name):
                raise ValueError(f"Недопустимый или повторяющийся предмет: {name}")
            if name.casefold() == original[pos]["name"].strip().casefold():
                raise ValueError(f"Предмет не изменён: {name}")
            if item.get("category") != original[pos]["category"]:
                raise ValueError(f"Изменена категория предмета: {name}")
            if not str(item.get("description", "")).strip():
                raise ValueError(f"Отсутствует описание предмета: {name}")
            env = str(item.get("environment", "")).strip()
            if item["category"] in (3, 4) and not env:
                raise ValueError(f"Отсутствует окружение предмета: {name}")
            if item["category"] in (1, 2):
                item["environment"] = ""
            names.add(name.casefold())
        updated = [dict(card) for card in original]
        for item in replacements:
            updated[item["position"]] = {
                key: item[key]
                for key in ("name", "category", "description", "environment")
            }
        return updated

    # Семантический аудит: максимум две попытки исправления.
    # Ошибка одного набора не отменяет остальные варианты.
    for variant in variants:
        concept = variant.get("concept", "")
        cards = variant["cards"]
        warnings = []
        for attempt in range(3):
            try:
                duplicates = semantic_duplicates(cards, concept)
            except Exception as error:
                warnings.append(f"Не удалось завершить проверку дублей: {error}")
                break
            if not duplicates:
                break
            print(f"Дубли в '{concept}': {duplicates}", flush=True)
            if attempt == 2:
                warnings.append(f"Возможные дубли, карточки: {[p + 1 for p in duplicates]}")
                break
            try:
                cards = repair_duplicates(cards, concept, duplicates)
                variant["cards"] = cards
                print(f"Исправлено {len(duplicates)} карточек", flush=True)
            except Exception as error:
                warnings.append(f"Не удалось автоматически заменить дубли: {error}")
                break
        if warnings:
            variant["_duplicate_warning"] = "; ".join(warnings)
            print(f"ПРЕДУПРЕЖДЕНИЕ '{concept}': {variant['_duplicate_warning']}", flush=True)
        print(f"Аудит '{concept}' завершён", flush=True)

    # Перевод небольшими пакетами: частичный ответ не стирает успешные переводы.
    # Каждый пакет валидируется, а отсутствующие позиции переводятся отдельно.
    import re as _re

    def valid_russian(value, english):
        value = str(value or "").strip()
        if not value or value.casefold() == str(english or "").strip().casefold():
            return False
        return bool(_re.search(r"[А-Яа-яЁё]", value))

    def translate_batch(cards, positions):
        payload = [{"position": p, "name": cards[p]["name"],
                    "description": cards[p]["description"],
                    "environment": cards[p].get("environment", "")}
                   for p in positions]
        instruction = (
            "Ты профессиональный переводчик игровых предметов. Переведи КАЖДОЕ "
            "поле name, description, environment с английского на естественный русский. "
            "Не транслитерируй английские предложения и не оставляй английский текст. "
            "Сохраняй исходные номера position. Для пустого environment верни пустой environment_ru. "
            "Ответ ТОЛЬКО JSON: {\"translations\":[{\"position\":0,"
            "\"name_ru\":\"Название\",\"description_ru\":\"Описание\","
            "\"environment_ru\":\"Окружение\"}]}. Данные: "
            + json.dumps(payload, ensure_ascii=False)
        )
        result = ask_semantic_model(instruction, max_tokens=1500)
        if isinstance(result, list):
            items = result
        elif isinstance(result, dict):
            items = result.get("translations", result.get("items", []))
        else:
            items = []
        if not isinstance(items, list):
            return {}
        translated = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            pos = item.get("position")
            if type(pos) is not int or pos not in positions:
                continue
            card = cards[pos]
            if not valid_russian(item.get("name_ru"), card["name"]):
                continue
            if not valid_russian(item.get("description_ru"), card["description"]):
                continue
            if card["category"] in (3, 4) and not valid_russian(
                item.get("environment_ru"), card.get("environment", "")
            ):
                continue
            translated[pos] = {
                "name_ru": str(item["name_ru"]).strip(),
                "description_ru": str(item["description_ru"]).strip(),
                "environment_ru": str(item.get("environment_ru", "")).strip()
                    if card["category"] in (3, 4) else "",
            }
        return translated

    for number, variant in enumerate(variants, start=1):
        cards = variant["cards"]
        print(f"Перевод {number}/{len(variants)}: {variant.get('concept', '')}", flush=True)
        pending = set(range(len(cards)))
        for start in range(0, len(cards), 3):
            positions = list(range(start, min(start + 3, len(cards))))
            try:
                translations = translate_batch(cards, positions)
                for pos, fields in translations.items():
                    cards[pos].update(fields)
                    pending.discard(pos)
            except Exception as error:
                print(f"Пакет перевода {positions}: {error}", flush=True)
        # Адресный повтор для неполных пакетов.
        for pos in sorted(pending):
            try:
                translations = translate_batch(cards, [pos])
                if pos in translations:
                    cards[pos].update(translations[pos])
                    pending.discard(pos)
            except Exception as error:
                print(f"Перевод карточки {pos + 1}: {error}", flush=True)
        if pending:
            variant["_translation_warning"] = (
                "Не удалось перевести карточки "
                + ", ".join(str(p + 1) for p in sorted(pending))
            )
            print("ПРЕДУПРЕЖДЕНИЕ:", variant["_translation_warning"], flush=True)
            # Не подменяем русский английским: незаполненные поля остаются пустыми.
            for pos in pending:
                for field in ("name_ru", "description_ru", "environment_ru"):
                    cards[pos][field] = ""
        print(f"Перевод {number}/{len(variants)} завершён; готово {10-len(pending)}/10", flush=True)

    # Сохраняем результаты отдельно для каждого жанра.
    # Уникальный номер запуска предотвращает перезапись файлов.

    from datetime import datetime

    import re

    safe_genre = re.sub(
        r"[^a-zA-Z0-9_-]+",
        "_",
        genre.strip()
    ).strip("_")[:50] or "custom_genre"

    output_dir = BASE / "generated" / safe_genre
    output_dir.mkdir(parents=True, exist_ok=True)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    output_path = output_dir / f"collections_{run_id}.json"


    output_path.write_text(
        json.dumps(
            collections,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\n=== ГЕНЕРАЦИЯ ЗАВЕРШЕНА ===")
    print("Жанр:", collections.get("genre"))
    print("Вариантов:", len(variants))

    for variant in variants:
        print(
            f"Вариант {variant['variant_id']}: "
            f"{variant['concept']} — "
            f"{len(variant['cards'])} карточек"
        )

    print("Результат:", output_path.name)
    print("Токены:", result.get("usage", {}))

    return collections


def replace_collection_items(genre, concept, cards, positions, wishes=""):
    """Заменяет выбранные предметы, сохраняя остальные."""

    if not positions:
        raise ValueError("Не выбраны предметы для замены.")

    positions = sorted(set(positions))
    if any(type(p) is not int or p < 0 or p >= len(cards) for p in positions):
        raise ValueError("Некорректные позиции предметов.")

    original_names = [card["name"] for card in cards]
    selected = [
        {"position": p, "name": original_names[p]}
        for p in positions
    ]

    request_text = f"""
You are a senior collectible game content designer.

Genre: {genre}
Collection: {concept}
Current cards:
{json.dumps(cards, ensure_ascii=False)}

Replace ONLY these zero-based positions:
{json.dumps(selected, ensure_ascii=False)}

Producer feedback:
{wishes or "Suggest more suitable, visually distinct physical objects."}


Requirements:
- Create exactly one dominant, recognizable physical object per illustration.
- Objects must be suitable for premium stylized 3D cartoon rendering.
- Preserve the collection theme and variety of object silhouettes.
- Avoid duplicates and near-duplicates across the collection.
- Composition category must be 1, 2, 3 or 4.

COMPOSITION CATEGORY RULES:

Category 1 — FLOATING OBJECT:
- One isolated physical object floating freely.
- No supporting surface.
- Simple gradient or subtly patterned background.
- The object must remain the dominant visual element.

Category 2 — SIMPLE TABLETOP:
- One physical object resting on a simple flat surface.
- Clean background, soft contact shadow.
- No elaborate room or thematic scene.
- Surface and background colors may be freely selected.
- Avoid repetitive color combinations across the collection.

Category 3 — OBJECT IN A SIMPLE ENVIRONMENT:
- One complete physical object dominates the illustration.
- The object should occupy approximately 55–75% of the image.
- Use a close three-quarter product-style view.
- Place the object on a believable surface or suitable mount.
- Show only minimal environmental context.
- A floor, wall or a few secondary details are allowed.
- The surroundings must remain visually subordinate.
- No complete rooms, theatrical stages, elaborate streets,
  wide establishing shots or environmental storytelling.
- The image must read as an illustration of an object,
  not an illustration of a location or event.

Category 4 — OBJECT IN A THEMATIC SCENE:
- One dominant physical object integrated into a coherent scene.
- The environment may include buildings, interiors,
  theatrical stages, streets or other thematic locations.
- The surroundings establish the context of the object.
- The main object must remain clearly recognizable.
- Avoid excessive background clutter.

CATEGORY SELECTION:
- Choose the category based on the actual visual composition,
  not merely on the object's type or location.
- The same object may belong to different categories
  depending on how it is depicted.
- A standalone spotlight on a simple stand is Category 3.
- A spotlight illuminating a theater stage is Category 4.
- A standalone car on a simple supporting surface
  with minimal context is Category 3.
- A car parked in a detailed city street is Category 4.
- If the subject requires a complete scene to communicate
  its meaning, assign Category 4 instead of Category 3.

SUBJECT AND ENVIRONMENT CONSISTENCY:
- The subject description must match the selected category.
- The environment description must match the selected category.
- For Category 3, describe the physical object itself,
  not an action taking place across an entire scene.
- For Category 3, environment must remain simple and secondary.
- For Category 4, the subject may interact with its environment.
- Never assign Category 3 while describing a complete scene.
- Resolve contradictions before returning the final JSON.

COLOR VARIETY:
- Use a broad, unrestricted color palette.
- Pink, turquoise, blue, yellow, orange, green, purple,
  coral, red and other colors are all allowed.
- Avoid repeating identical background and surface
  color combinations across the collection.
- Select colors that complement the object and its theme.
- Maintain clear contrast and mobile readability.
- Do not force fixed color combinations.

ADDITIONAL RULES:
- Do not use planets, entire locations or complex scenes
  as the main collectible objects.
- Do not return unchanged names.
- Return name_ru, description_ru, environment_ru
  as accurate Russian translations.
- English description and environment must not
  contain background or composition conflicts.
- Return ONLY valid JSON, without Markdown.

Expected JSON:
{{
  "replacements": [
    {{
      "position": 0,
      "name": "Example Object",
      "category": 1,
      "description": "Visual description",
      "environment": ""
    }}
  ]
}}

Return exactly {len(positions)} replacements,
using the requested position values.
"""

    session = requests.Session()
    session.verify = str(CERT)

    auth_response = session.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Authorization": f"Basic {KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={"scope": "GIGACHAT_API_PERS"},
        timeout=30,
    )
    auth_response.raise_for_status()
    token = auth_response.json()["access_token"]

    response = session.post(
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "model": "GigaChat-2-Pro",
            "messages": [{"role": "user", "content": request_text}],
            "temperature": 0.7,
            "max_tokens": 2500,
            "stream": False,
        },
        timeout=180,
    )
    response.raise_for_status()

    answer = response.json()["choices"][0]["message"]["content"].strip()

    if answer.startswith("```"):
        answer = answer.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(answer)
    replacements = data if isinstance(data, list) else data.get("replacements", [])

    if len(replacements) != len(positions):
        raise ValueError("GigaChat вернул неверное количество замен.")

    received = [item.get("position") for item in replacements]
    if len(set(received)) != len(received) or set(received) != set(positions):
        raise ValueError("GigaChat вернул неверные позиции.")

    kept_names = {
        card["name"].strip().casefold()
        for i, card in enumerate(cards)
        if i not in positions
    }

    new_names = set()

    for item in replacements:
        name = str(item.get("name", "")).strip()
        category = item.get("category")

        if not name or name.casefold() in kept_names:
            raise ValueError(f"Пустое или повторяющееся название: {name}")

        if name.casefold() in new_names:
            raise ValueError(f"Повтор среди замен: {name}")

        if name.casefold() == original_names[item["position"]].strip().casefold():
            raise ValueError(f"Предмет не изменён: {name}")

        if type(category) is not int or category not in (1, 2, 3, 4):
            raise ValueError(f"Некорректная категория: {name}")

        if not str(item.get("description", "")).strip():
            raise ValueError(f"Нет описания: {name}")

        if category in (3, 4) and not str(item.get("environment", "")).strip():
            item["environment"] = (
                "Warm wooden desk, blue-teal wall"
                if category == 3
                else "Cobblestone street, brick wall, vintage streetlamp"
            )

        new_names.add(name.casefold())

    for item in replacements:
        item.setdefault("name_ru", item.get("name", ""))
        item.setdefault("description_ru", item.get("description", ""))
        item.setdefault("environment_ru", item.get("environment", ""))
    return replacements

