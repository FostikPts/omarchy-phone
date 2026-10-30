# Установка Phone на свежую машину

Плагин — это виджет Omarchy плюс CLI. Сам по себе он не ставит пакеты и не
меняет конфиги Hyprland: это делается один раз руками (шаги 2 и 4-5).

## 1. Зависимости

```bash
omarchy pkg add android-tools scrcpy
```

- `android-tools` — `adb`, без него ничего не работает;
- `scrcpy` — само окно зеркала;
- `python3` — для вотчера окна (обычно уже стоит).

## 2. Установка плагина

```bash
omarchy plugin add https://github.com/FostikPts/omarchy-phone.git --enable
```

## 3. CLI по короткому имени

Виджету симлинк не нужен (он зовёт скрипт из папки плагина), а вот горячей
клавише и терминалу — нужен:

```bash
ln -sf ~/.config/omarchy/plugins/admin.phone/bin/omarchy-phone ~/.local/bin/omarchy-phone
```

## 4. Горячие клавиши — `~/.config/hypr/bindings.lua`

```lua
o.bind("SUPER + SHIFT + P", "Mirror phone", "omarchy-phone mirror")
o.bind("SUPER + SHIFT + U", "Phone over USB", "omarchy-phone usb")
o.bind("SUPER + SHIFT + R", "Rotate mirror view", "omarchy-phone view")
```

## 5. Правило окна — `~/.config/hypr/windows.lua`

Без него окно зеркала тайлится и не подстраивается под поворот телефона.

```lua
o.window("^scrcpy$", {
  float = true,
  center = true,
  border_size = 0,
  rounding = 0,
  no_shadow = true,
  no_blur = true,
  tag = "-default-opacity",
})
```

## 6. Применить и проверить

```bash
hyprctl reload && omarchy restart shell
omarchy-phone doctor
```

`doctor` перечисляет всё, что нужно, и помечает проблемы тегом `[FAIL]`.
Если он пишет `No hard problems found` — дело не в установке.

## Если телефон не подключается

**Главная особенность:** плагин считает, что интернет раздаёт ТЕЛЕФОН
(хотспот), поэтому адрес телефона = шлюз по умолчанию. Если телефон просто
в той же Wi-Fi сети, что и ноутбук, — автоопределение не сработает.

- Телефон в той же сети: включите «Беспроводную отладку» и выполните
  `omarchy-phone pair` (Android 11+), затем `omarchy-phone mirror`.
- Первый раз проще по кабелю: `omarchy-phone usb` — включит ADB по Wi-Fi.
- `adb devices` показывает `unauthorized` — разблокируйте телефон и нажмите
  «Разрешить отладку».
- `adb devices` пуст — проверьте, что ADB по Wi-Fi включён, и что телефон и
  ноутбук в одной сети (или работает хотспот телефона).

## Удаление

```bash
omarchy plugin disable admin.phone
rm -rf ~/.config/omarchy/plugins/admin.phone ~/.local/state/omarchy-phone
rm -f ~/.local/bin/omarchy-phone
```
