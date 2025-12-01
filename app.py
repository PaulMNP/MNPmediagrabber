from flask import Flask, request, send_file, render_template_string
import yt_dlp
import os
import uuid
import threading
import time

app = Flask(__name__)
progress = {}

# --- HTML Templates ---

HTML_FORM = """
<!doctype html>
<html>
<head>
  <title>MNP Media Grabber</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <link rel="icon" type="image/png" href="/static/favicon.png">
  <style>
    body { background-color: #121212; color: #f0f0f0; font-family: Arial, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; position: relative; }
    input[type="text"], input[type="submit"], select, button { width: 80%; max-width: 400px; margin-top: 10px; padding: 10px; border-radius: 8px; border: none; }
    input[type="submit"], button { background-color: #3498db; color: white; cursor: pointer; }
    input[type="submit"]:hover, button:hover { background-color: #2980b9; }
    img.logo { position: absolute; top: 20px; right: 20px; height: 80px; }
    button.theme-toggle { position: fixed; top: 20px; left: 20px; background: none; border: 2px solid #f0f0f0; color: #f0f0f0; padding: 5px 10px; border-radius: 8px; cursor: pointer; }
  </style>
</head>
<body>
  <button id="themeToggle" onclick="toggleTheme()" style="position:fixed; top:20px; left:20px; background:none; border:none; color:#f0f0f0; font-size:16px; cursor:pointer;">
  🌙 Dark
</button>
  <img src="/static/logo.png" alt="Logo" class="logo">
  <h1>MNP Media Grabber</h1>
  <form method="POST" action="/info">
    <input name="url" type="text" placeholder="Paste video URL..." required>
    <input type="submit" value="Fetch Video">
  </form>

<script>
function toggleTheme() {
  if (document.body.style.backgroundColor === "white") {
    // Switch to Dark
    document.body.style.backgroundColor = "#121212";
    document.body.style.color = "#f0f0f0";
    document.querySelectorAll('input, select, button').forEach(el => {
      if (el.id !== 'themeToggle') {
        el.style.backgroundColor = "#3498db";
        el.style.color = "white";
      }
    });
    var toggle = document.getElementById('themeToggle');
    toggle.innerText = "🌙 Dark";
    toggle.style.color = "#f0f0f0";
  } else {
    // Switch to Light
    document.body.style.backgroundColor = "white";
    document.body.style.color = "black";
    document.querySelectorAll('input, select, button').forEach(el => {
      if (el.id !== 'themeToggle') {
        el.style.backgroundColor = "#f0f0f0";
        el.style.color = "black";
      }
    });
    var toggle = document.getElementById('themeToggle');
    toggle.innerText = "☀️ Light";
    toggle.style.color = "black";
  }
}
</script>

<footer style="position: absolute; bottom: 10px; font-size: 12px; color: #888;">
  © 2025 MNP Tools. All rights reserved.
</footer>

</body>
</html>
"""

HTML_PREPARE_DOWNLOAD = """
<!doctype html>
<html>
<head>
  <title>Preparing Download</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { background-color: #121212; color: #f0f0f0; font-family: Arial, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    .loader { border: 12px solid #f3f3f3; border-top: 12px solid #3498db; border-radius: 50%; width: 100px; height: 100px; animation: spin 0.8s linear infinite; margin-bottom: 20px; }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
    h2 { margin-top: 10px; }
    img.logo { position: absolute; top: 20px; right: 20px; height: 80px; }
    button.theme-toggle { position: fixed; top: 20px; left: 20px; background: none; border: 2px solid #f0f0f0; color: #f0f0f0; padding: 5px 10px; border-radius: 8px; cursor: pointer; }
  </style>
</head>
<body>
  <button class="theme-toggle" onclick="toggleTheme()">Toggle Theme</button>
  <img src="/static/logo.png" alt="Logo" class="logo">
  <div class="loader"></div>
  <h2 id="status">Preparing your download...</h2>
  <button id="copyLink" onclick="copyLink()" style="display:none; margin-top:20px; background-color:#3498db; color:white; padding:10px 20px; border:none; border-radius:8px; cursor:pointer;">Copy Direct Download Link</button>

<script>
function toggleTheme() {
  if (document.body.style.backgroundColor === "white") {
    document.body.style.backgroundColor = "#121212"; document.body.style.color = "#f0f0f0";
    document.querySelectorAll('input, select, button').forEach(el => { el.style.backgroundColor = "#3498db"; el.style.color = "white"; });
  } else {
    document.body.style.backgroundColor = "white"; document.body.style.color = "black";
    document.querySelectorAll('input, select, button').forEach(el => { el.style.backgroundColor = "#f0f0f0"; el.style.color = "black"; });
  }
}

var source = new EventSource("/progress/{{ file_id }}");
source.onmessage = function(event) {
  document.getElementById("status").innerHTML = event.data;
  if (event.data.includes("Done")) {
    source.close();
    document.getElementById("copyLink").style.display = "block";
    setTimeout(function() {
      var a = document.createElement('a');
      a.href = '/download/{{ file_id }}/{{ fmt }}';
      a.download = '';
      document.body.appendChild(a);
      a.click();
      setTimeout(function() { window.location.href = '/'; }, 3000);
    }, 1000);
  } else if (event.data.includes("Error")) {
    source.close();
    document.getElementById("status").innerHTML = "<b style='color:red;'>" + event.data + "</b>";
  }
};

function copyLink() {
  var dummy = document.createElement("input");
  var text = window.location.origin + '/download/{{ file_id }}/{{ fmt }}';
  document.body.appendChild(dummy);
  dummy.value = text;
  dummy.select();
  document.execCommand("copy");
  document.body.removeChild(dummy);
  alert("Download link copied!");
}
</script>
</body>
</html>
"""

HTML_ERROR = """
<!doctype html>
<html>
<head>
  <title>Error</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { background-color: #121212; color: #f0f0f0; font-family: Arial, sans-serif; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100vh; margin: 0; }
    h1 { font-size: 48px; margin-bottom: 20px; }
    p { font-size: 20px; margin-bottom: 30px; }
    a.button { background-color: #3498db; color: white; padding: 10px 20px; border-radius: 8px; text-decoration: none; }
    img.logo { position: absolute; top: 20px; right: 20px; height: 80px; }
  </style>
</head>
<body>
  <img src="/static/logo.png" alt="Logo" class="logo">
  <h1>Oops!</h1>
  <p>Sorry, we couldn't find what you were looking for.</p>
  <a href="/" class="button">Go Back Home</a>
</body>
</html>
"""

# --- Routes ---

@app.route('/', methods=['GET'])
def home():
    return render_template_string(HTML_FORM)

@app.route('/info', methods=['POST'])
def info():
    url = request.form['url']

    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Unknown Title')
            thumbnail = info.get('thumbnail', '')  # <-- NEW
    except Exception as e:
        return f"Failed to fetch video info: {str(e)}"

    return f"""
    <!doctype html>
    <html>
    <head>
      <title>Choose Options</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body {{
          background-color: #121212;
          color: #f0f0f0;
          font-family: Arial, sans-serif;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          height: 100vh;
          margin: 0;
          position: relative;
        }}
        select, input[type="submit"] {{
          margin-top: 10px;
          padding: 10px;
          border-radius: 8px;
          border: none;
        }}
        input[type="submit"] {{
          background-color: #3498db;
          color: white;
          cursor: pointer;
          transition: background-color 0.3s;
        }}
        input[type="submit"]:hover {{
          background-color: #2980b9;
        }}
        img.thumbnail {{
          max-width: 300px;
          border-radius: 12px;
          margin-bottom: 20px;
        }}
        img.logo {{
          position: absolute;
          top: 20px;
          right: 20px;
          height: 50px;
        }}
      </style>
    </head>
    <body>
      <div style="position: absolute; top: 20px; right: 20px; display: flex; align-items: center; gap: 10px;">
        <button id="themeToggle" onclick="toggleTheme()" style="background:none; border:none; color:#f0f0f0; font-size:16px; cursor:pointer;">🌙 Dark</button>
        <img src="/static/logo.png" alt="Logo" class="logo">
      </div>

      <img src="{thumbnail}" alt="Thumbnail" class="thumbnail">
      <h2>🎬 {title}</h2>
      <form method="POST" action="/download-options">
        <input type="hidden" name="url" value="{url}">
        Format:<br>
        <select name="format">
          <option value="video">Video (.mp4)</option>
          <option value="audio">Audio (.m4a)</option>
        </select><br><br>
        Quality:<br>
        <select name="quality">
          <option value="best">Best Available</option>
          <option value="1080">1080p</option>
          <option value="720">720p</option>
          <option value="480">480p</option>
        </select><br><br>
        <input type="submit" value="Download">
      </form>

<script>
function toggleTheme() {{
  if (document.body.style.backgroundColor === "white") {{
    document.body.style.backgroundColor = "#121212";
    document.body.style.color = "#f0f0f0";
    document.querySelectorAll('input, select, button').forEach(el => {{
      if (el.id !== 'themeToggle') {{
        el.style.backgroundColor = "#3498db";
        el.style.color = "white";
      }}
    }});
    document.getElementById('themeToggle').innerText = "🌙 Dark";
    document.getElementById('themeToggle').style.color = "#f0f0f0";
  }} else {{
    document.body.style.backgroundColor = "white";
    document.body.style.color = "black";
    document.querySelectorAll('input, select, button').forEach(el => {{
      if (el.id !== 'themeToggle') {{
        el.style.backgroundColor = "#f0f0f0";
        el.style.color = "black";
      }}
    }});
    document.getElementById('themeToggle').innerText = "☀️ Light";
    document.getElementById('themeToggle').style.color = "black";
  }}
}}
</script>

    </body>
    </html>
    """


@app.route('/download-options', methods=['POST'])
def download_options():
    url = request.form['url']
    fmt = request.form['format']
    quality = request.form.get('quality', 'best')

    # Extract basic info first
    try:
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'downloaded_video')
    except Exception as e:
        return f"Failed to fetch video info: {str(e)}"

    # Sanitize title (remove bad characters for filename)
    safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).rstrip()
    safe_title = safe_title.replace(' ', '_')  # replace spaces with underscores if you want

    file_id = str(uuid.uuid4())
    platform = 'youtube'
    if 'tiktok.com' in url:
        platform = 'tiktok'
    elif 'instagram.com' in url:
        platform = 'instagram'

    ydl_opts = {
    'format': format_code,
    'merge_output_format': 'mp4',
    'cookiefile': 'cookies.txt',
    'outtmpl': f'{file_id}_{safe_title}.%(ext)s',
    'yes_playlist': True,
    'http_headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'en-US,en;q=0.9',
    }
}



    if fmt == 'video':
        if platform == 'youtube':
            if quality == 'best':
                format_code = 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[ext=mp4]/best'
            else:
                format_code = f'bv*[height<={quality}][vcodec^=avc1]+ba[acodec^=mp4a]/best[height<={quality}][ext=mp4]/best'
            ydl_opts['format'] = format_code
            ydl_opts['merge_output_format'] = 'mp4'
        else:
            ydl_opts['format'] = 'best'
            ydl_opts['merge_output_format'] = 'mp4'

    elif fmt == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'm4a',
            'preferredquality': '192',
        }]
    else:
        return "Invalid format selected."

    threading.Thread(target=background_download, args=(url, ydl_opts, safe_title, fmt)).start()
    return render_template_string(HTML_PREPARE_DOWNLOAD, file_id=safe_title, fmt=fmt)




def background_download(url, ydl_opts, file_id, fmt):
    def progress_hook(d):
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%').strip()
            progress[file_id] = f"Downloading... {percent}"
        elif d['status'] == 'finished':
            progress[file_id] = "Merging video and audio..."

    try:
        ydl_opts['progress_hooks'] = [progress_hook]
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        progress[file_id] = "Done! Starting download..."
    except yt_dlp.utils.DownloadError as e:
        error_message = str(e)
        if "This video is private" in error_message:
            progress[file_id] = "Error: Private video."
        elif "Sign in to confirm your age" in error_message:
            progress[file_id] = "Error: Age-restricted video."
        else:
            progress[file_id] = f"Error: {error_message}"

@app.route('/progress/<file_id>')
def progress_status(file_id):
    def generate():
        while True:
            status = progress.get(file_id, "Starting...")
            yield f"data: {status}\n\n"
            time.sleep(1)
    return app.response_class(generate(), mimetype='text/event-stream')

@app.route('/download/<file_id>/<fmt>')
def download(file_id, fmt):
    ext = 'mp4' if fmt == 'video' else 'm4a'
    filename = None

    for f in os.listdir('.'):
        if f.startswith(file_id) and f.endswith(f'.{ext}'):
            filename = f
            break

    if filename and os.path.exists(filename):
        response = send_file(filename, as_attachment=True)
        threading.Thread(target=delayed_delete, args=(filename,)).start()
        return response
    else:
        return render_template_string(HTML_ERROR)


def delayed_delete(filepath):
    time.sleep(5)
    try:
        os.remove(filepath)
    except Exception as e:
        print(f"Failed to delete file: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)