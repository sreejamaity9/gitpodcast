from flask import Flask, render_template, request, jsonify, url_for
import os
import re
import base64
import requests
from groq import Groq
import pyttsx3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Create audio directory
os.makedirs("static/audio", exist_ok=True)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in environment variables")

client = Groq(api_key=GROQ_API_KEY)

def parse_github_url(url):
    match = re.match(r'(?:https?://)?(?:www\.)?github\.com/([^/]+)/([^/]+)(?:\.git)?/?$', url.strip())
    if match:
        return match.group(1), match.group(2)
    return None, None

def get_repo_info(owner, repo, token=None):
    headers = {"Authorization": f"token {token}"} if token else {}
    
    # Repo basic info
    repo_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}", headers=headers)
    if not repo_resp.ok:
        raise Exception(f"Repository not found or access denied: {repo_resp.status_code}")
    repo_data = repo_resp.json()
    
    # Languages
    lang_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/languages", headers=headers)
    languages = list(lang_resp.json().keys()) if lang_resp.ok else []
    
    # README
    readme_content = ""
    readme_resp = requests.get(f"https://api.github.com/repos/{owner}/{repo}/readme", headers=headers)
    if readme_resp.ok:
        readme_data = readme_resp.json()
        readme_content = base64.b64decode(readme_data["content"]).decode("utf-8")
        # Truncate if too long for prompt
        if len(readme_content) > 4000:
            readme_content = readme_content[:4000] + "\n... (truncated)"
    
    return (
        repo_data.get("name", repo),
        repo_data.get("description", "No description provided."),
        languages,
        readme_content
    )

def generate_podcast_script(repo_name, description, languages, readme):
    prompt = f"""You are an engaging tech podcast host. Create a lively, conversational 1-2 minute podcast script (approximately 220-300 words) introducing this GitHub repository.

Repository: {repo_name}
Description: {description}
Languages: {', '.join(languages) if languages else 'Not specified'}

README excerpt:
{readme}

Style: Exciting, friendly, and informative. Structure it like a real podcast intro:
- Catchy opening
- What the repo does
- Key features & tech stack
- Why it's interesting/cool
- Call to action (stars, fork, contribute)

Keep it natural and spoken-language friendly. Do not include timestamps or sound effect instructions."""

    response = client.chat.completions.create(
        model="llama3-70b-8192",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.75,
        max_tokens=600
    )
    
    script = response.choices[0].message.content.strip()
    return script

def generate_audio(script):
    engine = pyttsx3.init()
    engine.setProperty('rate', 155)
    engine.setProperty('volume', 0.95)
    
    # Optional: female voice (index depends on system)
    # voices = engine.getProperty('voices')
    # engine.setProperty('voice', voices[1].id if len(voices) > 1 else voices[0].id)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"podcast_{timestamp}.wav"
    filepath = os.path.join("static", "audio", filename)
    
    engine.save_to_file(script, filepath)
    engine.runAndWait()
    
    return filename

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        repo_url = data.get("url")
        user_token = data.get("token") or GITHUB_TOKEN

        owner, repo = parse_github_url(repo_url)
        if not owner or not repo:
            return jsonify({"success": False, "error": "Invalid GitHub URL format"}), 400

        name, desc, langs, readme = get_repo_info(owner, repo, user_token)
        script = generate_podcast_script(name, desc, langs, readme)
        audio_filename = generate_audio(script)

        audio_url = url_for("static", filename=f"audio/{audio_filename}")

        return jsonify({
            "success": True,
            "audio_url": audio_url,
            "script": script,
            "repo_name": name
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True)