# desktop-control — Руки Ауры

Управление окнами Windows, мышью и клавиатурой. Дополняет `aura-senses` (глаза) руками.

## Что умеет

| Инструмент | Что делает |
|-----------|-----------|
| `desktop_status()` | Состояние: зависимости, разрешение экрана, приватный режим, позиция курсора |
| `desktop_list_windows(filter)` | Список открытых окон: заголовок, размер, позиция, активное |
| `desktop_focus_window(title)` | Активировать окно по части заголовка |
| `desktop_move_window(title, x, y, width, height)` | Переместить окно и/или изменить размер (0 = не менять) |
| `desktop_window_action(title, action, confirm)` | minimize / maximize / restore / close (close требует `confirm=True`) |
| `desktop_click(x, y, button, clicks)` | Клик мышью по координатам |
| `desktop_move_mouse(x, y, duration)` | Плавно переместить курсор |
| `desktop_type_text(text, press_enter)` | Ввести текст в активное окно (через буфер обмена + Ctrl+V — раскладка не важна) |
| `desktop_hotkey(keys)` | Сочетание клавиш: `ctrl+shift+t`, `win+d`, `alt+f4` |
| `desktop_scroll(amount)` | Прокрутка (плюс — вверх, минус — вниз) |
| `desktop_highlight(x, y, width, height, seconds, label)` | Подсветить область рамкой поверх экрана — «показать достижение» |
| `desktop_privacy(on)` | Приватный режим: полностью отключает управление |

## Безопасность

- `pyautogui.FAILSAFE = True` — резкий увод мыши в левый верхний угол экрана аварийно останавливает управление.
- Приватный режим хранится в `data.json` и блокирует ВСЕ действия (кроме `desktop_status`, `desktop_list_windows`, `desktop_privacy`).
- Закрытие окна — только с явным `confirm=True`.
- Клик проверяется на попадание в границы экрана.
- Ничего не отправляется наружу: всё локально.

## Зависимости

```
pip install pyautogui pygetwindow pillow
```

Если библиотек нет — инструменты вернут подсказку, а не упадут.

## Примеры

```
desktop_list_windows()                          # что открыто
desktop_focus_window("Visual Studio Code")      # переключиться в редактор
desktop_type_text("привет, Юра", press_enter=True)
desktop_hotkey("ctrl+s")                        # сохранить
desktop_highlight(100, 200, 400, 300, 3, "вот тут")  # показать
```
