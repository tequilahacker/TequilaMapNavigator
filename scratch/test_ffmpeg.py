import static_ffmpeg
import subprocess
import os

def test_static_ffmpeg():
    try:
        print("Adding paths...")
        static_ffmpeg.add_paths()
        print("Path updated:", os.environ.get("PATH", ""))
        
        # Test calling ffmpeg -version
        print("Running ffmpeg -version...")
        res = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print("Success! Output:", res.stdout.split("\n")[0])
    except Exception as e:
        print("Exception in static-ffmpeg:", e)

if __name__ == "__main__":
    test_static_ffmpeg()
