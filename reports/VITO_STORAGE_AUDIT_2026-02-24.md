# Аудит файлов и папок VITO (без удаления)
Дата: 2026-02-24

## Что проверено
- Полный обход файлов `/home/vito/vito-agent` и смежных директорий `/home/vito`.
- Размеры директорий, крупные файлы, подозрительные каталоги, владельцы файлов, кеши, пустые файлы, битые symlink.
- Ничего не удалялось и не изменялось.

## Ключевые цифры
- Файлов в `vito-agent`: 23729
- Файлов в `vito_dashboard_src`: 9914
- Размер `vito-agent`: 1.6G
- Размер `backups`: 1.6G (основной потребитель)
- Размер `logs`: 9.5M
- Размер `output`: 27M
- Размер `memory`: 7.2M
- Каталогов `__pycache__`: 138
- Каталогов `.pytest_cache`: 30

## Основные находки
- Найдено `MagicMock`-каталогов в корне `vito-agent`: 117.
- Найдено `MagicMock`-каталогов в `backups`: 699.
- Это мусорные артефакты тестов/моков (`<MagicMock name=...>`), занимают место и засоряют структуру.
- Обнаружены root-owned файлы внутри проекта (потенциальные проблемы прав записи для `vito`).
- Крупнейший файл: `backups/manual_before_gumroad_20260224_091542.tgz` (~820MB).
- Крупные папки вне проекта: `~/.cache/ms-playwright` (~929MB).

## Root-owned элементы (первые 40)
root:root	/home/vito/vito-agent/.claude/settings.local.json
root:root	/home/vito/vito-agent/vito_agent_prompts.md
root:root	/home/vito/vito-agent/output/social/instagram_1771767273.txt
root:root	/home/vito/vito-agent/output/social/twitter_1771767273.txt
root:root	/home/vito/vito-agent/output/social/twitter_1771768916.txt
root:root	/home/vito/vito-agent/output/social/instagram_1771768916.txt
root:root	/home/vito/vito-agent/output/articles/python_tips_1771767258.md
root:root	/home/vito/vito-agent/output/articles/написать_статью_о_ai_шаблонах_1771768579.md
root:root	/home/vito/vito-agent/output/articles/python_tips_1771768900.md
root:root	/home/vito/vito-agent/output/articles/написать_статью_о_ai_шаблонах_1771767262.md
root:root	/home/vito/vito-agent/output/articles/ai_guide_1771767258.md
root:root	/home/vito/vito-agent/output/articles/ai_guide_1771768900.md
root:root	/home/vito/vito-agent/output/articles/написать_статью_о_ai_шаблонах_1771768873.md
root:root	/home/vito/vito-agent/output/articles/написать_статью_о_ai_шаблонах_1771768904.md
root:root	/home/vito/vito-agent/Dashboard.tsx
root:root	/home/vito/vito-agent/__pycache__/conftest.cpython-312-pytest-9.0.2.pyc
root:root	/home/vito/vito-agent/backups/20260222_135619
root:root	/home/vito/vito-agent/backups/20260222_135619/.env
root:root	/home/vito/vito-agent/backups/20260222_135619/test_vito.db
root:root	/home/vito/vito-agent/backups/20260222_135619/settings.py
root:root	/home/vito/vito-agent/backups/20260222_140145
root:root	/home/vito/vito-agent/backups/20260222_140145/.env
root:root	/home/vito/vito-agent/backups/20260222_140145/test_vito.db
root:root	/home/vito/vito-agent/backups/20260222_140145/settings.py
root:root	/home/vito/vito-agent/backups/20260222_140114
root:root	/home/vito/vito-agent/backups/20260222_140114/.env
root:root	/home/vito/vito-agent/backups/20260222_140114/test_vito.db
root:root	/home/vito/vito-agent/backups/20260222_140114/settings.py
root:root	/home/vito/vito-agent/backups/backup_20260222_083409/__pycache__
root:root	/home/vito/vito-agent/backups/backup_20260222_083409/__pycache__/conftest.cpython-312-pytest-9.0.2.pyc
root:root	/home/vito/vito-agent/backups/20260222_133422
root:root	/home/vito/vito-agent/backups/20260222_133422/.env
root:root	/home/vito/vito-agent/backups/20260222_133422/test_vito.db
root:root	/home/vito/vito-agent/backups/20260222_133422/settings.py

## Крупные файлы (первые 60)
819947290	/home/vito/vito-agent/backups/manual_before_gumroad_20260224_091542.tgz
448737824	/home/vito/.cache/ms-playwright/chromium-1208/chrome-linux/chrome
287892096	/home/vito/.cache/ms-playwright/chromium_headless_shell-1208/chrome-linux/headless_shell
90387606	/home/vito/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx/model.onnx
83178821	/home/vito/.cache/chroma/onnx_models/all-MiniLM-L6-v2/onnx.tar.gz
42916239	/home/vito/.codex/sessions/2026/02/23/rollout-2026-02-23T01-42-16-019c8829-5609-7232-9b9d-4c6f4218048a.jsonl
38728544	/home/vito/.npm/_cacache/content-v2/sha512/fe/1b/c7f15c1d5df0d5c232e4aa77bc983d99fddfaef9edd6de699d34a1b95085e808ed35278b9558d18923c28b6ef3ca98236ea6b2c0947ff00c8e532d32d297
27844152	/home/vito/vito-agent/backups/manual_before_gumroad_20260224_091626.tgz
26506096	/home/vito/vito-backup-20260223-0052.tar.gz
26506096	/home/vito/vito-backup-20260223-0051.tar.gz
24106104	/home/vito/.cache/ms-playwright/chromium_headless_shell-1208/chrome-linux/libvk_swiftshader.so
24106104	/home/vito/.cache/ms-playwright/chromium-1208/chrome-linux/libvk_swiftshader.so
22457517	/home/vito/.claude/projects/-home-vito-vito-agent/ed1c304d-cdf3-4b41-bb1c-e62f0afdeff9.jsonl
819947290	/home/vito/vito-agent/backups/manual_before_gumroad_20260224_091542.tgz
27844152	/home/vito/vito-agent/backups/manual_before_gumroad_20260224_091626.tgz
7807717	/home/vito/vito-agent/logs/vito.log
7387923	/home/vito/vito-agent/backups/manual_20260224_174941/logs/vito.log
5566464	/home/vito/vito-agent/memory/chroma_db/chroma.sqlite3
4517888	/home/vito/vito-agent/backups/manual_20260224_174941/memory/chroma_db/chroma.sqlite3
4136432	/home/vito/vito-agent/backups/manual_20260224_020252/logs/vito.log
3341975	/home/vito/vito-agent/backups/manual_skill_registry_20260223_213958/logs/vito.log
3309422	/home/vito/vito-agent/backups/manual_learning_protocol_20260223_211946/logs/vito.log
3244712	/home/vito/vito-agent/backups/manual_envfix_20260223_204350/logs/vito.log
3226384	/home/vito/vito-agent/backups/manual_media_20260223_202700/logs/vito.log
3068029	/home/vito/vito-agent/backups/manual_post_audit_20260223_193813/logs/vito.log
3053353	/home/vito/vito-agent/backups/manual_post_audit_20260223_193149/logs/vito.log
2727936	/home/vito/vito-agent/backups/manual_20260224_020252/memory/chroma_db/chroma.sqlite3
2265479	/home/vito/vito-agent/backups/manual_post_audit_20260223_111904/logs/vito.log
2247867	/home/vito/vito-agent/backups/manual_post_audit_20260223_105325/logs/vito.log
2247867	/home/vito/vito-agent/backups/manual_audit_20260223_105144/logs/vito.log
2233492	/home/vito/vito-agent/backups/manual_post_audit_20260223_104855/logs/vito.log
2218387	/home/vito/vito-agent/backups/manual_post_audit_20260223_104436/logs/vito.log
2218387	/home/vito/vito-agent/backups/manual_audit_20260223_104250/logs/vito.log
2105344	/home/vito/vito-agent/backups/manual_skill_registry_20260223_213958/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_post_audit_20260223_193813/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_post_audit_20260223_193149/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_post_audit_20260223_111904/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_post_audit_20260223_105325/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_post_audit_20260223_104855/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_post_audit_20260223_104436/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_media_20260223_202700/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_learning_protocol_20260223_211946/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_envfix_20260223_204350/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_audit_20260223_105144/memory/chroma_db/chroma.sqlite3
2105344	/home/vito/vito-agent/backups/manual_audit_20260223_104250/memory/chroma_db/chroma.sqlite3
1867495	/home/vito/vito-agent/logs/errors.log
1867495	/home/vito/vito-agent/backups/manual_20260224_174941/logs/errors.log
1671168	/home/vito/vito-agent/memory/vito_local.db
1635040	/home/vito/vito-agent/backups/manual_20260224_020252/logs/errors.log
1385461	/home/vito/vito-agent/backups/manual_skill_registry_20260223_213958/logs/errors.log
1385461	/home/vito/vito-agent/backups/manual_post_audit_20260223_193813/logs/errors.log
1385461	/home/vito/vito-agent/backups/manual_post_audit_20260223_193149/logs/errors.log
1385461	/home/vito/vito-agent/backups/manual_media_20260223_202700/logs/errors.log
1385461	/home/vito/vito-agent/backups/manual_learning_protocol_20260223_211946/logs/errors.log
1385461	/home/vito/vito-agent/backups/manual_envfix_20260223_204350/logs/errors.log
1040384	/home/vito/vito-agent/backups/manual_20260224_174941/memory/vito_local.db
962560	/home/vito/vito-agent/backups/manual_20260224_110640/vito_local.db
919833	/home/vito/vito-agent/backups/manual_post_audit_20260223_111904/logs/errors.log
919833	/home/vito/vito-agent/backups/manual_post_audit_20260223_105325/logs/errors.log
919833	/home/vito/vito-agent/backups/manual_post_audit_20260223_104855/logs/errors.log

## Риски
- Рост диска из-за множества бэкапов и артефактов тестов.
- Нестабильность задач, если агенту нужны права записи в root-owned файлы.
- Сложнее ориентироваться и обслуживать проект из-за мусорных директорий.

## Безопасный план очистки (ПОСЛЕ ТВОЕГО ОК)
- Удалить только `MagicMock`-директории в корне проекта и в `backups/*`.
- Перенести старые `*.tgz` бэкапы старше N дней в cold storage.
- Нормализовать владельцев в проекте: `chown -R vito:vito /home/vito/vito-agent` (точечно по списку).
- Добавить защиту в тестах, чтобы пути с `MagicMock` не создавались на диске.
- Ввести ротацию логов и бэкапов по политике сроков хранения.

## Сырые отчёты
- `reports/server_full_scan_2026-02-24_part1.txt`
- `reports/server_full_scan_2026-02-24_part2.txt`