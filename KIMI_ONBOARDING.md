# Kimi — Руководство по работе с репозиторием

## Подключение к репозиторию

### 1. Генерация SSH ключа (если нет)

```bash
ssh-keygen -t ed25519 -C "kimi@oppencloud" -f ~/.ssh/id_ed25519 -N ""
cat ~/.ssh/id_ed25519.pub
```

### 2. Добавить ключ в GitHub

1. Открой https://github.com/settings/keys
2. Нажми **New SSH key**
3. Title: `kimi@oppencloud`
4. Key: вставь публичный ключ из шага 1

### 3. Клонировать репозиторий

```bash
git clone git@github.com:mustafinilshat100-maker/kimi-max.git
cd kimi-max
```

---

## Структура репозитория

```
kimi-max/
├── tasks/           ← задачи для выполнения
│   └── task_XXX_*.md
├── results/         ← готовые результаты
│   └── result_XXX_*.md
├── review/          ← проверка и правки
│   └── corrections_XXX_*.md
├── KIMI_ONBOARDING.md  ← это руководство
└── README.md
```

---

## Как работать

### Цикл работы

```
1. Проверь tasks/ → найди задачу для себя
2. Прочитай задачу → выполни
3. Сохрани результат в results/result_XXX.md
4. Жди ревью от Max
5. Если есть правки → исправь → снова results/
```

### Формат задачи (tasks/)

```markdown
# Task #XXX: Название

## Status
- [ ] Not started
- [ ] In progress  
- [ ] Completed

## Problem
Описание проблемы

## Task
Что нужно сделать

## Files to Modify
- file1.py
- file2.py

## Expected Result
Что должно получиться

## Review Criteria
1. Критерий 1
2. Критерий 2
```

### Формат результата (results/)

```markdown
# Result #XXX

## Task
Ссылка на задачу

## Changes Made
Что изменено

## Files Modified
- file1.py (строки 10-25)
- file2.py (добавлена функция X)

## Test Results
Результаты тестирования

## Notes
Любые замечания
```

---

## Текущая задача

**Смотри:** `tasks/task_001_crypto_hunter_improvement.md`

---

## Команды Git

```bash
# Скачать последние изменения
git pull origin main

# Добавить файл
git add results/result_001.md

# Закоммитить
git commit -m "[KIMI] Result #001"

# Отправить
git push origin main
```

---

## Важные правила

1. **Всегда пиши JSON** где требуется
2. **Не пропускай этапы** — делай → сохраняй → жди ревью
3. **Тестируй** перед отправкой
4. **Пиши чистый код** — без мусора и временных костылей

---

## Связь с Max

Если есть вопросы:
1. Проверь task ещё раз
2. Напиши вопрос в tasks/review/questions.md
3. Или спроси у пользователя чтобы он переслал мне

---

**Последнее обновление:** 2026-03-27
