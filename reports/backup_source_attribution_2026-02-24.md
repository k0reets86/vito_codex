# Атрибуция источников бэкапов
Дата: 2026-02-24

Метод: эвристики по имени, содержимому папок, корреляции с journalctl/history. Это вероятностная классификация.

## Сводка
- legacy_or_cloudcode_auto: 27
- legacy_test_backup: 11
- auto_backup_script: 3
- manual/codex_session: 29

## Таблица
| backup | source | confidence | mtime_utc | notes |
|---|---:|---:|---:|---|
| `20260221_191011` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:10:11 | timestamp-only naming, ambiguous source |
| `20260221_191046` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:10:46 | timestamp-only naming, ambiguous source |
| `20260221_191300` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:13:01 | timestamp-only naming, ambiguous source |
| `20260221_191333` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:13:33 | timestamp-only naming, ambiguous source |
| `20260221_191357` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:13:57 | timestamp-only naming, ambiguous source |
| `20260221_192046` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:20:46 | timestamp-only naming, ambiguous source |
| `20260221_192620` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:26:20 | timestamp-only naming, ambiguous source |
| `20260221_193211` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:32:11 | timestamp-only naming, ambiguous source |
| `20260221_194459` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:44:59 | timestamp-only naming, ambiguous source |
| `20260221_195523` | legacy_or_cloudcode_auto | 0.55 | 2026-02-21 19:55:23 | timestamp-only naming, ambiguous source |
| `20260222_133422` | legacy_test_backup | 0.7 | 2026-02-22 13:34:22 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260222_135619` | legacy_test_backup | 0.7 | 2026-02-22 13:56:19 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260222_140114` | legacy_test_backup | 0.7 | 2026-02-22 14:01:14 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260222_140145` | legacy_test_backup | 0.7 | 2026-02-22 14:01:45 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260222_145241` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 14:52:41 | timestamp-only naming, ambiguous source |
| `20260222_145314` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 14:53:14 | timestamp-only naming, ambiguous source |
| `20260222_151141` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 15:11:41 | timestamp-only naming, ambiguous source |
| `20260222_152108` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 15:21:08 | timestamp-only naming, ambiguous source |
| `20260222_152936` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 15:29:36 | timestamp-only naming, ambiguous source |
| `20260222_154854` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 15:48:54 | timestamp-only naming, ambiguous source |
| `20260222_173514` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 17:35:14 | timestamp-only naming, ambiguous source |
| `20260222_173542` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 17:35:42 | timestamp-only naming, ambiguous source |
| `20260222_181020` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 18:10:20 | timestamp-only naming, ambiguous source |
| `20260222_181109` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 18:11:09 | timestamp-only naming, ambiguous source |
| `20260222_181206` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 18:12:06 | timestamp-only naming, ambiguous source |
| `20260222_181256` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 18:12:56 | timestamp-only naming, ambiguous source |
| `20260222_190056` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 19:00:56 | timestamp-only naming, ambiguous source |
| `20260222_201203` | legacy_test_backup | 0.7 | 2026-02-22 20:12:03 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260222_201407` | legacy_test_backup | 0.7 | 2026-02-22 20:14:07 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260222_203639` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 20:36:39 | timestamp-only naming, ambiguous source |
| `20260222_221603` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 22:16:03 | timestamp-only naming, ambiguous source |
| `20260222_221921` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 22:19:21 | timestamp-only naming, ambiguous source |
| `20260222_223011` | legacy_or_cloudcode_auto | 0.55 | 2026-02-22 22:30:11 | timestamp-only naming, ambiguous source |
| `20260222_234104` | legacy_test_backup | 0.7 | 2026-02-22 23:41:04 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260223_063458` | legacy_test_backup | 0.7 | 2026-02-23 06:34:58 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260223_064116` | legacy_test_backup | 0.7 | 2026-02-23 06:41:16 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260223_095317` | legacy_test_backup | 0.7 | 2026-02-23 09:53:17 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `20260223_102612` | legacy_test_backup | 0.7 | 2026-02-23 10:26:12 | timestamp-only naming, ambiguous source; contains test_vito.db typical of older backup flow |
| `backup_20260222_083409` | auto_backup_script | 0.78 | 2026-02-22 13:34:03 | prefix backup_ indicates scripted backup |
| `backup_20260223_063600` | auto_backup_script | 0.78 | 2026-02-23 06:35:10 | prefix backup_ indicates scripted backup |
| `backup_20260224_003445` | auto_backup_script | 0.78 | 2026-02-24 00:22:42 | prefix backup_ indicates scripted backup |
| `manual_20260223_020809` | manual/codex_session | 0.95 | 2026-02-23 02:08:09 | prefix/name indicates manual backup |
| `manual_20260223_021726` | manual/codex_session | 0.95 | 2026-02-23 02:17:26 | prefix/name indicates manual backup |
| `manual_20260223_062804` | manual/codex_session | 0.95 | 2026-02-23 06:28:04 | prefix/name indicates manual backup |
| `manual_20260223_094659` | manual/codex_session | 0.95 | 2026-02-23 09:46:59 | prefix/name indicates manual backup |
| `manual_20260224_020252` | manual/codex_session | 0.95 | 2026-02-24 01:08:07 | prefix/name indicates manual backup |
| `manual_20260224_110640` | manual/codex_session | 0.95 | 2026-02-24 11:06:40 | prefix/name indicates manual backup |
| `manual_20260224_174941` | manual/codex_session | 0.95 | 2026-02-24 17:08:20 | prefix/name indicates manual backup |
| `manual_audit_20260223_104250` | manual/codex_session | 0.95 | 2026-02-23 10:26:27 | prefix/name indicates manual backup |
| `manual_audit_20260223_105144` | manual/codex_session | 0.95 | 2026-02-23 10:44:20 | prefix/name indicates manual backup |
| `manual_before_gumroad_20260224_091542.tgz` | manual/codex_session | 0.98 | 2026-02-24 09:16:16 | prefix/name indicates manual backup; explicit manual_before_gumroad archive naming |
| `manual_before_gumroad_20260224_091626.tgz` | manual/codex_session | 0.98 | 2026-02-24 09:16:28 | prefix/name indicates manual backup; explicit manual_before_gumroad archive naming |
| `manual_envfix_20260223_204350` | manual/codex_session | 0.95 | 2026-02-23 11:27:35 | prefix/name indicates manual backup |
| `manual_learning_protocol_20260223_211946` | manual/codex_session | 0.95 | 2026-02-23 11:27:35 | prefix/name indicates manual backup |
| `manual_media_20260223_202700` | manual/codex_session | 0.95 | 2026-02-23 11:27:35 | prefix/name indicates manual backup |
| `manual_post_20260223_021456` | manual/codex_session | 0.95 | 2026-02-23 02:14:57 | prefix/name indicates manual backup |
| `manual_post_20260223_021528` | manual/codex_session | 0.95 | 2026-02-23 02:15:28 | prefix/name indicates manual backup |
| `manual_post_20260223_021830` | manual/codex_session | 0.95 | 2026-02-23 02:18:30 | prefix/name indicates manual backup |
| `manual_post_20260223_061107` | manual/codex_session | 0.95 | 2026-02-23 06:11:07 | prefix/name indicates manual backup |
| `manual_post_20260223_061129` | manual/codex_session | 0.95 | 2026-02-23 06:11:29 | prefix/name indicates manual backup |
| `manual_post_20260223_061142` | manual/codex_session | 0.95 | 2026-02-23 06:11:42 | prefix/name indicates manual backup |
| `manual_post_20260223_061157` | manual/codex_session | 0.95 | 2026-02-23 06:11:57 | prefix/name indicates manual backup |
| `manual_post_20260223_062837` | manual/codex_session | 0.95 | 2026-02-23 06:28:37 | prefix/name indicates manual backup |
| `manual_post_audit_20260223_104436` | manual/codex_session | 0.95 | 2026-02-23 10:44:20 | prefix/name indicates manual backup |
| `manual_post_audit_20260223_104855` | manual/codex_session | 0.95 | 2026-02-23 10:44:20 | prefix/name indicates manual backup |
| `manual_post_audit_20260223_105325` | manual/codex_session | 0.95 | 2026-02-23 10:44:20 | prefix/name indicates manual backup |
| `manual_post_audit_20260223_111904` | manual/codex_session | 0.95 | 2026-02-23 11:18:52 | prefix/name indicates manual backup |
| `manual_post_audit_20260223_193149` | manual/codex_session | 0.95 | 2026-02-23 11:27:35 | prefix/name indicates manual backup |
| `manual_post_audit_20260223_193813` | manual/codex_session | 0.95 | 2026-02-23 11:27:35 | prefix/name indicates manual backup |
| `manual_skill_registry_20260223_213958` | manual/codex_session | 0.95 | 2026-02-23 11:27:35 | prefix/name indicates manual backup |