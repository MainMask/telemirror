# deploy/ — запуск telemirror на VPS под systemd

Обвязка для постоянной (24/7) работы живого зеркала и разового прогона истории
курсов. Рассчитана на bare-metal Ubuntu с systemd (не Docker; для Docker есть
`docker-compose.yaml` в корне).

## Что внутри

| Файл | Назначение |
|---|---|
| `bootstrap.sh` | одноразовый установщик: swap + симлинки юнитов + журнал + cron + `daemon-reload` |
| `setup-swap.sh` | идемпотентный ресайз `/swapfile` до 2 ГБ и `vm.swappiness=10` |
| `systemd/telemirror.service` | живое зеркало (`main.py`), 24/7 |
| `systemd/telemirror-past-courses.service` | разовый прогон истории курсов (`past_mode.py`) |
| `systemd/telemirror-alert@.service` | `OnFailure=`: шлёт в `TECH_CHANNEL`, что юнит сдался |
| `systemd/telemirror-restart.{timer,service}` | чистый рестарт зеркала раз в сутки (04:00) |
| `systemd/journald.conf.d/telemirror.conf` | `SystemMaxUse=500M` — журнал не забьёт `/var` |
| `cron.d/telemirror-tmp` | ежечасная подчистка осиротевших `/tmp/tmp*.mp4` |

## Требования

- Ubuntu + systemd ≥ 254 (нужны `OnSuccess=`, `RestartSteps=`/`RestartMaxDelaySec=`).
- Python-venv в `/root/telemirror/.venv` (`bash install.sh` из корня репо).
- `ffmpeg` в `PATH` (`apt install ffmpeg`) — для водяного знака на видео.
- PostgreSQL локально (`postgresql.service`), БД и роль `telemirror` созданы,
  параметры совпадают с `.env`.
- `.env` в корне репо заполнен (`API_ID`, `API_HASH`, `SESSION_STRING`,
  `DB_*`). `SESSION_STRING` берётся из `python login.py`. Для алертов о падении
  нужен `TECH_CHANNEL` (id канала/чата, куда бот пишет).
- Если сеть поднимается через systemd-networkd — включи
  `systemctl enable systemd-networkd-wait-online.service`, иначе
  `network-online.target` не блокирует старт (не критично: telethon
  переподключается сам, `Restart=always` подстрахует).

## Установка

```bash
cd /root/telemirror
sudo deploy/bootstrap.sh
```

Скрипт: увеличит swap, поставит симлинки юнитов в `/etc/systemd/system/`,
положит cron-файл, сделает `daemon-reload`. Сервисы **не запускает** — это
делается вручную ниже.

Юниты — симлинки на репо, cron-файл — копия. Если правишь
`deploy/cron.d/telemirror-tmp` — прогони `bootstrap.sh` ещё раз (или скопируй
руками); если правишь юниты — хватит `git pull` + `systemctl daemon-reload`.

## Живое зеркало

```bash
systemctl status telemirror.service | grep -q masked && systemctl unmask telemirror.service
systemctl enable --now telemirror.service
journalctl -u telemirror.service -f
```

Читает `.configs/mirror.config.yml`. При старте ресинкается по таблице
`binding_id`, поэтому краш не теряет сообщения.

### Как оно держится 24/7

| Отказ | Что происходит |
|---|---|
| Краш / OOM-kill / чистый выход | `Restart=always`, бэкофф 10s → 120s |
| Обрыв сети / сбой Telegram DC | telethon переподключается сам (`connection_retries=1000`); watchdog терпит отключённое состояние до **30 мин**, дольше — рестарт свежим процессом |
| **Зависание** (процесс жив, апдейты не идут) | `Type=notify` + `WatchdogSec=600`: watchdog-таск каждые 300 с делает `updates.GetState` round-trip; завис/не отвечает → `WATCHDOG=1` не уходит → systemd шлёт `SIGTERM` и рестартит |
| Стойкий crash-loop | 15 падений за час → `failed` → `OnFailure=telemirror-alert@` пишет в `TECH_CHANNEL`, сервис стоит до `systemctl reset-failed && systemctl start` |
| Бан аккаунта / отзыв сессии | попадает в crash-loop выше → алерт; чинить через `python login.py` |
| Медленная утечка памяти | `telemirror-restart.timer` — чистый рестарт в 04:00 |

Проверки:
```bash
systemctl show telemirror.service -p Type -p WatchdogUSec -p NRestarts
systemctl list-timers telemirror-restart.timer
# симуляция зависания — через ~10 мин ждём watchdog-рестарт:
systemctl kill -s STOP telemirror.service
```

## Прогон истории курсов

```bash
systemctl start telemirror-past-courses.service
journalctl -u telemirror-past-courses.service -f
```

- Конфиг подставляется из `.configs/citadel_courses.config.yml` через
  `YAML_CONFIG_ENV` (файл `main.py` сам не читает).
- `Conflicts=telemirror.service`: старт бэкофилла **останавливает** живое
  зеркало (общий `SESSION_STRING`), по успешному завершению `OnSuccess=`
  поднимает его обратно.
- При загрузке сервера юнит не стартует (нет `[Install]`).
- `past_mode.py` держит чекпоинты в БД — прерывание резюмится с места. Полный
  сброс истории и получателей — `skylon_set/clear_channels.py`.

## Память и мониторинг

Сервер тесный (2 ГБ RAM). Юниты ограничены `MemoryHigh=1100M` / `MemoryMax=1400M`
— при утечке ядро прибьёт только telemirror, не случайный процесс.

```bash
systemctl status telemirror.service
systemd-cgtop                       # потребление по cgroup
free -h
journalctl -k | grep -i oom        # были ли OOM-kill
```

Не держи VS Code Remote Server запущенным в проде — он ест ~1.2 ГБ RAM и
раньше провоцировал OOM.

## Обновление

```bash
cd /root/telemirror && git pull
systemctl daemon-reload            # если менялись файлы в deploy/systemd/
systemctl restart telemirror.service
```

## Заметки

- **Одно ядро CPU.** Водяной знак на видео = полное перекодирование: ролик
  ≤ 5 мин (`stamp_video_max_duration_s` в `mirror.config.yml`) пинит ядро на
  6–13 минут, на это время растёт задержка пересылки остального. Если критично —
  снизь порог до 120–180 или ставь 2+ ядра. Видео длиннее порога уходят как
  оригинал, без знака.
- **Строгий сэндбоксинг не включён** (`ProtectHome`, `ProtectSystem=strict`):
  ломает запись `__pycache__` в `/root/telemirror`, выигрыш для solo-бота мал.
  Оставлены `PrivateTmp`, `NoNewPrivileges`, `ProtectSystem=full`.
- **cron-очистка `/tmp`** нужна в основном для ручных запусков `past_mode.py`
  вне systemd — у юнитов `PrivateTmp=true` подчищает темпы сам.
