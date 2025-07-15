from api import app

# Главный файл для запуска всех сервисов


def main():
    pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
    main()
