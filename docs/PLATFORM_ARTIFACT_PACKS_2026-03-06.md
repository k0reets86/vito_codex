# Platform Artifact Packs (Preflight)

Цель: перед любой публикацией сначала собрать полный пакет артефактов и полей, и только затем вызывать publish-flow.

## Что добавлено в код

- `modules/platform_artifact_pack.py`
  - `PLATFORM_PACKS` — карта обязательных полей/артефактов по платформам.
  - `build_platform_bundle(platform, payload)` — детерминированно собирает payload (тексты + файлы + SEO-блок) заранее.
- Подключено в:
  - `decision_loop.py` (Gumroad publish route).
  - `scripts/live_publish_matrix.py` (единый preflight payload для live тестов).

## Пакеты по платформам

1. `gumroad`
- Обязательные поля: `name`, `description`, `price`, `category`, `tags`
- Обязательные артефакты: `pdf_path`, `cover_path`, `thumb_path`

2. `etsy`
- Обязательные поля: `title`, `description`, `price`, `category`, `tags`
- Обязательные артефакты: `cover_path`

3. `kofi`
- Обязательные поля: `title`, `description`, `price`
- Обязательные артефакты: `cover_path`

4. `amazon_kdp`
- Обязательные поля: `title`, `description`, `keywords`
- Обязательные артефакты: `pdf_path`, `cover_path`

5. `twitter`
- Обязательные поля: `text`
- Обязательные артефакты: `image_path`

6. `reddit`
- Обязательные поля: `subreddit`, `title`
- Обязательные артефакты: `image_path`

7. `pinterest`
- Обязательные поля: `title`, `description`, `url`
- Обязательные артефакты: `image_path`

8. `printful`
- Обязательные поля: `sync_product`, `sync_variants`
- Обязательные артефакты: `image_path`

## Артефакты по умолчанию

Используются заранее подготовленные файлы из `output/`:
- PDF: `output/The_AI_Side_Hustle_Playbook_v2.pdf`
- Cover: `output/ai_side_hustle_cover_1280x720.png`
- Thumb: `output/ai_side_hustle_thumb_600x600.png`
- Social image: `output/social/vito_social_test.png` (fallback на cover/thumb)

Это исключает хаотичный поиск файлов “на лету” в publish-цикле.

