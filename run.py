"""Start the Naming Names app. Usage: python run.py [--port 8000]"""
import argparse
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", default=False)
    args = parser.parse_args()
    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, reload=args.reload)
