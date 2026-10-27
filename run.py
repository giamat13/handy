import sys

import window

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == window.WINDOW_FLAG:   # תהליך בן שמציג רק את החלון
        window.show(sys.argv[2])
    else:
        import mp_path
        mp_path.fix()   # שם משתמש עם אותיות לא-ASCII: MediaPipe לא פותח את המודלים בנתיב כזה
        from app import run
        run()
