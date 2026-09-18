from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fase0.db"
    app_name: str = "Classificador de Comprovantes"
    storage_root: str = "./storage"
    # Cada worker do pool pode carregar os modelos do PaddleOCR em memória, e um
    # pool novo é criado por lote. Um default conservador evita que dois lotes
    # concorrentes estourem a memória da máquina.
    ocr_max_workers: int = 2
    # Limite de arquivos aceitos por requisição de upload.
    max_arquivos_por_upload: int = 50
    # Ollama local (Fase 4 — classificação por IA). Assume que o servidor já está
    # rodando e o modelo já foi baixado (`ollama pull <modelo>`) manualmente.
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    ollama_timeout_segundos: int = 15


settings = Settings()
