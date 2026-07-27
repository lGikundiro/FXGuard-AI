import uvicorn
from dotenv import load_dotenv


# The local .env is the source of truth for the development runner. Render does
# not include this git-ignored file and supplies its own environment variables.
load_dotenv(override=True)

if __name__ == "__main__":
    uvicorn.run("backend.app.main:app", host="127.0.0.1", port=8000, reload=True)
