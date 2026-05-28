# 🛡️ ML Telegram Moderator Bot

Telegram-бот для автоматической модерации чатов с использованием методов машинного обучения. 

Бот в реальном времени анализирует поток сообщений, выявляет спам на русском языке с помощью дообученной языковой модели (RuBERT).

## ✨ Ключевые особенности (Features)
* **High-Precision ML Classification:** В качестве ядра используется дообученная архитектура Transformer (`cointegrated/rubert-tiny2`), демонстрирующая F1-Score **~0.96** на миноритарном классе (спам).
* **False Positive Mitigation:** В случае подозрения на спам бот временно изолирует сообщения пользователя и выдает математическую капчу. Непрохождение капчи за установленное время приводит к бану.
* **Multi-tenant архитектура & Дашборды:** Логирование событий (удаления, баны) в SQLite с жесткой привязкой к `chat_id`. Встроенная команда `/stats` для администраторов с изолированной аналитикой по конкретной группе.
* **RBAC (Role-Based Access Control):** Иммунитет для создателей и администраторов сообществ.

## 🛠 Стек технологий
* **Machine Learning:** PyTorch, Transformers (Hugging Face), CatBoost, Scikit-learn, Pandas.
* **Backend:** Python 3.11, aiogram 3.28.2, aiosqlite, asyncio.
* **Инфраструктура:** SQLite.

## 🔬 Исследовательская часть (Jupyter Notebooks)
В директории `/notebooks` представлены этапы разработки ML-модели:
1. `01_LogReg_model.ipynb` - Обучение базовой модели (TF-IDF + Logistic Regression)
2. `02_catboost_model.ipynb` - Обучение модели на catboost
3. `03_rubert_finetuning.ipynb` - Fine-tuning модели RuBERT-tiny2.

Все модели обучены на датасете из 500 000 строк. В ноутбуках представлены метрики и матрица ошибок.

**Доступ к весам модели:** Готовая к инференсу модель опубликована на Hugging Face Hub: [ссылка](https://huggingface.co/super-apple/spam-classifier-ru/). Бот автоматически загрузит веса при первом запуске.

## 🚀 Быстрый старт (Installation)

1. Склонируйте репозиторий:
```bash
git clone [https://github.com/cybergrenade/ml-telegram-moderator.git](https://github.com/cybergrenade/ml-telegram-moderator.git)
cd ml-telegram-moderator
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл .env в корневой директории и укажите токен вашего бота (получить у @BotFather):
```
BOT_TOKEN=123456789:ABCdefGhIJKlmnOpQrStUvWxYz
```

4. Запустите бота:
```bash
python bot.py
```

Примечание: При первом запуске автоматически создастся база данных SQLite `bot_stats.db` и скачаются веса модели с Hugging Face (~115 МБ).

## 👨‍💻 Использование в Telegram
1. Добавьте бота в вашу группу.
2. Обязательно назначьте его *Администратором* с правом удаления сообщений и блокировки пользователей.
3. Команда `/stats` (доступна только админам) покажет статистику работы фильтра в текущей группе.