import sys
import os
import requests

def normalize_url(url):
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    return url

def fetch_text(url):
    resp = requests.get(normalize_url(url), verify=False)
    resp.raise_for_status()
    return resp.text

def fetch_image(url, save_dir="."):
    url = normalize_url(url)
    resp = requests.get(url, verify=False)
    resp.raise_for_status()
    filename = os.path.join(save_dir, url.split("/")[-1])
    with open(filename, "wb") as f:
        f.write(resp.content)
    return filename

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    if "--image" in args:
        args.remove("--image")
        save_dir = args[1] if len(args) > 1 else "."
        print("Saved:", fetch_image(args[0], save_dir))
    else:
        print(fetch_text(args[0]))
