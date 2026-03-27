import time
import traceback
from datetime import datetime, timezone
from telegram_bot.notifier import send_message

class ExecutionManager:
    def __init__(self):
        self.start = datetime.now(timezone.utc)
        self.last = self.start
        self.plan = []
        self.total = 0
        self.current = 0
        self.task = ""

    def set_plan(self, name, steps):
        self.task = name
        self.plan = steps
        self.total = len(steps)
        self.last = datetime.now(timezone.utc)
        send_message(f"🚀 Начинаю задачу: {name}\nЗапланировано шагов: {self.total}")

    def should_report(self):
        minutes = (datetime.now(timezone.utc) - self.start).total_seconds() / 60
        interval = 30 if minutes < 120 else 60
        return (datetime.now(timezone.utc) - self.last).total_seconds() > interval * 60

    def report(self):
        self.last = datetime.now(timezone.utc)
        send_message(
            f"⚙️ Работаю над: {self.task}\n"
            f"📍 Прогресс: {self.current}/{self.total}\n"
            f"🔍 Текущий шаг: {self.plan[self.current-1] if self.current>0 else 'начало'}\n"
            f"⏱ Время работы: {datetime.now(timezone.utc) - self.start}"
        )

    def run_step(self, func, desc):
        self.current += 1
        try:
            func()
        except Exception:
            trace = traceback.format_exc()
            try:
                func()
            except Exception:
                send_message(
                    f"❌ Ошибка на шаге: {desc}\n"
                    f"📄 Traceback:\n{trace}"
                    f"\n🛑 Я остановил выполнение задачи."
                )
                raise
        send_message(f"🟢 Шаг выполнен: {desc}")
