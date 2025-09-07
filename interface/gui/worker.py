from PyQt6.QtCore import QObject, pyqtSignal
from agent.ai_client import AIClient


class AIWorker(QObject):
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, model, chat_id, user_input):
        super().__init__()
        self._model = model
        self.chat_id = chat_id
        self.user_input = user_input

    def run(self):
        try:
            memory = self._model.load_memory_for_chat(chat_id=self.chat_id)

            ai_client = AIClient(memory=memory, model=self._model.model)

            response_dict = ai_client.ask(user_input=self.user_input)

            self.finished.emit(response_dict)

        except Exception as e:
            self.error.emit(str(e))
