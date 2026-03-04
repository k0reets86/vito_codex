# Digital Platform Spec Playbook (for VITO)

Цель: единый практический справочник по платформам из `.env` и runtime-каталога VITO: обязательные поля, ограничения, публикация, удаление, и что проверять перед live-действиями.

## 1) Платформы из текущей конфигурации VITO
- Commerce: Gumroad, Etsy, Amazon KDP, Printful, Ko-fi
- Social/Content: X(Twitter), Reddit (browser-only), YouTube
- Infra/LLM: Gemini/Google, OpenAI, Cloudinary (поддержка, не storefront)

## 2) Универсальный preflight перед публикацией
1. Проверить auth/cookie/token (live probe если есть).
2. Проверить обязательные поля карточки.
3. Проверить ограничения медиа (размер/формат/длительность).
4. Выполнить dry-run/payload validation.
5. Только после этого запускать live publish.
6. После publish записать evidence: URL/ID/время/статус.

## 3) Спецификации по платформам

### 3.1 Gumroad
- Базовые поля: `name/title`, `description`, `price`, `content file`, `cover`.
- Для digital delivery важно: корректный файл и preview-обложка.
- В VITO: API + browser fallback, dry-run уже поддержан.
- Практика VITO: перед live-публикацией выполнять auth probe и проверку доступности dashboard.
- Источники:
  - https://gumroad.com/api
  - https://gumroad.com/help

### 3.2 Etsy (digital listing)
- Базовые поля: `title`, `description`, `price`, `who_made`, `when_made`, `taxonomy/category`, `tags`, `files`.
- Digital files: до 5 файлов на listing, лимит 20MB на файл (instant download).
- Изображения listing: high-res, минимум 2000px по ширине (рекомендовано Etsy).
- В VITO: OAuth2 PKCE + fallback browser session capture.
- Источники:
  - https://developer.etsy.com/documentation/
  - https://developer.etsy.com/documentation/essentials/authentication/
  - https://help.etsy.com/hc/en-us/articles/115015628347-How-to-Manage-Your-Digital-Listings

### 3.3 Amazon KDP
- Базовые поля: metadata книги, manuscript, cover, pricing/territories.
- Cover/manuscript требования зависят от формата (ebook/paperback/hardcover).
- В текущем контуре VITO: browser flow + session state/probe; API официального публичного publish-интерфейса нет.
- Источники:
  - https://kdp.amazon.com/en_US/help
  - https://kdp.amazon.com/en_US/help/topic/G201113520

### 3.4 Printful
- Базовые поля: `store`, `product template/data`, `mockups/files`, `pricing`.
- Ключевая проверка: доступ к store перед созданием/публикацией.
- В VITO: auth через API token, dry-run подготовка включена.
- Источники:
  - https://developers.printful.com/
  - https://developers.printful.com/docs/

### 3.5 Ko-fi
- Базовые поля: `title`, `description`, `price`, `file/media`.
- Ограничения зависят от плана аккаунта и политики контента.
- В VITO: поддержан dry-run/prepare flow.
- Источник:
  - https://help.ko-fi.com/hc/en-us

### 3.6 X (Twitter)
- Базовые поля: `text` (и media при наличии media flow).
- В VITO: OAuth1 user-context, auth probe через `/2/users/me`, dry-run публикации реализован.
- Источники:
  - https://developer.x.com/en/docs
  - https://developer.x.com/en/docs/tutorials/authenticating-with-twitter-api-for-enterprise/oauth1-0a-and-user-access-tokens

### 3.7 Reddit
- В текущем режиме VITO: browser-only по owner policy.
- Если API включать позже: OAuth app/script + rate-limit дисциплина.
- Источники:
  - https://www.reddit.com/dev/api/
  - https://support.reddithelp.com/hc/en-us/articles/14945211791892-Developer-Platform-Overview

### 3.8 YouTube
- Базовые поля upload: `title`, `description`, `privacyStatus`, `video file`, `thumbnail` (опционально).
- Для upload обязателен OAuth scope `youtube.upload` (API key недостаточно).
- В VITO: dry-run слой есть; для live нужен устойчивый OAuth refresh token.
- Источники:
  - https://developers.google.com/youtube/v3
  - https://developers.google.com/youtube/v3/guides/uploading_a_video

## 4) Что VITO должен запоминать как «правило навыка»
- Не публиковать live без preflight и evidence.
- Если live-check auth не пройден, не делать вид что публикация выполнена.
- Для browser-only платформ хранить: `session_age`, `last_live_probe`, `manual_confirmed_at`.
- Для каждой платформы вести структуру ошибок: `auth`, `validation`, `rate_limit`, `policy_block`.

## 5) Практический статус тестов этого пакета
- Dry-run E2E по платформам: `reports/VITO_PLATFORM_E2E_DRYRUN_2026-03-04_0656UTC.json`
- Social SDK dry-run: `reports/VITO_SOCIAL_SDK_DRYRUN_2026-03-04_0656UTC.json`
- Smoke scorecard: `reports/PLATFORM_SMOKE_SCORECARD_2026-02-25.json`

Важно: dry-run подтверждает корректность пайплайна подготовки, но не доказывает фактический live publish/delete на стороне внешней платформы.
