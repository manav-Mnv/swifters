import os

from app import create_app

app = create_app()


if __name__ == "__main__":
    # Never enable the Werkzeug debugger by default: it allows remote code execution.
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
