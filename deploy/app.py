import json
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from technical_qc import check_image
from database_manager import initialize_database
import streamlit as st
from PIL import Image, ImageOps
from collection_generator import generate_collections, replace_collection_items
import io
import zipfile

BASE = Path(__file__).resolve().parent
IMAGES_DIR = BASE / 'images'
PROMPTS_DIR = BASE / 'prompts'
GENERATED_DIR = BASE / 'generated'
UPLOAD_DIR = BASE / 'uploaded_images'

st.set_page_config(page_title='AI Collection Studio', page_icon='🎨', layout='wide')
initialize_database()

# Русские подписи храним отдельно, не меняя английские поля карточек.
def initialize_card_translations():
    with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS card_translations (
                card_id INTEGER PRIMARY KEY,
                name_ru TEXT NOT NULL DEFAULT '',
                description_ru TEXT NOT NULL DEFAULT '',
                environment_ru TEXT NOT NULL DEFAULT ''
            )
        """)


initialize_card_translations()



# VISUAL_REFERENCES_V1
VISUAL_REF_DIR = BASE.parent / 'references'

def reference_style_prompt(prompt):
    try:
        profile = json.loads((VISUAL_REF_DIR / 'style_spec.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return prompt
    begin = prompt.find('ART STYLE:')
    end = prompt.find('\nCOMPOSITION:', begin)
    block = 'ART STYLE:\n' + profile['style_prompt'] + '\nAVOID:\n' + profile['avoid'] + '\n'
    if begin >= 0 and end > begin:
        return prompt[:begin] + block + prompt[end:]
    return prompt + '\n\nREFERENCE STYLE OVERRIDE:\n' + block

def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        st.warning(f'Не удалось прочитать {path.name}: {exc}')
        return None


def extract_cards(obj):
    if isinstance(obj, list) and len(obj) == 10 and all(isinstance(x, dict) for x in obj):
        return obj
    if isinstance(obj, dict):
        for key in ('cards', 'items', 'objects'):
            if key in obj:
                found = extract_cards(obj[key])
                if found:
                    return found
    return None


def collect_variants(obj):
    found = []
    if isinstance(obj, dict):
        cards = extract_cards(obj)
        if cards:
            found.append((obj, cards))
        else:
            for key in ('collections', 'variants', 'results', 'data'):
                if key in obj:
                    found.extend(collect_variants(obj[key]))
    elif isinstance(obj, list):
        if extract_cards(obj):
            found.append(({}, obj))
        else:
            for item in obj:
                found.extend(collect_variants(item))
    return found


def safe_part(value):
    return re.sub(r'[^a-zA-Z0-9_-]+', '_', str(value)).strip('_')[:60] or 'item'

def delete_collection_from_database(collection_id):
    db_path = BASE / "database" / "studio.db"

    with sqlite3.connect(db_path) as db:
        db.execute("PRAGMA foreign_keys = ON")

        exists = db.execute(
            "SELECT 1 FROM collections WHERE id = ?",
            (collection_id,)
        ).fetchone()

        if exists is None:
            raise ValueError("Коллекция не найдена в базе данных")

        db.execute(
            """
            DELETE FROM images
            WHERE card_id IN (
                SELECT id FROM cards WHERE collection_id = ?
            )
            """,
            (collection_id,)
        )

        db.execute(
            """
            DELETE FROM prompts
            WHERE card_id IN (
                SELECT id FROM cards WHERE collection_id = ?
            )
            """,
            (collection_id,)
        )

        db.execute(
            "DELETE FROM card_translations WHERE card_id IN "
            "(SELECT id FROM cards WHERE collection_id = ?)",
            (collection_id,)
        )

        db.execute(
            "DELETE FROM cards WHERE collection_id = ?",
            (collection_id,)
        )

        db.execute(
            "DELETE FROM collections WHERE id = ?",
            (collection_id,)
        )

def catalog_from_database():
    db_path = BASE / "database" / "studio.db"

    if not db_path.is_file():
        return []

    entries = []

    with sqlite3.connect(db_path) as connection:
        collections = connection.execute("""
            SELECT
                c.id,
                p.genre,
                c.name
            FROM collections AS c
            JOIN projects AS p ON p.id = c.project_id
            ORDER BY c.id
        """).fetchall()

        for collection_id, genre, name in collections:
            rows = connection.execute("""
                SELECT
                    name,
                    description,
                    composition_category,
                    environment,
                    cards.id
                FROM cards
                WHERE collection_id = ?
                ORDER BY position
            """, (collection_id,)).fetchall()

            cards = []
            for row in rows:
                translation = connection.execute(
                    "SELECT name_ru, description_ru, environment_ru "
                    "FROM card_translations WHERE card_id = ?", (row[4],)
                ).fetchone() or ('', '', '')
                cards.append({
                    "name": row[0], "description": row[1],
                    "category": row[2], "environment": row[3],
                    "name_ru": translation[0],
                    "description_ru": translation[1],
                    "environment_ru": translation[2],
                })

            entries.append({
                "id": f"db_{collection_id}",
                "label": f"{genre} · {name}",
                "cards": cards,
                "original": False
            })

    return entries


def catalog():
    return catalog_from_database()
    # Первоначальная коллекция теперь загружается из SQLite.
    # collection.json сохраняем как исходный файл.
    if GENERATED_DIR.is_dir():
        for genre_dir in sorted(p for p in GENERATED_DIR.iterdir() if p.is_dir()):
            if genre_dir.name == 'Detective':
                continue

            files = sorted(genre_dir.glob('collections_*.json'))
            if not files:
                continue
            data = read_json(files[-1])
            for index, (meta, cards) in enumerate(collect_variants(data), 1):
                name = (meta.get('name') or meta.get('title') or
                        meta.get('collection_name') or f'Вариант {index}')
                entries.append({'id': f'{safe_part(genre_dir.name)}_{index}',
                                'label': f'{genre_dir.name} · {name}', 'cards': cards,
                                'original': False})
    return entries


def card_name(card, index):
    return str(card.get('name_ru') or card.get('name') or card.get('title') or card.get('object') or f'Карточка {index:02d}')


def image_path_from_database(entry, index):
    if not entry["id"].startswith("db_"):
        return None

    db_path = BASE / "database" / "studio.db"

    if not db_path.is_file():
        return None

    collection_id = int(entry["id"][3:])

    with sqlite3.connect(db_path) as connection:
        result = connection.execute("""
            SELECT images.file_path
            FROM images
            JOIN cards ON cards.id = images.card_id
            WHERE cards.collection_id = ?
              AND cards.position = ?
            ORDER BY images.id DESC
            LIMIT 1
        """, (collection_id, index)).fetchone()

    if result is None:
        return None

    path = BASE / result[0]

    return path if path.is_file() else None



def image_path(entry, index):
    # Сначала ищем изображение через SQLite
    db_image = image_path_from_database(entry, index)

    if db_image is not None:
        return db_image

    # Если изображение не найдено, используем старую логику
    if entry['original']:
        return IMAGES_DIR / f'card_{index:02d}.png'

    return UPLOAD_DIR / entry['id'] / f'card_{index:02d}.png'




def prompt_path(entry, index):
    # Первоначальная коллекция Detective хранится в SQLite с ID 4
    if entry['id'] == 'db_4':
        return PROMPTS_DIR / f'card_{index:02d}.txt'

    # Поддержка старых коллекций
    if entry['original']:
        return PROMPTS_DIR / f'card_{index:02d}.txt'

    return BASE / 'custom_prompts' / entry['id'] / f'card_{index:02d}.txt'



def prompt_for(entry, index):
    import random
    import re

    card = entry['cards'][index - 1]
    name = card.get('name', '')
    description = card.get('description', '')
    environment = card.get('environment', '')

    try:
        category = int(card.get('category', 1))
    except (ValueError, TypeError):
        category = 1

    # -----------------------------------------
    # 1. Получаем исходный промпт
    # -----------------------------------------

    original_prompt = None

    if entry['id'].startswith('db_'):
        collection_id = int(entry['id'][3:])

        with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
            result = db.execute("""
                SELECT p.prompt_text
                FROM prompts AS p
                JOIN cards AS c ON c.id = p.card_id
                WHERE c.collection_id = ?
                  AND c.position = ?
                ORDER BY p.id DESC
                LIMIT 1
            """, (collection_id, index)).fetchone()

        if result is not None:
            original_prompt = result[0]

    if original_prompt is None:
        path = prompt_path(entry, index)

        if path.is_file():
            original_prompt = path.read_text(
                encoding='utf-8'
            )

    if original_prompt is None:
        for key in (
            'prompt',
            'image_prompt',
            'generation_prompt'
        ):
            value = card.get(key)

            if isinstance(value, str) and value.strip():
                original_prompt = value
                break

    # -----------------------------------------
    # 2. Композиционные правила категорий
    # -----------------------------------------

    compositions = {
        1: (
            "One dominant object floating freely. "
            "No supporting surface. "
            "Clean background with a subtle gradient "
            "or simple decorative pattern. "
            "Strong silhouette and mobile readability."
        ),
        2: (
            "One dominant object resting on a simple "
            "flat surface with a soft contact shadow. "
            "Clean, visually separate background. "
            "The surface and background must remain "
            "minimal and secondary to the object."
        ),
        3: (
            "CATEGORY 3 — SINGLE OBJECT IN A SIMPLE ENVIRONMENT. "
            "Show one complete physical object as the dominant "
            "subject, occupying approximately 55–75% of the image. "
            "Use a close three-quarter product-style view. "
            "Place the object on a believable supporting surface "
            "or a simple mount appropriate to its construction. "
            "Show only minimal environmental context, such as "
            "a floor, wall or a few secondary background details. "
            "Keep the environment visually subordinate. "
            "No complete rooms, theatrical stages, wide shots "
            "or elaborate thematic scenes. "
            "If the description includes an action in a larger "
            "setting, focus on the physical object instead "
            "of depicting the entire scene."
        ),
        4: (
            "One dominant object naturally integrated "
            "into a coherent thematic scene. "
            "Preserve the location, surroundings "
            "and atmosphere described in the prompt."
        )
    }

    composition = compositions.get(
        category,
        compositions[1]
    )

    # -----------------------------------------
    # 3. Создаём промпт, если его ещё нет
    # -----------------------------------------

    if original_prompt is None:
        original_prompt = f"""Create a single collectible game illustration.

SUBJECT:
{name}
{description}

ENVIRONMENT:
{environment}

ART STYLE:
Premium colorful casual mobile game illustration.
Polished stylized 3D cartoon rendering.
Simplified geometry, playful proportions.
Vivid saturated colors, soft directional lighting.
Controlled highlights, subtle ambient occlusion.
One dominant physical object with a crisp silhouette.

COMPOSITION:
{composition}

CANVAS:
Portrait orientation, exact 43:48 width-to-height aspect ratio.
Target image dimensions: 430 x 480 pixels.
Full-bleed illustration with sharp rectangular corners.
The subject must remain clearly readable on a mobile screen.

NEGATIVE CONSTRAINTS:
No text, letters, logos, UI elements, stars or watermarks.
No collectible card borders, frames or rounded corners.
No additional competing main subjects.
"""

    # -----------------------------------------
    # 4. Разнообразие палитры всей коллекции
    # -----------------------------------------

    color_families = [
        "pink and rose",
        "turquoise and aqua",
        "sunny yellow",
        "orange and apricot",
        "mint and fresh green",
        "sky blue and azure",
        "lavender and violet",
        "coral and salmon",
        "lime and chartreuse",
        "magenta and fuchsia",
        "peach and warm cream",
        "deep blue and indigo",
        "emerald and jade",
        "red and raspberry",
        "lilac and periwinkle",
        "gold and amber"
    ]

    # Стабильное распределение для коллекции.
    # Повторный просмотр не меняет цвета.

    collection_key = str(entry.get('id', ''))
    collection_seed = sum(
        (position + 1) * ord(character)
        for position, character in enumerate(
            collection_key
        )
    )

    rng = random.Random(collection_seed)

    # Перемешиваем направления, чтобы коллекции
    # не начинались с одинаковой палитры.

    background_colors = color_families.copy()
    rng.shuffle(background_colors)

    surface_colors = color_families.copy()
    rng.shuffle(surface_colors)

    # Избегаем совпадений цветовых направлений
    # поверхности и фона в одной карточке.

    for offset in range(len(surface_colors)):
        if all(
            surface_colors[
                (i + offset) % len(surface_colors)
            ] != background_colors[i]
            for i in range(len(color_families))
        ):
            surface_colors = (
                surface_colors[offset:]
                + surface_colors[:offset]
            )
            break

    color_index = (
        (index - 1) % len(color_families)
    )

    background_color = background_colors[
        color_index
    ]

    surface_color = surface_colors[
        color_index
    ]

    # -----------------------------------------
    # 5. Цветовые правила по категориям
    # -----------------------------------------

    if category == 1:
        color_instruction = f"""
COLOR DIRECTION:
Use {background_color} as the starting color
family for the simple background.

Choose exact hues, brightness and saturation
to contrast with the subject.

The palette is not restricted to these colors.
Other colors may be used when they improve
contrast, harmony or the collection theme.

Keep the object floating without a surface.
Avoid copying colors from style references.
"""

    elif category == 2:
        color_instruction = f"""
COLOR DIRECTION:
Suggested background color family:
{background_color}.

Suggested tabletop or surface color family:
{surface_color}.

These are independent color directions,
not mandatory exact shades.

Choose suitable hues, materials and brightness
based on the subject and collection theme.

Ensure clear visual separation between
the object, surface and background.

Use a soft contact shadow.
Keep the surface simple and uncluttered.

The full color spectrum is allowed.
Avoid defaulting to brown or orange tables
with blue backgrounds.
"""

    elif category == 3:
        color_instruction = f"""
COLOR DIRECTION:
Consider {background_color} as a possible
color accent within the environment.

Preserve the believable surface, materials,
location and spatial composition.

Do not force this color onto the entire scene.
Adapt it to the subject and environment.

Use complementary or contrasting colors
freely to maintain visual variety.
"""

    else:
        color_instruction = f"""
COLOR DIRECTION:
Consider {background_color} as a possible
secondary color accent in the scene.

Preserve the original thematic environment,
its materials, lighting and atmosphere.

Do not recolor recognizable objects
unnaturally just to match the palette.

Use any additional colors that improve
the composition and thematic coherence.
"""

    # -----------------------------------------

    # -----------------------------------------
    # 6. Обновляем сохранённые промпты
    # -----------------------------------------

    # Убираем ранее добавленный цветовой блок,
    # если он уже присутствует в тексте.

    original_prompt = re.sub(
        r'\n?COLLECTION COLOR DIVERSITY RULES:'
        r'.*?END COLLECTION COLOR DIVERSITY RULES',
        '',
        original_prompt,
        flags=re.DOTALL
    ).rstrip()

    # -----------------------------------------
    # 7. Обновляем композицию категории 3
    # -----------------------------------------

    if category == 3:
        new_composition = compositions[3]

        # Заменяем только раздел COMPOSITION.
        # Остальные разделы сохраняются.

        composition_pattern = (
            r'(?im)^COMPOSITION:\s*\n'
            r'.*?'
            r'(?=^[A-Z][A-Z _-]*:\s*$|\Z)'
        )

        replacement = (
            "COMPOSITION:\n"
            + new_composition
            + "\n\n"
        )

        if re.search(
            composition_pattern,
            original_prompt,
            flags=re.DOTALL
        ):
            original_prompt = re.sub(
                composition_pattern,
                lambda match: replacement,
                original_prompt,
                count=1,
                flags=re.DOTALL
            )
        else:
            original_prompt = (
                original_prompt.rstrip()
                + "\n\n"
                + replacement
            )

    # -----------------------------------------
    # 8. Добавляем цветовые правила
    # -----------------------------------------

    diversity_rules = f"""

COLLECTION COLOR DIVERSITY RULES:
This illustration belongs to a collection
of {len(entry['cards'])} collectible images.

Use a varied, colorful art direction across
the collection. Avoid repetitive backgrounds
and identical surface/background combinations.

Each illustration should have its own
recognizable color identity.

{color_instruction.strip()}

PRIORITY:
Preserve the original subject, environment,
composition category and artistic intent.

If an older prompt specifies a fixed generic
background or tabletop color that conflicts
with the new color direction, prefer the
new color direction.

Do not change distinctive colors that are
essential to the subject's identity.

Style references define rendering quality,
not the colors or layout of the scene.

END COLLECTION COLOR DIVERSITY RULES
"""


    # Исправляем устаревший формат в сохранённых промптах.
    # Не изменяем предмет, окружение и композицию.
    original_prompt = re.sub(
        r'(?<!\d)3\s*:\s*4(?!\d)',
        '43:48',
        original_prompt
    )

    # Добавляем актуальные требования к формату.
    format_rules = """

FINAL IMAGE FORMAT REQUIREMENTS:
Portrait orientation.
Exact width-to-height aspect ratio: 43:48.
Target dimensions: 430 x 480 pixels
or a proportionally larger resolution.
Full-bleed illustration with sharp rectangular corners.
Do not crop, stretch or distort the main subject.
These requirements override older canvas instructions.
END FINAL IMAGE FORMAT REQUIREMENTS
"""


    # Разнообразие геометрических фонов внутри коллекции.
    geometric_patterns = [
        "soft diagonal stripes",
        "subtle radial rays",
        "wide concentric arcs",
        "large overlapping geometric shapes",
        "gentle zigzag bands",
        "soft diamond grid",
        "broad vertical geometric bands",
        "layered angular polygons",
        "subtle chevron pattern",
        "large staggered geometric tiles",
    ]

    pattern_rng = random.Random(
        sum((i + 1) * ord(c) for i, c in enumerate(str(entry["id"])))
        + 137
    )
    pattern_rng.shuffle(geometric_patterns)
    selected_pattern = geometric_patterns[
        (index - 1) % len(geometric_patterns)
    ]

    pattern_rules = ""

    if category in (1, 2):
        pattern_rules = f"""

COLLECTION GEOMETRIC BACKGROUND RULES:
Use this background pattern: {selected_pattern}.
The pattern must be clearly recognizable but visually
subordinate to the main object.
Use large simple shapes, soft tonal differences
and a clean polished casual mobile game appearance.
Choose pattern colors that harmonize with the
illustration's assigned color palette.
Do not add extra objects, text or decorative symbols.
For Category 2, apply the pattern to the background
behind the tabletop, not to the tabletop itself.
These instructions override older generic
background descriptions when they conflict.
END COLLECTION GEOMETRIC BACKGROUND RULES
"""


    category3_rules = ""

    if category == 3:
        category3_rules = """

CATEGORY 3 — FINAL COMPOSITION OVERRIDE:

Create a close-up product-style illustration
of ONE complete physical object.
The object must occupy 60–75% of the canvas.

Show only the immediate supporting surface
and a minimal, softly simplified background.

The SUBJECT and ENVIRONMENT fields describe
the object's identity and thematic context.
They do NOT require depicting the full location.

If the subject mentions a stage, theater,
street, cinema, red carpet or another large
location, do NOT reproduce that location.

Do not show complete rooms, stages, entrances,
streets, landscapes, architectural facades,
panoramic environments or multiple background props.

Keep the physical object as the clear focal point.
Show a small amount of believable environmental
context, but never a complete thematic scene.

For a spotlight, show the spotlight fixture
and its immediate mount, not the illuminated stage.
For a star plaque, show the plaque on a small
section of pavement, not an entire street.
For a red carpet, show a short rolled or partially
unrolled carpet section, not a theater entrance.

This instruction overrides conflicting SUBJECT,
ENVIRONMENT and COMPOSITION descriptions.

END CATEGORY 3 OVERRIDE
"""

    return (
        original_prompt
        + diversity_rules
        + format_rules
        + pattern_rules
        + category3_rules
    )



def image_preview(path, height=280):
    if not path.is_file():
        st.info('Изображение отсутствует')
        return
    try:
        with Image.open(path) as source:
            img = ImageOps.exif_transpose(source).convert('RGB')
            img.thumbnail((650, height))
            st.image(img)
    except Exception as exc:
        st.error(f'Не удалось открыть изображение: {exc}')


with st.expander("✨ Создать коллекции с помощью GigaChat", expanded=False):
    with st.form("ai_generate_collections"):
        ai_project = st.text_input(
            "Название проекта",
            value="Playrix Demo"
        )
        ai_genre = st.text_input(
            "Жанр",
            value="Adventure"
        )
        ai_description = st.text_area(
            "Описание и пожелания",
            placeholder="Например: затерянная экспедиция, древние артефакты..."
        )
        ai_count = st.selectbox(
            "Количество коллекций",
            options=[3, 4, 5]
        )
        ai_submit = st.form_submit_button(
            "✨ Сгенерировать коллекции"
        )

    if ai_submit:
        if not ai_project.strip() or not ai_genre.strip():
            st.error("Укажите название проекта и жанр.")
        else:
            with st.spinner("GigaChat создаёт коллекции..."):
                try:
                    generated = generate_collections(
                        ai_genre,
                        ai_description,
                        ai_count
                    )
                    st.session_state["generated_collections"] = generated
                    st.session_state["generated_project_name"] = ai_project.strip()
                    st.session_state["generated_genre"] = ai_genre.strip()
                except Exception as exc:
                    st.error(f"Ошибка генерации: {exc}")

    if "generated_collections" in st.session_state:
        generated = st.session_state["generated_collections"]
        st.success("Коллекции сгенерированы!")

        variants = generated.get("variants", [])

        st.subheader("Предложенные коллекции")
        st.caption(
            f"Коллекций: {len(variants)} | "
            f"Предметов: {sum(len(v.get('cards', [])) for v in variants)}"
        )

        category_names = {
            1: "1 — Floating",
            2: "2 — Tabletop",
            3: "3 — Desk",
            4: "4 — Street"
        }

        for index, variant in enumerate(variants):
            with st.expander(
                f"Коллекция {index + 1}: "
                f"{variant.get('concept', 'Без названия')}",
                expanded=(index == 0)
            ):

                if variant.get("_duplicate_warning"):
                    warning = variant["_duplicate_warning"]

                    if isinstance(warning, (list, tuple, set)):
                        numbers = ", ".join(str(n) for n in warning)
                        message = f"Возможные смысловые дубли: карточки {numbers}."
                    else:
                        message = str(warning)

                    st.warning(
                        message + " Проверьте предметы перед сохранением; "
                        "при необходимости отметьте их для замены через GigaChat."
                    )

                variant["_selected_for_save"] = st.checkbox(
                    "Сохранить эту коллекцию",
                    value=variant.get("_selected_for_save", True),
                    key=f"ai_save_collection_{index}"
                )
                variant["concept"] = st.text_input(
                    "Название коллекции",
                    value=variant.get("concept", ""),
                    key=f"ai_concept_{index}"
                )

                rows = [
                    {
                        "Заменить": False,
                        "Статус": (
                            "🔄 Заменён ИИ"
                            if card.get("_ai_replaced") else ""
                        ),
                        "Предмет (RU)": card.get("name_ru", ""),
                        "Предмет (EN)": card.get("name", ""),
                        "Описание (RU)": card.get("description_ru", ""),
                        "Описание (EN)": card.get("description", ""),
                        "Категория": category_names.get(
                            card.get("category"), "1 — Floating"
                        ),
                        "Окружение (RU)": card.get("environment_ru", ""),
                        "Окружение (EN)": card.get("environment", "")
                    }
                    for card in variant.get("cards", [])
                ]

                edited_rows = st.data_editor(
                    rows,
                    key=f"ai_editor_{index}",
                    hide_index=True,
                    width="stretch",
                    num_rows="fixed",
                    column_config={
                        "Заменить": st.column_config.CheckboxColumn(
                            "Заменить",
                            help="Отметьте предметы для повторного подбора через GigaChat"
                        ),
                        "Статус": st.column_config.TextColumn(
                            "Статус",
                            disabled=True
                        ),
                        "Предмет (RU)": st.column_config.TextColumn("Предмет (RU)"),
                        "Предмет (EN)": st.column_config.TextColumn("Предмет (EN)", required=True),
                        "Описание (RU)": st.column_config.TextColumn("Описание (RU)", width="large"),
                        "Описание (EN)": st.column_config.TextColumn("Описание (EN)", width="large"),
                        "Категория": st.column_config.SelectboxColumn(
                            "Категория",
                            options=list(category_names.values()),
                            required=True
                        ),
                        "Окружение (RU)": st.column_config.TextColumn("Окружение (RU)"),
                        "Окружение (EN)": st.column_config.TextColumn("Окружение (EN)")
                    }
                )

                for card, row in zip(variant["cards"], edited_rows):
                    card["name_ru"] = row["Предмет (RU)"]
                    card["name"] = row["Предмет (EN)"]
                    card["description_ru"] = row["Описание (RU)"]
                    card["description"] = row["Описание (EN)"]
                    card["category"] = int(row["Категория"][0])
                    card["environment_ru"] = row["Окружение (RU)"]
                    card["environment"] = row["Окружение (EN)"]


                selected_positions = [
                    position
                    for position, row in enumerate(edited_rows)
                    if row["Заменить"]
                ]

                replacement_wishes = st.text_input(
                    "Пожелания к замене",
                    placeholder="Например: вместо планет предложи космические приборы",
                    key=f"ai_replacement_wishes_{index}"
                )

                if st.button(
                    f"🔄 Заменить выбранные через GigaChat ({len(selected_positions)})",
                    key=f"ai_replace_button_{index}",
                    disabled=not selected_positions
                ):
                    with st.spinner("GigaChat подбирает новые предметы..."):
                        try:
                            replacements = replace_collection_items(
                                genre=st.session_state["generated_genre"],
                                concept=variant["concept"],
                                cards=variant["cards"],
                                positions=selected_positions,
                                wishes=replacement_wishes
                            )

                            for replacement in replacements:
                                position = replacement["position"]
                                variant["cards"][position].update({
                                    "name": replacement["name"],
                                    "description": replacement["description"],
                                    "category": replacement["category"],
                                    "environment": replacement.get("environment", ""),
                                    "name_ru": replacement.get("name_ru", ""),
                                    "description_ru": replacement.get("description_ru", ""),
                                    "environment_ru": replacement.get("environment_ru", ""),
                                    "_ai_replaced": True
                                })

                            # Сбрасываем состояние таблицы, чтобы показать новые данные.
                            editor_key = f"ai_editor_{index}"
                            if editor_key in st.session_state:
                                del st.session_state[editor_key]

                            st.success(
                                f"Заменено предметов: {len(replacements)}"
                            )
                            st.rerun()

                        except Exception as exc:
                            st.error(f"Не удалось заменить предметы: {exc}")


        st.caption(
            "Проверьте названия, описания и категории. "
            "Все изменения будут учтены при сохранении."
        )


        if st.button("💾 Утвердить и сохранить коллекции"):
            try:
                variants = [
                    variant
                    for variant in generated["variants"]
                    if variant.get("_selected_for_save", True)
                ]

                if not variants:
                    st.warning("Выберите хотя бы одну коллекцию для сохранения.")
                    st.stop()

                with sqlite3.connect(BASE / "database" / "studio.db") as db:
                    cursor = db.execute(
                        "INSERT INTO projects (name, genre) VALUES (?, ?)",
                        (
                            st.session_state["generated_project_name"],
                            st.session_state["generated_genre"]
                        )
                    )
                    project_id = cursor.lastrowid

                    for variant in variants:
                        collection_name = variant["concept"]

                        cursor = db.execute(
                            "INSERT INTO collections (project_id, name) VALUES (?, ?)",
                            (project_id, collection_name)
                        )
                        collection_id = cursor.lastrowid

                        for position, card in enumerate(variant["cards"], start=1):
                            cursor = db.execute(
                                """INSERT INTO cards
                                   (collection_id, position, name, description,
                                    composition_category, environment)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                (
                                    collection_id,
                                    position,
                                    card["name"],
                                    card.get("description", ""),
                                    card["category"],
                                    card.get("environment", "")
                                )
                            )
                            db.execute(
                                """INSERT INTO card_translations
                                   (card_id, name_ru, description_ru, environment_ru)
                                   VALUES (?, ?, ?, ?)""",
                                (
                                    cursor.lastrowid,
                                    card.get("name_ru", ""),
                                    card.get("description_ru", ""),
                                    card.get("environment_ru", "")
                                )
                            )

                    db.commit()

                del st.session_state["generated_collections"]
                st.success("Коллекции и карточки сохранены!")
                st.rerun()

            except Exception as exc:
                st.error(f"Ошибка сохранения: {exc}")



entries = catalog()
st.title('🎨 AI Collection Studio')
st.caption('Playrix AI Producer · Локальный прототип · Платные API отключены')
if not entries:
    st.info('Коллекций пока нет. Создайте первый проект.')

    with st.form('create_first_collection'):
        project_name = st.text_input('Название проекта', value='Playrix Demo')
        genre = st.text_input('Жанр', value='Adventure')
        collection_name = st.text_input('Название коллекции')
        create = st.form_submit_button('Создать проект и коллекцию')

    if create:
        if not project_name.strip() or not collection_name.strip():
            st.error('Заполните название проекта и коллекции.')
        else:
            with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
                cursor = db.execute(
                    'INSERT INTO projects (name, genre) VALUES (?, ?)',
                    (project_name.strip(), genre.strip())
                )
                project_id = cursor.lastrowid

                cursor = db.execute(
                    'INSERT INTO collections (project_id, name) VALUES (?, ?)',
                    (project_id, collection_name.strip())
                )
                collection_id = cursor.lastrowid

                for position in range(1, 11):
                    db.execute(
                        'INSERT INTO cards (collection_id, position, name) VALUES (?, ?, ?)',
                        (collection_id, position, f'Предмет {position:02d}')
                    )

                db.commit()

            st.success('Коллекция создана!')
            st.rerun()

    st.stop()

with st.sidebar:
    st.header('Навигация')
    selected_id = st.selectbox('Коллекция', [e['id'] for e in entries],
                               format_func=lambda value: next(e['label'] for e in entries if e['id'] == value))
    page = st.radio('Раздел', ['Галерея', 'Иллюстрации', 'Проверка качества'])
    st.divider()
    st.caption(f'Доступно коллекций: {len(entries)}')

    st.divider()
    st.markdown('**Визуальные эталоны Playrix**')
    ref_cat = st.selectbox('Категория эталона', [1, 2, 3, 4], key='ref_cat')
    ref_files = st.file_uploader('Загрузить эталоны без UI', type=['png','jpg','jpeg','webp'], accept_multiple_files=True, key='ref_upload')
    if ref_files and st.button('Сохранить эталоны'):
        folder = VISUAL_REF_DIR / f'category_{ref_cat}'
        folder.mkdir(parents=True, exist_ok=True)
        for uploaded in ref_files:
            (folder / Path(uploaded.name).name).write_bytes(uploaded.getvalue())
        st.success('Эталоны сохранены')
    ref_saved = [p for p in sorted((VISUAL_REF_DIR / f'category_{ref_cat}').glob('*')) if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
    st.caption(f'Эталонов: {len(ref_saved)}')
    if ref_saved:
        st.image(str(ref_saved[0]), use_container_width=True)


entry = next(e for e in entries if e['id'] == selected_id)
cards = entry['cards']
ready = sum(image_path(entry, i).is_file() for i in range(1, len(cards) + 1))

if page == 'Галерея':
    st.subheader(entry['label'])
    a, b, c = st.columns(3)
    a.metric('Карточек', len(cards))
    b.metric('С изображением', ready)
    c.metric('Без изображения', len(cards) - ready)

    if st.button(
        '🎨 Сгенерировать все изображения',
        key='generate_all_images',
        use_container_width=True
    ):
        st.info(
            'Пакетная генерация изображений предусмотрена '
            'для следующего этапа разработки. '
            'После подключения API изображения будут '
            'генерироваться автоматически по промптам коллекции.'
        )

    if str(entry["id"]).startswith("db_"):
        collection_db_id = int(str(entry["id"])[3:])


        if str(entry["id"]).startswith("db_"):
            collection_db_id = int(str(entry["id"])[3:])

            if st.button(
                "🗑 Удалить коллекцию",
                key=f"open_delete_{entry['id']}",
                use_container_width=True
            ):
                st.session_state[f"show_delete_{entry['id']}"] = True

            if st.session_state.get(f"show_delete_{entry['id']}", False):
                st.warning(
                    "Удалить эту коллекцию? Все её карточки, "
                    "промпты и записи изображений будут удалены из базы. "
                    "Файлы изображений на диске сохранятся."
                )

                col_confirm, col_cancel = st.columns(2)

                with col_confirm:
                    if st.button(
                        "🗑 Подтвердить удаление",
                        key=f"confirm_delete_{entry['id']}",
                        use_container_width=True
                    ):
                        try:
                            delete_collection_from_database(collection_db_id)
                            st.session_state.pop(
                                f"show_delete_{entry['id']}", None
                            )
                            st.success("Коллекция удалена.")
                            st.rerun()
                        except Exception as error:
                            st.error(f"Ошибка удаления: {error}")

                with col_cancel:
                    if st.button(
                        "Отмена",
                        key=f"cancel_delete_{entry['id']}",
                        use_container_width=True
                    ):
                        st.session_state.pop(
                            f"show_delete_{entry['id']}", None
                        )
                        st.rerun()



    if ready > 0:
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(
            zip_buffer,
            'w',
            zipfile.ZIP_DEFLATED
        ) as archive:
            for index in range(1, len(cards) + 1):
                path = image_path(entry, index)

                if path.is_file():
                    archive.write(
                        path,
                        arcname=f'card_{index:02d}{path.suffix.lower()}'
                    )

        st.download_button(
            '📦 Скачать все изображения (ZIP)',
            data=zip_buffer.getvalue(),
            file_name=f"collection_{entry['id']}_images.zip",
            mime='application/zip',
            use_container_width=True,
            key=f'download_all_{entry["id"]}'
        )
    else:
        st.button(
            '📦 Скачать все изображения (ZIP)',
            disabled=True,
            use_container_width=True
        )

    for start in range(0, len(cards), 5):
        cols = st.columns(5)
        for offset, card in enumerate(cards[start:start + 5]):
            index = start + offset + 1
            with cols[offset]:
                st.markdown(f'**{index:02d}. {card_name(card, index)}**')
                if card.get('name_ru'):
                    st.caption(card.get('name', ''))
                path = image_path(entry, index)
                image_preview(path, height=215)
                st.caption(f"Категория: {card.get('category', '—')}")

elif page == 'Иллюстрации':
    st.subheader('Управление иллюстрациями')
    selected = st.selectbox('Карточка', list(range(1, len(cards) + 1)),
                            format_func=lambda i: f'{i:02d} — {card_name(cards[i - 1], i)}')
    path = image_path(entry, selected)
    selected_card = cards[selected - 1]
    if selected_card.get('name_ru'):
        st.caption(f"English: {selected_card.get('name', '')}")
    if selected_card.get('description_ru'):
        st.write('**Описание:**', selected_card['description_ru'])
    if selected_card.get('environment_ru'):
        st.write('**Окружение:**', selected_card['environment_ru'])
    if entry['id'].startswith('db_'):
        collection_id = int(entry['id'][3:])

        with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
            status_row = db.execute(
                'SELECT status FROM cards WHERE collection_id = ? AND position = ?',
                (collection_id, selected)
            ).fetchone()

        if status_row:
            st.caption(f'Статус карточки: {status_row[0]}')
            new_status = st.selectbox(
                'Изменить статус карточки',
                ['DRAFT', 'REVIEW', 'APPROVED'],
                index=['DRAFT', 'REVIEW', 'APPROVED'].index(status_row[0]),
                key=f'status_{entry["id"]}_{selected}'
            )
            if st.button('Сохранить статус', key=f'save_status_{entry["id"]}_{selected}'):
                if new_status == 'APPROVED':
                    with sqlite3.connect(BASE / 'database' / 'studio.db') as db:

                        latest_image = db.execute(
                            '''
                            SELECT i.status
                            FROM images i
                            JOIN cards c ON c.id = i.card_id
                            WHERE c.collection_id = ?
                              AND c.position = ?
                            ORDER BY i.id DESC
                            LIMIT 1
                            ''',
                            (collection_id, selected)
                        ).fetchone()

                    if latest_image is None or latest_image[0] != 'APPROVED':
                        st.error(
                            'Нельзя утвердить карточку: '
                            'её актуальное изображение не утверждено.'
                        )
                        st.stop()
                with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
                    db.execute(
                        'UPDATE cards SET status = ?, updated_at = CURRENT_TIMESTAMP '
                        'WHERE collection_id = ? AND position = ?',
                        (new_status, collection_id, selected)
                    )

                st.success(f'Статус карточки изменён на {new_status}')
                st.rerun()
    ppath = prompt_path(entry, selected)
    left, right = st.columns([1, 1.3], gap='large')
    with left:
        st.markdown('**Текущее изображение**')
        if entry['id'].startswith('db_'):
            with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
                image_row = db.execute(
                    '''
                    SELECT i.status
                    FROM images i
                    JOIN cards c ON c.id = i.card_id
                    WHERE c.collection_id = ? AND c.position = ?
                    ORDER BY i.id DESC
                    LIMIT 1
                    ''',
                    (collection_id, selected)
                ).fetchone()

            st.caption(
                f'Статус изображения: {image_row[0]}'
                if image_row else 'Статус изображения: нет изображения'
            )
            if image_row:
                new_image_status = st.selectbox(
                    'Изменить статус изображения',
                    ['DRAFT', 'REVIEW', 'APPROVED'],
                    index=['DRAFT', 'REVIEW', 'APPROVED'].index(image_row[0]),
                    key=f'image_status_{entry["id"]}_{selected}'
                )
                if st.button(
                    'Сохранить статус изображения',
                    key=f'save_image_status_{entry["id"]}_{selected}'
                ):
                    with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
                        db.execute(
                            '''
                            UPDATE images
                            SET status = ?
                            WHERE id = (
                                SELECT i.id
                                FROM images i
                                JOIN cards c ON c.id = i.card_id
                                WHERE c.collection_id = ?
                                  AND c.position = ?
                                ORDER BY i.id DESC
                                LIMIT 1
                            )
                            ''',
                            (new_image_status, collection_id, selected)
                        )
                        if new_image_status != 'APPROVED':
                            db.execute(
                                '''
                                UPDATE cards
                                SET status = 'REVIEW',
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE collection_id = ?
                                  AND position = ?
                                  AND status = 'APPROVED'
                                ''',
                                (collection_id, selected)
                            )
        image_preview(path, height=400)
        st.caption('Загружено' if path.is_file() else 'Нет изображения')
        if True:
            st.markdown('**AI-проверка качества**')

            if st.button(
                'Проверить изображение с помощью GigaChat',
                disabled=not path.is_file(),
                key=f'ai_qa_{entry["id"]}_{selected}'
            ):
                with st.spinner('GigaChat анализирует изображение...'):
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(BASE / 'test_vision.py'),
                            str(selected),
                            str(path.resolve()),
                            entry['id']
                        ],
                        cwd=BASE,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        timeout=180
                    )

                if result.returncode == 0:
                    st.success('AI-проверка завершена!')
                    report_path = BASE / 'vision_reports' / f"{entry['id']}_card_{selected:02d}_vision.json"

                    if report_path.is_file():
                        report = json.loads(report_path.read_text(encoding='utf-8'))
                        analysis = report['analysis']

                        st.metric('Оценка AI', f"{analysis['score']} / 10")
                        st.write('**Результат проверки:**', analysis['status'])
                        st.markdown('**Замечания AI QA**')

                        issues = analysis.get('issues', [])

                        if not issues:
                            st.success('Замечаний не обнаружено.')
                        else:
                            for number, issue in enumerate(issues, start=1):
                                with st.expander(
                                    f"{number}. {issue.get('category', 'Проблема')} — "
                                    f"{issue.get('severity', 'unknown')}"
                                ):
                                    st.write('**Проблема:**', issue.get('description', ''))
                                    st.write('**Рекомендация:**', issue.get('recommendation', ''))
                                    st.write('**Обоснование:**', issue.get('evidence', ''))
                                    st.write('**Вердикт:**', issue.get('verdict', ''))
                else:
                    st.error('Ошибка при проверке изображения')
                    st.code(result.stderr or result.stdout)
            saved_report_path = (
                BASE / 'vision_reports' / f"{entry['id']}_card_{selected:02d}_vision.json"
            )

            if saved_report_path.is_file():
                with st.expander('Последний сохранённый отчёт AI QA'):
                    saved_report = json.loads(
                        saved_report_path.read_text(encoding='utf-8')
                    )
                    st.json(saved_report['analysis'])
        st.write('**Загрузка изображения**')

        if st.button(
            '🔄 Сгенерировать изображение повторно',
            key=f'regenerate_image_{entry["id"]}_{selected}'
        ):
            st.info(
                'Повторная генерация выбранного изображения будет '
                'доступна после подключения Image Generation API. '
                'Промпт карточки будет использоваться повторно, '
                'остальные изображения коллекции не изменятся.'
            )

        upload = st.file_uploader(
            'PNG или JPG',
            type=['png', 'jpg', 'jpeg'],
            key=f'upload_{entry["id"]}_{selected}'
        )

        if upload is not None:
            try:
                with Image.open(upload) as src:
                    candidate = ImageOps.exif_transpose(src).convert('RGB')

                st.image(candidate, caption='Предпросмотр', width=220)

                overwrite = (
                    st.checkbox(
                        'Разрешить замену существующего файла',
                        key=f'overwrite_{entry["id"]}_{selected}'
                    )
                    if path.exists() else True
                )

                if st.button('Сохранить изображение', disabled=not overwrite):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    candidate.save(path, format='PNG')

                    if entry['id'].startswith('db_'):
                        collection_id = int(entry['id'][3:])

                        with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
                            card_row = db.execute(
                                'SELECT id FROM cards WHERE collection_id = ? AND position = ?',
                                (collection_id, selected)
                            ).fetchone()

                            if card_row is None:
                                st.error('Карточка не найдена в базе данных.')
                                st.stop()

                            relative_path = path.relative_to(BASE).as_posix()

                            db.execute(
                                'INSERT INTO images (card_id, file_path, status) VALUES (?, ?, ?)',
                                (card_row[0], relative_path, 'DRAFT')
                            )

                    st.success('Изображение сохранено')
                    st.rerun()

            except Exception as exc:
                st.error(f'Файл не удалось обработать: {exc}')
    with right:
        st.markdown('**Промпт изображения**')
        current_prompt = prompt_for(entry, selected)

        current_prompt = reference_style_prompt(current_prompt)
        current_category = entry['cards'][selected - 1].get('category')
        available_refs = [p for p in sorted((VISUAL_REF_DIR / f'category_{current_category}').glob('*')) if p.suffix.lower() in ('.png','.jpg','.jpeg','.webp')]
        if available_refs:
            st.caption('При генерации изображения прикрепи один из этих эталонов к промпту:')
            st.image([str(p) for p in available_refs[:3]], width=130)

        edited = st.text_area('Текст промпта', value=current_prompt, height=430,
                              key=f'prompt_{entry["id"]}_{selected}')
        if st.button('Сохранить промпт'):
            ppath.parent.mkdir(parents=True, exist_ok=True)
            ppath.write_text(edited, encoding='utf-8')

            if entry['id'].startswith('db_'):
                collection_id = int(entry['id'][3:])

                with sqlite3.connect(BASE / 'database' / 'studio.db') as db:
                    card_row = db.execute(
                        'SELECT id FROM cards WHERE collection_id = ? AND position = ?',
                        (collection_id, selected)
                    ).fetchone()

                    if card_row is None:
                        st.error('Карточка не найдена в базе данных.')
                        st.stop()

                    existing = db.execute(
                        'SELECT id FROM prompts WHERE card_id = ? ORDER BY id DESC LIMIT 1',
                        (card_row[0],)
                    ).fetchone()

                    if existing:
                        db.execute(
                            'UPDATE prompts SET prompt_text = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                            (edited, existing[0])
                        )
                    else:
                        db.execute(
                            'INSERT INTO prompts (card_id, prompt_text) VALUES (?, ?)',
                            (card_row[0], edited)
                        )

            st.success('Промпт сохранён в файл и SQLite')
        if not current_prompt:
            st.caption('Для этой карточки промпт ещё не подготовлен.')

else:
    st.subheader('Проверка качества')

    a, b, c = st.columns(3)
    a.metric('Всего карточек', len(cards))
    b.metric('Изображений готово', ready)
    c.metric('Осталось', len(cards) - ready)

    st.progress(ready / len(cards))

    st.markdown('### Техническая проверка')
    st.caption(
        'Проверяем формат, разрешение, пропорции 43:48 '
        'и целостность файлов. Бесплатно, без AI API.'
    )

    if st.button(
        '🔍 Проверить все изображения',
        type='primary'
    ):
        results = []

        for index, card in enumerate(cards, start=1):
            path = image_path(entry, index)

            if path.is_file():
                result = check_image(path)
            else:
                result = {
                    'file': path.name,
                    'status': 'MISSING',
                    'width': None,
                    'height': None,
                    'format': None,
                    'errors': ['Изображение отсутствует'],
                }

            result['card_number'] = index
            result['card_name'] = card_name(card, index)
            results.append(result)

        st.session_state[
            f'qc_results_{entry["id"]}'
        ] = results

    results = st.session_state.get(
        f'qc_results_{entry["id"]}'
    )

    if results:
        passed = sum(
            r['status'] == 'PASS'
            for r in results
        )
        failed = sum(
            r['status'] == 'FAIL'
            for r in results
        )
        missing = sum(
            r['status'] == 'MISSING'
            for r in results
        )

        st.divider()

        x, y, z = st.columns(3)
        x.metric('Прошли проверку', passed)
        y.metric('Ошибки', failed)
        z.metric('Нет изображения', missing)

        for result in results:
            status = result['status']

            if status == 'PASS':
                symbol = '✅'
            elif status == 'FAIL':
                symbol = '❌'
            else:
                symbol = '⚪'

            title = (
                f"{symbol} "
                f"{result['card_number']:02d}. "
                f"{result['card_name']}"
            )

            with st.expander(title):
                st.write(
                    'Статус:',
                    status
                )

                if result['width'] is not None:
                    st.write(
                        'Разрешение:',
                        f"{result['width']} × "
                        f"{result['height']}"
                    )

                    st.write(
                        'Формат:',
                        result['format']
                    )

                if result['errors']:
                    for error in result['errors']:
                        st.error(error)
                else:
                    st.success(
                        'Все технические требования выполнены'
                    )

        st.download_button(
            '📥 Скачать технический отчёт JSON',
            data=json.dumps(
                results,
                ensure_ascii=False,
                indent=2
            ),
            file_name='technical_qc_report.json',
            mime='application/json',
        )

    else:
        st.info(
            'Нажми кнопку проверки, чтобы получить '
            'отчёт по текущей коллекции.'
        )

    st.divider()
    st.subheader('🤖 AI-проверка изображений — GigaChat Vision')

    available_images = [
        (i, image_path(entry, i))
        for i in range(1, len(cards) + 1)
        if image_path(entry, i).is_file()
    ]

    st.caption(
        f'Доступно для AI-проверки: {len(available_images)} '
        f'из {len(cards)} изображений.'
    )

    if st.button(
        '🤖 Проверить все изображения через GigaChat',
        disabled=not available_images,
        key=f'run_batch_ai_{entry["id"]}'
    ):
        ai_results = []
        progress = st.progress(0)

        for number, (card_index, card_path) in enumerate(available_images, start=1):
            with st.spinner(
                f'Проверка {number}/{len(available_images)}: '
                f'{card_name(cards[card_index - 1], card_index)}'
            ):
                try:
                    result = subprocess.run(
                        [
                            sys.executable,
                            str(BASE / 'test_vision.py'),
                            str(card_index),
                            str(card_path.resolve()),
                            entry['id']
                        ],
                        cwd=BASE,
                        capture_output=True,
                        text=True,
                        encoding='utf-8',
                        errors='replace',
                        timeout=180
                    )

                    report_path = (
                        BASE / 'vision_reports'
                        / f"{entry['id']}_card_{card_index:02d}_vision.json"
                    )

                    if result.returncode == 0 and report_path.is_file():
                        report = json.loads(
                            report_path.read_text(encoding='utf-8')
                        )
                        ai_results.append({
                            'card': card_name(cards[card_index - 1], card_index),
                            'number': card_index,
                            'analysis': report['analysis'],
                            'error': None
                        })
                    else:
                        ai_results.append({
                            'card': card_name(cards[card_index - 1], card_index),
                            'number': card_index,
                            'analysis': None,
                            'error': result.stderr or result.stdout or 'Отчёт не найден'
                        })

                except Exception as exc:
                    ai_results.append({
                        'card': card_name(cards[card_index - 1], card_index),
                        'number': card_index,
                        'analysis': None,
                        'error': str(exc)
                    })

            progress.progress(number / len(available_images))

        st.session_state[f'batch_ai_results_{entry["id"]}'] = ai_results

    saved_results = st.session_state.get(
        f'batch_ai_results_{entry["id"]}', []
    )

    if saved_results:
        for item in saved_results:
            with st.expander(
                f"{item['number']:02d}. {item['card']}",
                expanded=False
            ):
                if item['error']:
                    st.error(item['error'])
                else:
                    analysis = item['analysis']
                    st.metric('Оценка AI', f"{analysis.get('score', '—')} / 10")
                    st.write('**Статус:**', analysis.get('status', '—'))

                    issues = analysis.get('issues', [])
                    if not issues:
                        st.success('Замечаний не обнаружено.')
                    else:
                        for issue in issues:
                            st.write(
                                f"**{issue.get('category', 'Проблема')}** "
                                f"({issue.get('severity', '—')})"
                            )
                            st.write(issue.get('description', ''))
                            st.caption(
                                issue.get('recommendation', '')
                            )

        st.download_button(
            '📥 Скачать AI-отчёт JSON',
            data=json.dumps(
                saved_results,
                ensure_ascii=False,
                indent=2
            ),
            file_name=f"ai_qa_{entry['id']}.json",
            mime='application/json',
            key=f'download_ai_{entry["id"]}'
        )
