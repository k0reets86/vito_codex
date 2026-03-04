# Ko-fi Login Fix (Browser Session)

Текущий live-flow для Ko-fi в VITO работает через browser session state.

## 1) Захватить browser session

```bash
python3 scripts/kofi_auth_helper.py browser-capture --timeout-sec 420
```

Если нужно попытаться автоматически нажать кнопку входа:

```bash
python3 scripts/kofi_auth_helper.py browser-capture --timeout-sec 420 --auto-submit
```

Если запускаешь без GUI:

```bash
python3 scripts/kofi_auth_helper.py browser-capture --timeout-sec 420 --headless --auto-submit
```

## 2) Проверить, что файлы появились

- `runtime/kofi_storage_state.json`
- `runtime/kofi_storage_state.cookies.json`

## 3) Включить browser mode для Ko-fi

В `.env`:

```env
KOFI_MODE=browser_only
KOFI_STORAGE_STATE_FILE=runtime/kofi_storage_state.json
```

## 4) Full-cycle проверка

```bash
KOFI_MODE=browser_only python3 scripts/etsy_kofi_full_cycle_verify.py
```

Отчёт сохраняется в `reports/VITO_ETSY_KOFI_FULL_CYCLE_*.json`.
